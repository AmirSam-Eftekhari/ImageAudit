"""Framework-independent application service behind the HTTP API.

Everything the API does (jobs, queries, thumbnails, reports) lives here so it can be unit-tested
without FastAPI. The route layer in ``app.py`` only translates HTTP <-> these calls.

Security notes:
  * dataset paths are validated with ``validate_dataset_path`` (+ optional allow-list);
  * images are addressed by opaque record id, never by client-supplied path, and every file read
    re-checks that the resolved path stays inside the dataset root;
  * uploaded archives are extracted with size/count/traversal/symlink guards.
"""

from __future__ import annotations

import logging
import shutil
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from ..core.cache import AnalysisCache
from ..core.config import SEVERITIES, AuditConfig, load_config
from ..core.engine import STAGES, AuditEngine
from ..core.errors import ImageAuditError, ScanCancelled, SecurityError
from ..core.models import INVALID_STATUSES, AuditResult, Finding, ImageRecord
from ..core.security import (
    find_dataset_root,
    remove_tree,
    resolve_within,
    safe_extract_zip,
    validate_dataset_path,
)
from ..core.store import AuditNotFound, AuditStore
from ..reports.generator import CONTENT_TYPES, CSV_KINDS, FORMATS, ReportGenerator
from .settings import Settings

log = logging.getLogger("imageaudit.api")

THUMB_SIZES = (128, 256, 512, 1024, 1600)
MAX_PAGE_SIZE = 200
# Rough share of total scan time per stage, used only to render a single progress bar.
_STAGE_SPAN = {"discover": (0.0, 0.02), "images": (0.02, 0.82), "annotations": (0.82, 0.90),
               "duplicates": (0.90, 0.95), "leakage": (0.95, 0.96), "statistics": (0.96, 0.98),
               "scoring": (0.98, 0.99), "findings": (0.99, 1.0), "done": (1.0, 1.0)}


class BadRequest(ImageAuditError):
    """Invalid query parameter or request body."""


class NotFound(ImageAuditError):
    pass


@dataclass
class Job:
    id: str
    path: str
    mode: str
    source: str = "path"  # path | upload
    status: str = "queued"  # queued | running | done | failed | cancelled
    stage: str = "queued"
    done: int = 0
    total: int = 0
    progress: float = 0.0
    error: str | None = None
    audit_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    finished_at: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "path": self.path, "mode": self.mode, "source": self.source,
                "status": self.status, "stage": self.stage, "done": self.done, "total": self.total,
                "progress": round(self.progress, 4), "error": self.error, "audit_id": self.audit_id,
                "created_at": self.created_at, "finished_at": self.finished_at}


@dataclass
class ImageFilter:
    split: str | None = None
    tags: list[str] = field(default_factory=list)  # all must match; "error" is an alias group
    class_name: str | None = None
    q: str | None = None
    status: str | None = None
    min_width: int | None = None
    max_width: int | None = None
    min_height: int | None = None
    max_height: int | None = None
    finding: str | None = None
    sort: str = "path"
    order: str = "asc"
    page: int = 1
    page_size: int = 48


@dataclass
class _Loaded:
    result: AuditResult
    by_id: dict[str, ImageRecord]
    class_ids: dict[str, int]


