"""Converts measurements into structured, actionable findings.

Severity rules are deliberately simple and documented in docs/findings.md so a reader can
predict why a finding has the severity it has.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from .config import SEVERITIES, AuditConfig
from .models import AnnotationIssue, DuplicateGroup, Finding, ImageRecord

MAX_EXAMPLES = 8
MAX_AFFECTED_IDS = 5000

_SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def severity_at_least(severity: str, floor: str) -> bool:
    return _SEV_RANK[severity] >= _SEV_RANK[floor]


class FindingBuilder:
    def __init__(self, cfg: AuditConfig, images: Sequence[ImageRecord], issues: Sequence[AnnotationIssue],
                 groups: Sequence[DuplicateGroup], leakage: dict[str, Any], stats: dict[str, Any],
                 class_names: Sequence[str], notes: Sequence[str] = ()) -> None:
        self.notes = list(notes)
        self.cfg, self.images, self.issues = cfg, list(images), list(issues)
        self.groups, self.leakage, self.stats = list(groups), leakage, stats
        self.class_names = list(class_names)
        self.by_id = {i.id: i for i in self.images}
        self.findings: list[Finding] = []

    # ------------------------------------------------------------------- public
    def build(self) -> list[Finding]:
        self._structure()
        self._integrity()
        self._leakage()
        self._duplicates()
        self._annotations()
        self._class_balance()
        self._quality()
        for f in self.findings:
            self._enrich(f)
        self.findings.sort(key=lambda f: (_SEV_RANK[f.severity], -f.affected_count, f.id))
        return self.findings

    # ------------------------------------------------------------------ helpers
    def _add(self, fid: str, severity: str, category: str, title: str, description: str,
             recommendation: str, *, ids: Sequence[str] = (), count: int | None = None,
             examples: list[dict[str, Any]] | None = None, metric: dict[str, Any] | None = None) -> None:
        ids = list(dict.fromkeys(ids))
        self.findings.append(Finding(
            id=fid, severity=severity, category=category, title=title, description=description,
            affected_count=count if count is not None else len(ids), recommendation=recommendation,
            examples=(examples or [])[:MAX_EXAMPLES], affected_image_ids=ids[:MAX_AFFECTED_IDS],
            metric=metric or {}))

    def _img_examples(self, ids: Sequence[str], detail: str | dict[str, str] = "") -> list[dict[str, Any]]:
        out = []
        for i in list(ids)[:MAX_EXAMPLES]:
            r = self.by_id[i]
            d = detail.get(i, "") if isinstance(detail, dict) else detail
            out.append({"image_id": r.id, "path": r.path, "split": r.split, "detail": d or (r.error or "")})
        return out

    def _enrich(self, f: Finding) -> None:
        recs = [self.by_id[i] for i in f.affected_image_ids if i in self.by_id]
        f.splits = sorted({r.split for r in recs})
        names: set[str] = set()
        for r in recs:
            for b in r.boxes:
                names.add(self.class_names[b.class_id] if b.class_id < len(self.class_names) else f"class_{b.class_id}")
        names.update(str(c) for c in f.metric.get("classes", []))  # class-level findings name their classes
        f.classes = sorted(names)

    def _ids_with_tag(self, tag: str) -> list[str]:
        return [i.id for i in self.images if tag in i.tags]

    # --------------------------------------------------------------- categories
    def _structure(self) -> None:
        total = len(self.images)
        if total == 0:
            self._add("no_images", "critical", "dataset_structure", "No images found",
                      "The dataset directory contains no image files.",
                      "Check the dataset path and that data.yaml split paths are correct.", count=0)
            return
        splits = self.stats["splits"]
        names = {s["split"] for s in splits}
        if "train" in names and "val" not in names:
            self._add("no_val_split", "medium", "dataset_structure", "No validation split",
                      "A train split exists but no validation split was found, so model selection "
                      "and overfitting checks have no held-out data.",
                      "Create a validation split (commonly 10-20% of the data) without overlap with train.",
                      count=0)
        if "train" in names and "test" not in names:
            self._add("no_test_split", "info", "dataset_structure", "No test split",
                      "No test split was found. This is common, but final evaluation then reuses "
                      "validation data.", "Consider holding out a test split for unbiased evaluation.", count=0)
        train = next((s for s in splits if s["split"] == "train"), None)
        others = [s for s in splits if s["split"] in ("val", "test")]
        if train and others and total:
            small = [s for s in others if s["images"] / total < 0.05 and s["split"] == "val"]
            if small:
                self._add("tiny_val_split", "low", "dataset_structure", "Validation split is very small",
                          f"Validation holds {small[0]['images']} of {total} images "
                          f"({small[0]['images'] / total:.1%}); metrics computed on it will be noisy.",
                          "Increase the validation split or use cross-validation.", count=small[0]["images"])
        for note in self.notes:
            self._add("layout_note", "low", "dataset_structure", "Dataset layout note", note,
                      "Verify the split paths in data.yaml.", count=0)

    def _integrity(self) -> None:
        n = len(self.images)
        for status, title, sev, rec in (
            ("corrupted", "Corrupted or unreadable images", "high",
             "Delete or re-export these files; training loaders will crash or skip them."),
            ("zero_byte", "Zero-byte image files", "high", "Remove empty files or restore them from source."),
            ("unsupported", "Unsupported file formats in image folders", "medium",
             "Convert to JPEG/PNG/BMP/WebP/TIFF or move the files out of the images folder."),
            ("too_large", "Files exceeding size/pixel limits", "medium",
             "Downscale these images or raise max_file_bytes / max_pixels in the config."),
        ):
            ids = [i.id for i in self.images if i.status == status]
            if not ids:
                continue
            if status == "corrupted" and n and len(ids) / n >= 0.05:
                sev = "critical"
            self._add(f"integrity_{status}", sev, "integrity", f"{title} ({len(ids)})",
                      f"{len(ids)} of {n} files ({len(ids) / n:.1%}) have status '{status}'.", rec,
                      ids=ids, examples=self._img_examples(ids), metric={"rate": len(ids) / n})

    def _leakage(self) -> None:
        lk = self.leakage
        if not lk.get("cross_split_groups"):
            return
        cross = [g for g in self.groups if g.scope == "cross_split"]
        for kind, sev, title, expl in (
            ("exact", "critical", "Exact duplicate images across splits",
             "Byte-identical files appear in more than one split. Evaluation metrics on the "
             "held-out split are inflated because the model has seen these exact files."),
            ("perceptual", "high", "Near-duplicate images across splits",
             "Visually near-identical images (perceptual-hash match, not byte-identical) appear "
             "in more than one split. They may be re-encodes, resizes or light edits of the same image."),
        ):
            gs = [g for g in cross if g.kind == kind]
            if not gs:
                continue
            ids = [m.image_id for g in gs for m in g.members]
            ex = [{"image_id": g.members[0].image_id, "path": g.members[0].path, "split": g.members[0].split,
                   "group_id": g.id,
                   "detail": " ≡ ".join(f"{m.path} ({m.split})" for m in g.members[:4])} for g in gs[:MAX_EXAMPLES]]
            self._add(f"leakage_{kind}", sev, "data_leakage", f"{title} ({len(gs)} groups)",
                      f"{len(gs)} duplicate group(s) span multiple splits, involving {len(set(ids))} images. {expl}",
                      "Review the duplicated images and remove them from the evaluation split "
                      "(or de-duplicate before splitting).", ids=ids, count=len(set(ids)), examples=ex,
                      metric={"groups": len(gs), "leaked_images": lk.get("leaked_images", 0)})

    def _duplicates(self) -> None:
        within = [g for g in self.groups if g.scope == "within_split"]
        for kind, sev_low, title in (("exact", "medium", "Exact duplicate images within a split"),
                                     ("perceptual", "low", "Near-duplicate images within a split")):
            gs = [g for g in within if g.kind == kind]
            if not gs:
                continue
            ids = [m.image_id for g in gs for m in g.members]
            redundant = sum(len(g.members) - 1 for g in gs)
            valid = max(1, sum(1 for i in self.images if i.status == "ok"))
            sev = "high" if kind == "exact" and redundant / valid >= 0.10 else sev_low
            ex = [{"image_id": g.members[0].image_id, "path": g.members[0].path, "split": g.members[0].split,
                   "group_id": g.id, "detail": ", ".join(m.path for m in g.members[:4])} for g in gs[:MAX_EXAMPLES]]
            self._add(f"duplicates_{kind}", sev, "duplicates", f"{title} ({len(gs)} groups)",
                      f"{len(gs)} group(s) contain {len(ids)} images; {redundant} are redundant copies "
                      f"({redundant / valid:.1%} of valid images). Duplicates over-weight some samples "
                      "and bias training.", "Keep one image per group and delete the rest, or verify "
                      "that repetition is intentional.", ids=ids, examples=ex,
                      metric={"groups": len(gs), "redundant": redundant})

    def _annotations(self) -> None:
        by_code: dict[str, list[AnnotationIssue]] = defaultdict(list)
        for iss in self.issues:
            by_code[iss.code].append(iss)
        n_imgs = max(1, sum(1 for i in self.images if i.status == "ok"))

        def issue_examples(items: list[AnnotationIssue]) -> list[dict[str, Any]]:
            out = []
            for it in items[:MAX_EXAMPLES]:
                where = f"{it.label_path}:{it.line}" if it.line else (it.label_path or "")
                raw = f" → {it.raw}" if it.raw else ""
                out.append({"image_id": it.image_id, "path": it.image_path or it.label_path or "",
                            "split": it.split or "", "detail": f"{where} {it.message}{raw}".strip()})
            return out

        def emit(code: str, sev: str, title: str, desc: str, rec: str) -> None:
            items = by_code.get(code, [])
            if not items:
                return
            ids = [it.image_id for it in items if it.image_id]
            self._add(f"annotations_{code}", sev, "annotations", f"{title} ({len(items)})",
                      desc.format(n=len(items), files=len(set(ids)) or len(items)), rec,
                      ids=ids, count=len(items), examples=issue_examples(items), metric={"issues": len(items)})

        emit("malformed_line", "high", "Malformed annotation lines",
             "{n} label lines in {files} files cannot be parsed as YOLO annotations "
             "(wrong number of fields or non-numeric values). They are excluded from all statistics.",
             "Fix or regenerate these label files; frameworks may crash or silently skip these lines.")
        emit("invalid_class_id", "high", "Invalid class ids",
             "{n} annotations reference a class id outside the range declared in data.yaml.",
             "Correct the class ids or update the class list in data.yaml.")
        emit("negative_coordinate", "high", "Negative box coordinates",
             "{n} annotations have negative centre coordinates.", "Fix the labels; boxes must be normalised to [0, 1].")
        emit("coordinate_out_of_range", "high", "Coordinates greater than 1 (not normalised)",
             "{n} annotations contain values > 1, which usually means pixel coordinates were "
             "written instead of normalised ones.", "Normalise coordinates by image width/height.")
        emit("invalid_size", "high", "Negative box width/height",
             "{n} annotations have a negative width or height.", "Fix or delete these annotations.")
        emit("zero_area", "high", "Zero-area boxes", "{n} annotations have zero width or height.",
             "Delete these annotations or fix the box extents.")
        emit("label_file_unreadable", "high", "Unreadable label files", "{n} label files could not be read.",
             "Check file permissions and encoding.")
        emit("label_file_too_large", "medium", "Oversized label files",
             "{n} label files exceed the size limit and were not parsed.", "Split or trim these files, or raise max_label_bytes.")
        emit("duplicate_annotation", "medium", "Duplicate annotations",
             "{n} boxes duplicate another box of the same class in the same image (IoU above the threshold).",
             "Remove the duplicate lines; they inflate class counts and can distort training.")
        emit("box_out_of_bounds", "low", "Boxes extending past the image",
             "{n} boxes extend beyond the image boundary.", "Clip these boxes to the image or verify the labels.")
        emit("tiny_box", "low", "Suspiciously tiny boxes",
             "{n} boxes cover a very small fraction of the image and may be annotation noise.",
             "Inspect these boxes; remove them if they are mistakes.")
        emit("large_box", "low", "Boxes covering almost the whole image",
             "{n} boxes cover most of the image.", "Verify these are intentional (e.g. close-ups) and not full-frame mistakes.")

        missing = [i for i in self.images if i.label_status == "missing" and i.status == "ok"]
        if missing:
            rate = len(missing) / n_imgs
            sev = "high" if rate >= 0.10 else "medium"
            self._add("annotations_missing_label_file", sev, "annotations",
                      f"Images without a label file ({len(missing)})",
                      f"{len(missing)} images ({rate:.1%}) have no label file. In YOLO, a missing file "
                      "is not the same as an empty one: most trainers treat it as a data error or skip the image.",
                      "Add label files (an empty file for background images) or remove the images.",
                      ids=[i.id for i in missing], examples=self._img_examples([i.id for i in missing], "no label file"),
                      metric={"rate": rate})
        empty = [i for i in self.images if i.label_status == "empty" and i.status == "ok"]
        if empty:
            rate = len(empty) / n_imgs
            self._add("annotations_empty_label_file", "low" if rate > 0.5 else "info", "annotations",
                      f"Images with empty label files ({len(empty)})",
                      f"{len(empty)} images ({rate:.1%}) have empty label files. That is valid for "
                      "background/negative images but suspicious if unintended.",
                      "Confirm these are intentional negatives.", ids=[i.id for i in empty],
                      examples=self._img_examples([i.id for i in empty], "empty label file"), metric={"rate": rate})
        orphans = by_code.get("orphan_label", [])
        if orphans:
            self._add("annotations_orphan_label", "medium", "annotations", f"Label files without an image ({len(orphans)})",
                      f"{len(orphans)} label files have no matching image.",
                      "Delete stale labels or restore the missing images.", count=len(orphans),
                      examples=issue_examples(orphans), metric={"labels": len(orphans)})

    def _class_balance(self) -> None:
        bal = self.stats["class_balance"]
        classes = self.stats["classes"]
        if not classes:
            return
        unused = bal.get("unused_classes", [])
        if unused:
            self._add("classes_unused", "medium", "class_balance", f"Declared classes with no annotations ({len(unused)})",
                      f"{len(unused)} of {len(classes)} declared classes never appear in any valid annotation: "
                      f"{', '.join(unused[:8])}.", "Remove unused classes from data.yaml or add labelled examples.",
                      count=len(unused), metric={"classes": unused})
        ratio = bal.get("imbalance_ratio")
        if ratio and ratio >= 10:
            sev = "high" if ratio >= 50 else "medium"
            counts = sorted((c for c in classes if c["count"] > 0), key=lambda c: -c["count"])
            self._add("class_imbalance", sev, "class_balance", f"Class imbalance (max/min ratio {ratio:g}×)",
                      f"'{bal['max_class']}' has {counts[0]['count']} annotations while the rarest class "
                      f"'{bal['min_class']}' has {counts[-1]['count']}. Rare classes are usually learned poorly.",
                      "Collect more examples of rare classes, resample, or use class-weighted losses.",
                      count=counts[-1]["count"], metric={"imbalance_ratio": ratio})
        tr = {c["name"] for c in classes if c["per_split"].get("train", 0) > 0}
        for split in ("val", "test"):
            if not any(s["split"] == split for s in self.stats["splits"]):
                continue
            missing = sorted(n for n in tr if not any(c["name"] == n and c["per_split"].get(split, 0) > 0 for c in classes))
            if missing:
                self._add(f"classes_missing_{split}", "medium", "class_balance",
                          f"Classes present in train but absent from {split} ({len(missing)})",
                          f"Classes {', '.join(missing[:8])} have no annotations in the {split} split, "
                          "so they cannot be evaluated.", "Rebalance the split so every class appears in every split.",
                          count=len(missing), metric={"classes": missing})

    def _quality(self) -> None:
        ok = [i for i in self.images if i.status == "ok"]
        n = max(1, len(ok))
        rules = [
            ("blurry", "Blurry images", "Laplacian variance below {t:g} (heuristic, dataset-dependent).",
             lambda r: "high" if r >= 0.20 else "medium" if r >= 0.05 else "low",
             "Review these images; remove or re-capture unusable ones. Tune quality.blur_threshold if the dataset is naturally soft."),
            ("low_resolution", "Low-resolution images", "Shorter side below {t} px.",
             lambda r: "medium" if r >= 0.10 else "low", "Upsampling cannot recover detail; consider removing them."),
            ("extreme_aspect", "Extreme aspect ratios", "Aspect ratio beyond {t:g}:1.",
             lambda r: "low", "Check that letterboxing/resizing in training handles these sensibly."),
            ("dark", "Suspiciously dark images", "Mean gray level below {t:g}/255.",
             lambda r: "medium" if r >= 0.10 else "low", "Inspect for exposure problems or black frames."),
            ("bright", "Suspiciously bright images", "Mean gray level above {t:g}/255.",
             lambda r: "medium" if r >= 0.10 else "low", "Inspect for over-exposure or blank frames."),
            ("low_contrast", "Low-contrast images", "Gray-level standard deviation below {t:g}.",
             lambda r: "low", "Inspect for flat, washed-out or blank images."),
        ]
        q = self.cfg.quality
        thresholds = {"blurry": q.blur_threshold, "low_resolution": q.min_side_px,
                      "extreme_aspect": q.max_aspect_ratio, "dark": q.dark_brightness,
                      "bright": q.bright_brightness, "low_contrast": q.low_contrast_std}
        for tag, title, expl, sev_fn, rec in rules:
            ids = self._ids_with_tag(tag)
            if not ids:
                continue
            rate = len(ids) / n
            self._add(f"quality_{tag}", sev_fn(rate), "image_quality", f"{title} ({len(ids)})",
                      f"{len(ids)} images ({rate:.1%}) flagged. " + expl.format(t=thresholds[tag]), rec,
                      ids=ids, examples=self._img_examples(ids), metric={"rate": rate, "threshold": thresholds[tag]})
        gray = [i.id for i in ok if i.is_grayscale]
        if gray and len(gray) < len(ok):
            self._add("quality_mixed_grayscale", "low", "image_quality", f"Mixed grayscale and colour images ({len(gray)})",
                      f"{len(gray)} grayscale images are mixed into a colour dataset ({len(gray) / n:.1%}).",
                      "Verify they are intentional; models may need consistent channel handling.",
                      ids=gray, examples=self._img_examples(gray), metric={"rate": len(gray) / n})
