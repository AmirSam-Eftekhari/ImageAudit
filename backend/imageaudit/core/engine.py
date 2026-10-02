"""AuditEngine: orchestrates discovery -> analysis -> detection -> scoring -> findings.

The engine is independent of FastAPI and the CLI; both call `AuditEngine.run`.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from .. import __version__
from ..analyzers.image import ImageAnalyzer
from ..analyzers.quality import quality_flags
from ..datasets.base import DatasetLayout, image_id
from ..datasets.registry import detect_adapter
from ..detectors.duplicates import DuplicateDetector, summarize_duplicates
from ..detectors.leakage import LeakageDetector
from ..scoring.health import HealthScorer
from .cache import AnalysisCache
from .config import AuditConfig
from .errors import DatasetError, ScanCancelled
from .findings import FindingBuilder
from .models import (
    AnnotationIssue,
    AuditResult,
    ImageMeasurements,
    ImageRecord,
)
from .security import validate_dataset_path
from .statistics import compute_statistics

log = logging.getLogger("imageaudit.engine")
ProgressCallback = Callable[[str, int, int], None]
T = TypeVar("T")

STAGES = ("discover", "images", "annotations", "duplicates", "leakage", "statistics", "scoring", "findings")


def _chunks(seq: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


class AuditEngine:
    """Usage::

        result = AuditEngine(AuditConfig()).run("path/to/dataset")
        print(result.health["overall"])
    """

    def __init__(self, config: AuditConfig | None = None, *, cache: AnalysisCache | None = None) -> None:
        self.cfg = (config or AuditConfig()).validate()
        self._cache = cache

    def run(self, root: str | Path, *, mode: str = "scan", progress: ProgressCallback | None = None,
            cancel: threading.Event | None = None) -> AuditResult:
        if mode not in ("scan", "validate"):
            raise ValueError("mode must be 'scan' or 'validate'")
        started = time.monotonic()
        full = mode == "scan"

        def tick(stage: str, done: int = 0, total: int = 0) -> None:
            if cancel is not None and cancel.is_set():
                raise ScanCancelled("Scan cancelled")
            if progress:
                progress(stage, done, total)

        tick("discover")
        root_path = validate_dataset_path(root, allowed_roots=[])
        adapter = detect_adapter(root_path)
        layout = adapter.discover(root_path)
        if not layout.samples:
            raise DatasetError(f"No images found in {root_path}")
        log.info("Discovered %d images (%s)", len(layout.samples), layout.info.format)

        records = self._analyze_images(layout, ImageAnalyzer(self.cfg, full=full), tick)

        # --- annotations -----------------------------------------------------------
        issues: list[AnnotationIssue] = []
        total_lines = invalid_lines = 0
        tracked = {os.path.normcase(str(s.label_path)) for s in layout.samples if s.label_path}
        for n, (sample, rec) in enumerate(zip(layout.samples, records, strict=True), start=1):
            parsed = adapter.read_annotations(sample, layout, self.cfg.annotations)
            rec.label_status = parsed.status
            rec.boxes = parsed.boxes
            total_lines += parsed.total_lines
            invalid_lines += parsed.invalid_lines
            rec.invalid_annotation_count = parsed.invalid_lines
            if parsed.status == "missing" and sample.label_path is not None:
                rec.label_path = sample.label_path.relative_to(root_path).as_posix() \
                    if sample.label_path.is_relative_to(root_path) else sample.label_path.name
                parsed.issues.append(AnnotationIssue(
                    code="missing_label_file", label_path=rec.label_path,
                    message="No label file found for this image"))
            elif sample.label_path is not None:
                rec.label_path = parsed.issues[0].label_path if parsed.issues else \
                    sample.label_path.relative_to(root_path).as_posix()
            for iss in parsed.issues:
                iss.image_id, iss.image_path, iss.split = rec.id, rec.path, rec.split
            issues.extend(parsed.issues)
            if n % 500 == 0:
                tick("annotations", n, len(records))
        tick("annotations", len(records), len(records))

        orphans = 0
        for lf in layout.label_files:
            if os.path.normcase(str(lf)) not in tracked:
                orphans += 1
                issues.append(AnnotationIssue(
                    code="orphan_label", label_path=lf.relative_to(root_path).as_posix()
                    if lf.is_relative_to(root_path) else lf.name,
                    message="Label file has no matching image"))

        # --- duplicates & leakage --------------------------------------------------
        groups = []
        if full:
            tick("duplicates")
            detector = DuplicateDetector(self.cfg.duplicates)
            groups = detector.detect(records)
            if detector.skipped_buckets:
                layout.info.notes.append(
                    f"{detector.skipped_buckets} oversized hash bucket(s) skipped during near-duplicate search")
        tick("leakage")
        leakage = LeakageDetector().analyze(groups, records)
        dup_summary = summarize_duplicates(groups)
        if not full:  # duplicate/leakage analysis was not run: never report it as "clean"
            leakage["applicable"] = False
            leakage["note"] = "Not computed in validate mode (run `imageaudit scan` for leakage analysis)."
            dup_summary["skipped"] = True
        self._assign_tags(records, groups, leakage)

        # --- statistics, score, findings --------------------------------------------
        tick("statistics")
        stats = compute_statistics(records, issues, layout.info, total_lines=total_lines,
                                   invalid_lines=invalid_lines, orphan_labels=orphans,
                                   duplicate_summary=dup_summary)
        tick("scoring")
        health = HealthScorer(self.cfg.scoring).score(
            records, invalid_lines=invalid_lines, total_lines=total_lines, has_labels=layout.info.has_labels,
            class_counts=[c["count"] for c in stats["classes"]], leakage=leakage, duplicate_summary=dup_summary)
        tick("findings")
        findings = FindingBuilder(self.cfg, records, issues, groups, leakage, stats,
                                  layout.info.class_names, layout.info.notes).build()

        tick("done", 1, 1)
        stamp = datetime.now(UTC)
        return AuditResult(
            id=f"{stamp:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}", version=__version__,
            created_at=stamp.isoformat(timespec="seconds"), duration_s=round(time.monotonic() - started, 2),
            mode=mode, dataset=layout.info, config=self.cfg.to_dict(), images=records, issues=issues,
            duplicates=groups, leakage=leakage, statistics=stats, health=health, findings=findings)

    # ------------------------------------------------------------------ internals
    def _analyze_images(self, layout: DatasetLayout, analyzer: ImageAnalyzer,
                        tick: Callable[..., None]) -> list[ImageRecord]:
        cache = self._cache if self.cfg.use_cache else None
        params = analyzer.cache_params()
        total = len(layout.samples)
        measured: list[ImageMeasurements | None] = [None] * total
        pending: list[tuple[int, str, int, int]] = []
        for idx, s in enumerate(layout.samples):
            key = str(s.path)
            try:
                st = s.path.stat()
                stat_key = (st.st_size, st.st_mtime_ns)
            except OSError:
                stat_key = (-1, -1)
            hit = None
            if cache is not None and not s.unsupported and stat_key[0] >= 0:
                hit = cache.get(key, stat_key[0], stat_key[1], params)
            if hit is not None:
                measured[idx] = hit
            else:
                pending.append((idx, key, *stat_key))
        done = total - len(pending)
        tick("images", done, total)

        workers = self.cfg.effective_workers()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="imageaudit") as pool:
            for batch in _chunks(pending, max(1, workers * 8)):
                results = list(pool.map(
                    lambda p: analyzer.analyze(layout.samples[p[0]].path,
                                               force_status="unsupported" if layout.samples[p[0]].unsupported else None),
                    batch))
                puts = []
                for (idx, key, size, mtime), meas in zip(batch, results, strict=True):
                    measured[idx] = meas
                    if size >= 0 and not layout.samples[idx].unsupported:
                        puts.append((key, size, mtime, params, meas))
                if cache is not None:
                    cache.put_many(puts)
                done += len(batch)
                tick("images", done, total)

        records: list[ImageRecord] = []
        for s, meas in zip(layout.samples, measured, strict=True):
            assert meas is not None
            rec = ImageRecord(**meas.to_dict(), id=image_id(s.rel_path), path=s.rel_path, split=s.split)
            if rec.width and rec.height:
                rec.aspect_ratio = round(rec.width / rec.height, 4)
            records.append(rec)
        return records

    def _assign_tags(self, records: list[ImageRecord], groups, leakage: dict) -> None:
        exact_ids: set[str] = set()
        near_ids: set[str] = set()
        cross_ids: set[str] = set()
        for g in groups:
            sha_counts = Counter(m.sha256 for m in g.members)
            for m in g.members:
                if sha_counts[m.sha256] > 1:
                    exact_ids.add(m.image_id)
                if len(sha_counts) > 1:
                    near_ids.add(m.image_id)
                if g.scope == "cross_split":
                    cross_ids.add(m.image_id)
        for r in records:
            tags: list[str] = []
            if r.status != "ok":
                tags.append(r.status)
            else:
                tags += quality_flags(r, self.cfg.quality)
                if r.is_grayscale:
                    tags.append("grayscale")
            if r.label_status == "missing":
                tags.append("missing_label")
            elif r.label_status == "empty":
                tags.append("empty_label")
            if r.invalid_annotation_count:
                tags.append("invalid_annotations")
            if any(f in ("tiny", "large", "out_of_bounds", "duplicate") for b in r.boxes for f in b.flags):
                tags.append("suspicious_boxes")
            if r.id in exact_ids:
                tags.append("exact_duplicate")
            if r.id in near_ids:
                tags.append("near_duplicate")
            if r.id in cross_ids:
                tags.append("cross_split_leak")
            r.tags = tags