class AuditService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.home = self.settings.home
        self.store = AuditStore(self.home / "audits")
        self.cache = AnalysisCache(self.home / "cache.sqlite")
        self.uploads = self.home / "uploads"
        self.thumbs = self.home / "thumbs"
        self._pool = ThreadPoolExecutor(max_workers=max(1, self.settings.max_concurrent_scans),
                                        thread_name_prefix="imageaudit-scan")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._loaded: OrderedDict[str, _Loaded] = OrderedDict()

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.cache.close()

    # ------------------------------------------------------------------ jobs
    def submit_path(self, raw_path: str, *, mode: str = "scan",
                    config: dict[str, Any] | None = None) -> Job:
        path = validate_dataset_path(raw_path, self.settings.allowed_roots)
        cfg = self._config(config)
        return self._submit(path, cfg, mode, source="path", cleanup=None)

    def submit_archive(self, archive: Path, display_name: str, *, mode: str = "scan",
                       config: dict[str, Any] | None = None) -> Job:
        """``archive`` is a temp file owned by the caller; it is deleted after extraction."""
        cfg = self._config(config)
        return self._submit(archive, cfg, mode, source="upload", cleanup=archive, display=display_name)

    def _config(self, overrides: dict[str, Any] | None) -> AuditConfig:
        cfg = load_config(None, overrides or None)
        if cfg.workers > 32:
            raise BadRequest("workers must be <= 32")
        return cfg

    def _submit(self, path: Path, cfg: AuditConfig, mode: str, *, source: str, cleanup: Path | None,
                display: str | None = None) -> Job:
        if mode not in ("scan", "validate"):
            raise BadRequest("mode must be 'scan' or 'validate'")
        job = Job(id=uuid.uuid4().hex[:12], path=display or str(path), mode=mode, source=source)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run_job, job, path, cfg, cleanup)
        return job

    def _run_job(self, job: Job, path: Path, cfg: AuditConfig, cleanup: Path | None) -> None:
        upload_dir: Path | None = None
        try:
            if job.cancel.is_set():
                raise ScanCancelled("Scan cancelled")
            job.status = "running"
            root = path
            if job.source == "upload":
                job.stage = "extracting"
                upload_dir = self.uploads / job.id
                root = safe_extract_zip(path, upload_dir)
                root = find_dataset_root(root)
            engine = AuditEngine(cfg, cache=self.cache)
            result = engine.run(root, mode=job.mode, progress=lambda s, d, t: self._on_progress(job, s, d, t),
                                cancel=job.cancel)
            if job.source == "upload":
                result.dataset.name = Path(job.path).stem or result.dataset.name
            self.store.save(result)
            job.audit_id, job.status, job.progress, job.stage = result.id, "done", 1.0, "done"
        except ScanCancelled:
            job.status, job.error = "cancelled", "Scan cancelled"
            self._drop_upload(upload_dir)
        except ImageAuditError as exc:
            job.status, job.error = "failed", str(exc)
            self._drop_upload(upload_dir)
        except Exception as exc:  # noqa: BLE001 - surface unexpected failures with their type
            log.exception("Scan %s crashed", job.id)
            job.status, job.error = "failed", f"Unexpected {type(exc).__name__}: {exc}"
            self._drop_upload(upload_dir)
        finally:
            job.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
            if cleanup is not None:
                Path(cleanup).unlink(missing_ok=True)

    @staticmethod
    def _on_progress(job: Job, stage: str, done: int, total: int) -> None:
        lo, hi = _STAGE_SPAN.get(stage, (0.0, 0.0))
        job.stage, job.done, job.total = stage, done, total
        job.progress = lo + (hi - lo) * (done / total if total else 0.0)

    def _drop_upload(self, upload_dir: Path | None) -> None:
        if upload_dir is not None:
            remove_tree(upload_dir)

    def job(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise NotFound(f"Scan '{job_id}' not found")
        return job

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [j.public() for j in items]

    def cancel(self, job_id: str) -> Job:
        job = self.job(job_id)
        job.cancel.set()
        return job

    # ------------------------------------------------------------------ audits
    def audits(self) -> list[dict[str, Any]]:
        return self.store.list()

    def _load(self, audit_id: str) -> _Loaded:
        with self._lock:
            if audit_id in self._loaded:
                self._loaded.move_to_end(audit_id)
                return self._loaded[audit_id]
        try:
            result = self.store.load(audit_id)
        except AuditNotFound as exc:
            raise NotFound(str(exc)) from exc
        loaded = _Loaded(result, {i.id: i for i in result.images},
                         {n: k for k, n in enumerate(result.dataset.class_names)})
        with self._lock:
            self._loaded[audit_id] = loaded
            while len(self._loaded) > 3:
                self._loaded.popitem(last=False)
        return loaded

    def delete_audit(self, audit_id: str) -> None:
        """Permanently delete one audit: stored result + summary, thumbnails and extracted uploads.

        Dataset directories that were scanned in place are never touched. Raises ``NotFound`` for an
        unknown or malformed id (nothing is deleted in that case).
        """
        try:
            present = self.store.exists(audit_id)  # also validates the id before any path is built
        except AuditNotFound as exc:
            raise NotFound(str(exc)) from exc
        if not present:
            raise NotFound(f"Audit '{audit_id}' not found")
        root: Path | None = None
        try:  # best effort: a corrupt result file must still be deletable
            root = Path(self._load(audit_id).result.dataset.root)
        except (NotFound, ValueError, KeyError, TypeError, OSError):
            log.warning("Audit %s is unreadable; deleting its files without upload cleanup", audit_id)
        with self._lock:
            self._loaded.pop(audit_id, None)
        self.store.delete(audit_id)
        shutil.rmtree(self.thumbs / audit_id, ignore_errors=True)
        try:  # only ever delete extracted uploads that live under our own uploads directory
            if root is not None and self.uploads.exists():
                uploads = self.uploads.resolve()
                resolved = root.resolve()
                if resolved != uploads and resolved.is_relative_to(uploads):
                    remove_tree(uploads / resolved.relative_to(uploads).parts[0])
        except (OSError, ValueError):
            log.warning("Could not remove uploaded data for %s", audit_id)

    def overview(self, audit_id: str) -> dict[str, Any]:
        r = self._load(audit_id).result
        return {
            **r.summary(), "version": r.version, "dataset": _asdict(r.dataset), "config": r.config,
            "health": r.health, "statistics": r.statistics,
            "findings": [_finding_public(f, id_limit=0) for f in r.findings],
            "leakage": _leakage_public(r.leakage),
            "issue_total": len(r.issues),
            "severity_order": list(SEVERITIES),
        }

    # ------------------------------------------------------------------ images
    def image_page(self, audit_id: str, flt: ImageFilter) -> dict[str, Any]:
        loaded = self._load(audit_id)
        r = loaded.result
        page_size = max(1, min(flt.page_size, MAX_PAGE_SIZE))
        page = max(1, flt.page)
        allowed_ids: set[str] | None = None
        if flt.finding:
            finding = next((f for f in r.findings if f.id == flt.finding), None)
            if finding is None:
                raise NotFound(f"Finding '{flt.finding}' not found")
            allowed_ids = set(finding.affected_image_ids)
        class_id: int | None = None
        if flt.class_name:
            if flt.class_name not in loaded.class_ids:
                raise BadRequest(f"Unknown class '{flt.class_name}'")
            class_id = loaded.class_ids[flt.class_name]

        needle = flt.q.lower() if flt.q else None
        rows = []
        for img in r.images:
            if flt.split and img.split != flt.split:
                continue
            if flt.status and img.status != flt.status:
                continue
            if allowed_ids is not None and img.id not in allowed_ids:
                continue
            if needle and needle not in img.path.lower():
                continue
            if class_id is not None and not any(b.class_id == class_id for b in img.boxes):
                continue
            if not _dims_ok(img, flt):
                continue
            if flt.tags and not all(_has_tag(img, t) for t in flt.tags):
                continue
            rows.append(img)

        key = _SORTS.get(flt.sort)
        if key is None:
            raise BadRequest(f"sort must be one of {sorted(_SORTS)}")
        rows.sort(key=lambda i: (key(i) is None, key(i) if key(i) is not None else 0, i.path),
                  reverse=flt.order == "desc")
        total = len(rows)
        start = (page - 1) * page_size
        return {"total": total, "page": page, "page_size": page_size,
                "items": [_image_item(i, r.dataset.class_names) for i in rows[start:start + page_size]],
                "available_tags": sorted({t for i in r.images for t in i.tags}),
                "splits": r.dataset.splits, "classes": r.dataset.class_names}

    def image_detail(self, audit_id: str, image_id: str) -> dict[str, Any]:
        loaded = self._load(audit_id)
        img = self._image(loaded, image_id)
        names = loaded.result.dataset.class_names
        groups = [g for g in loaded.result.duplicates if any(m.image_id == image_id for m in g.members)]
        return {
            **_image_item(img, names),
            "sha256": img.sha256, "phash": img.phash, "dhash": img.dhash, "mode": img.mode,
            "channels": img.channels, "brightness": img.brightness, "contrast": img.contrast,
            "is_grayscale": img.is_grayscale, "error": img.error, "label_path": img.label_path,
            "label_status": img.label_status, "invalid_annotation_count": img.invalid_annotation_count,
            "boxes": [{"class_id": b.class_id, "class_name": _class_name(names, b.class_id), "cx": b.cx,
                       "cy": b.cy, "w": b.w, "h": b.h, "line": b.line, "flags": b.flags} for b in img.boxes],
            "issues": [i.to_dict() for i in loaded.result.issues if i.image_id == image_id],
            "duplicate_groups": [{"id": g.id, "kind": g.kind, "scope": g.scope, "size": len(g.members),
                                  "splits": g.splits} for g in groups],
        }

    @staticmethod
    def _image(loaded: _Loaded, image_id: str) -> ImageRecord:
        img = loaded.by_id.get(image_id)
        if img is None:
            raise NotFound(f"Image '{image_id}' not found")
        return img

    def thumbnail(self, audit_id: str, image_id: str, size: int = 256) -> Path:
        loaded = self._load(audit_id)
        img = self._image(loaded, image_id)
        if img.status != "ok":
            raise NotFound(f"No preview available: image is {img.status}")
        size = next((s for s in THUMB_SIZES if s >= size), THUMB_SIZES[-1])
        target = self.thumbs / audit_id / f"{image_id}_{size}.jpg"
        if target.is_file():
            return target
        try:
            src = resolve_within(Path(loaded.result.dataset.root), img.path)
        except SecurityError as exc:
            raise NotFound("Image path is not inside the dataset") from exc
        if not src.is_file():
            raise NotFound("Image file no longer exists on disk")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_bytes(make_thumbnail(src, size))
        tmp.replace(target)
        return target

    # ------------------------------------------------------------------ annotations / dups / findings
    def issues_page(self, audit_id: str, *, code: str | None = None, level: str | None = None,
                    split: str | None = None, q: str | None = None, page: int = 1,
                    page_size: int = 50) -> dict[str, Any]:
        r = self._load(audit_id).result
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        rows = [i for i in r.issues
                if (not code or i.code == code) and (not level or i.level == level)
                and (not split or i.split == split)
                and (not q or q.lower() in (i.image_path or i.label_path or "").lower())]
        start = (max(1, page) - 1) * page_size
        return {"total": len(rows), "page": max(1, page), "page_size": page_size,
                "items": [i.to_dict() for i in rows[start:start + page_size]],
                "code_counts": r.statistics.get("issue_counts", {}),
                "class_names": r.dataset.class_names}

    def duplicates_page(self, audit_id: str, *, kind: str | None = None, scope: str | None = None,
                        split: str | None = None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        r = self._load(audit_id).result
        page_size = max(1, min(page_size, 100))
        rows = [g for g in r.duplicates
                if (not kind or g.kind == kind) and (not scope or g.scope == scope)
                and (not split or split in g.splits)]
        rows.sort(key=lambda g: (g.scope != "cross_split", g.kind != "exact", -len(g.members), g.id))
        start = (max(1, page) - 1) * page_size
        return {"total": len(rows), "page": max(1, page), "page_size": page_size,
                "summary": r.statistics.get("duplicates", {}),
                "items": [g.to_dict() for g in rows[start:start + page_size]]}

    def leakage(self, audit_id: str) -> dict[str, Any]:
        return _leakage_public(self._load(audit_id).result.leakage)

    def findings(self, audit_id: str, *, severity: str | None = None, category: str | None = None,
                 split: str | None = None, class_name: str | None = None) -> dict[str, Any]:
        r = self._load(audit_id).result
        if severity and severity not in SEVERITIES:
            raise BadRequest(f"severity must be one of {list(SEVERITIES)}")
        rows = [f for f in r.findings
                if (not severity or f.severity == severity) and (not category or f.category == category)
                and (not split or split in f.splits) and (not class_name or class_name in f.classes)]
        return {"total": len(rows), "items": [_finding_public(f) for f in rows],
                "categories": sorted({f.category for f in r.findings}),
                "splits": r.dataset.splits, "classes": r.dataset.class_names}

    # ------------------------------------------------------------------ reports
    def report(self, audit_id: str, fmt: str, csv_kind: str = "images",
               include_images: bool = False) -> tuple[bytes, str, str]:
        if fmt not in FORMATS:
            raise BadRequest(f"format must be one of {list(FORMATS)}")
        if csv_kind not in CSV_KINDS:
            raise BadRequest(f"csv_kind must be one of {list(CSV_KINDS)}")
        result = self._load(audit_id).result
        gen = ReportGenerator()
        data = gen.generate(result, fmt, csv_kind=csv_kind, include_images=include_images)
        return data, CONTENT_TYPES[fmt], gen.filename(result, fmt, csv_kind)


# ---------------------------------------------------------------------- helpers
def make_thumbnail(path: Path, size: int) -> bytes:
    """Decode with a bounded memory footprint (JPEG draft mode) and return JPEG bytes."""
    with Image.open(path) as im:
        if im.format == "JPEG":
            im.draft("RGB", (size * 2, size * 2))
        im.load()
        im = ImageOps.exif_transpose(im)
        if im.mode.startswith("I") or im.mode == "F":
            arr = np.asarray(im).astype(np.float64)
            span = arr.max() - arr.min()
            im = Image.fromarray(((arr - arr.min()) / (span or 1.0) * 255).astype(np.uint8))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((size, size), Image.Resampling.LANCZOS)
        buf = BytesIO()
        im.save(buf, "JPEG", quality=82 if size <= 512 else 88)
        return buf.getvalue()


def _asdict(obj: Any) -> dict[str, Any]:
    import dataclasses
    return dataclasses.asdict(obj)


def _class_name(names: list[str], cid: int) -> str:
    return names[cid] if 0 <= cid < len(names) else f"class_{cid}"


def _has_tag(img: ImageRecord, tag: str) -> bool:
    if tag == "error":  # anything that makes the image or its labels unusable
        return img.status in INVALID_STATUSES or "invalid_annotations" in img.tags
    if tag == "duplicate":
        return any(t in img.tags for t in ("exact_duplicate", "near_duplicate"))
    return tag in img.tags


def _dims_ok(img: ImageRecord, f: ImageFilter) -> bool:
    checks = ((f.min_width, img.width, True), (f.max_width, img.width, False),
              (f.min_height, img.height, True), (f.max_height, img.height, False))
    for bound, value, is_min in checks:
        if bound is None:
            continue
        if value is None or (value < bound if is_min else value > bound):
            return False
    return True


_SORTS = {
    "path": lambda i: i.path,
    "size": lambda i: i.file_size,
    "width": lambda i: i.width,
    "height": lambda i: i.height,
    "blur": lambda i: i.blur_score,
    "brightness": lambda i: i.brightness,
    "annotations": lambda i: len(i.boxes),
}


def _image_item(img: ImageRecord, names: list[str]) -> dict[str, Any]:
    return {
        "id": img.id, "path": img.path, "split": img.split, "status": img.status, "format": img.format,
        "width": img.width, "height": img.height, "file_size": img.file_size, "tags": img.tags,
        "annotation_count": len(img.boxes),
        "classes": sorted({_class_name(names, b.class_id) for b in img.boxes}),
        "blur_score": None if img.blur_score is None else round(img.blur_score, 2),
        "has_preview": img.status == "ok",
    }


def _finding_public(f: Finding, id_limit: int = 50) -> dict[str, Any]:
    d = f.to_dict()
    total = len(f.affected_image_ids)
    d["affected_image_ids"] = f.affected_image_ids[:id_limit]
    d["affected_image_total"] = total
    return d


def _leakage_public(lk: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in lk.items() if k not in ("leaked_image_ids", "pairs")}
    out["pairs"] = [{k: v for k, v in p.items() if k != "image_ids"} for p in lk.get("pairs", [])]
    return out


__all__ = ["STAGES", "AuditService", "BadRequest", "ImageFilter", "Job", "NotFound", "make_thumbnail"]
