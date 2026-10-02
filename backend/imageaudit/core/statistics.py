"""Dataset statistics. Every number the UI or a report shows comes from here."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from ..datasets.base import SPLIT_PRIORITY
from .models import INVALID_STATUSES, AnnotationIssue, DatasetInfo, ImageRecord

ASPECT_EDGES = [0, 0.5, 0.75, 0.95, 1.05, 1.34, 1.6, 2.0, 3.0, math.inf]
ASPECT_LABELS = ["<0.5", "0.5-0.75", "0.75-0.95", "≈1:1", "1.05-1.34", "1.34-1.6", "1.6-2", "2-3", ">3"]
BLUR_EDGES = [0, 25, 50, 100, 200, 500, 1000, math.inf]
BLUR_LABELS = ["<25", "25-50", "50-100", "100-200", "200-500", "500-1k", ">1k"]
BRIGHT_EDGES = [0, 32, 64, 96, 128, 160, 192, 224, 256.001]
BRIGHT_LABELS = ["0-32", "32-64", "64-96", "96-128", "128-160", "160-192", "192-224", "224-255"]
CONTRAST_EDGES = [0, 16, 32, 48, 64, 80, 96, 128, math.inf]
CONTRAST_LABELS = ["<16", "16-32", "32-48", "48-64", "64-80", "80-96", "96-128", ">128"]
MP_EDGES = [0, 0.1, 0.3, 0.5, 1, 2, 4, 8, math.inf]
MP_LABELS = ["<0.1", "0.1-0.3", "0.3-0.5", "0.5-1", "1-2", "2-4", "4-8", ">8"]
DENSITY_EDGES = [0, 1, 2, 3, 6, 11, 21, math.inf]
DENSITY_LABELS = ["0", "1", "2", "3-5", "6-10", "11-20", "21+"]
BOX_AREA_EDGES = [0, 1e-4, 1e-3, 1e-2, 0.05, 0.1, 0.25, 0.5, 1.0001]
BOX_AREA_LABELS = ["<0.01%", "0.01-0.1%", "0.1-1%", "1-5%", "5-10%", "10-25%", "25-50%", ">50%"]


def histogram(values: Sequence[float], edges: list[float], labels: list[str]) -> list[dict[str, Any]]:
    counts = np.zeros(len(labels), dtype=int)
    if len(values):
        idx = np.searchsorted(np.asarray(edges[1:-1], dtype=float), np.asarray(values, dtype=float), side="right")
        counts = np.bincount(idx, minlength=len(labels))[: len(labels)]
    return [{"label": lab, "count": int(c)} for lab, c in zip(labels, counts, strict=True)]


def _describe(values: Sequence[float]) -> dict[str, float | None]:
    if not len(values):
        return {"min": None, "max": None, "mean": None, "median": None}
    a = np.asarray(values, dtype=float)
    return {"min": float(a.min()), "max": float(a.max()), "mean": round(float(a.mean()), 3),
            "median": float(np.median(a))}


def compute_statistics(images: Sequence[ImageRecord], issues: Sequence[AnnotationIssue],
                       info: DatasetInfo, *, total_lines: int, invalid_lines: int,
                       orphan_labels: int, duplicate_summary: dict[str, Any]) -> dict[str, Any]:
    ok = [i for i in images if i.status == "ok"]
    status_counts = Counter(i.status for i in images)
    boxes_total = sum(len(i.boxes) for i in images)
    split_order = sorted({i.split for i in images}, key=lambda s: (SPLIT_PRIORITY.get(s, 9), s))

    df = pd.DataFrame({
        "split": [i.split for i in images], "status": [i.status for i in images],
        "boxes": [len(i.boxes) for i in images], "label_status": [i.label_status for i in images],
    })
    splits = []
    for s in split_order:
        sub = df[df["split"] == s]
        splits.append({
            "split": s, "images": int(len(sub)), "valid": int((sub["status"] == "ok").sum()),
            "invalid": int((sub["status"] != "ok").sum()), "annotations": int(sub["boxes"].sum()),
            "annotated_images": int((sub["boxes"] > 0).sum()),
            "missing_labels": int((sub["label_status"] == "missing").sum()),
            "empty_labels": int((sub["label_status"] == "empty").sum()),
        })

    # --- classes ------------------------------------------------------------------
    counts: Counter[int] = Counter()
    img_counts: Counter[int] = Counter()
    per_split: dict[int, Counter[str]] = defaultdict(Counter)
    for img in images:
        seen: set[int] = set()
        for b in img.boxes:
            counts[b.class_id] += 1
            per_split[b.class_id][img.split] += 1
            seen.add(b.class_id)
        img_counts.update(seen)
    declared = len(info.class_names)
    class_ids = sorted(set(range(declared)) | set(counts))
    classes = []
    for cid in class_ids:
        name = info.class_names[cid] if cid < declared else f"class_{cid}"
        classes.append({"class_id": cid, "name": name, "count": counts.get(cid, 0),
                        "share": (counts.get(cid, 0) / boxes_total) if boxes_total else 0.0,
                        "images": img_counts.get(cid, 0), "per_split": dict(per_split.get(cid, {}))})
    cvals = [c["count"] for c in classes]
    balance: dict[str, Any] = {"classes": len(classes), "unused_classes": [c["name"] for c in classes if c["count"] == 0]}
    used = [c for c in classes if c["count"] > 0]  # unused classes are reported separately
    if len(cvals) >= 2 and len(used) >= 2:
        p = np.asarray(cvals, dtype=float) / sum(cvals)
        nz = p[p > 0]
        entropy = float(-(nz * np.log(nz)).sum())
        balance.update(imbalance_ratio=round(max(c["count"] for c in used) / min(c["count"] for c in used), 2),
                       evenness=round(entropy / math.log(len(cvals)), 4),
                       max_class=max(used, key=lambda c: c["count"])["name"],
                       min_class=min(used, key=lambda c: c["count"])["name"])
    else:
        balance.update(imbalance_ratio=None, evenness=None, max_class=None, min_class=None)

    # --- image-level distributions -------------------------------------------------
    widths = [i.width for i in ok if i.width]
    heights = [i.height for i in ok if i.height]
    res_counter = Counter(f"{i.width}x{i.height}" for i in ok if i.width and i.height)
    aspect = [i.width / i.height for i in ok if i.width and i.height]
    megapixels = [(i.width * i.height) / 1e6 for i in ok if i.width and i.height]
    density = [len(i.boxes) for i in images if i.status == "ok" and i.label_status != "missing"]
    box_areas = [b.w * b.h for i in images for b in i.boxes]
    blur = [i.blur_score for i in ok if i.blur_score is not None]
    bright = [i.brightness for i in ok if i.brightness is not None]
    contrast = [i.contrast for i in ok if i.contrast is not None]
    n_annotated = sum(1 for i in images if i.boxes)
    sizes = [i.file_size for i in images if i.file_size]

    issue_counts = Counter(i.code for i in issues)
    tag_counts = Counter(t for i in images for t in i.tags)

    return {
        "totals": {
            "images_total": len(images), "images_valid": len(ok), "images_invalid": len(images) - len(ok),
            "status_counts": dict(status_counts),
            "invalid_by_status": {s: status_counts.get(s, 0) for s in INVALID_STATUSES},
            "annotations_total": boxes_total, "annotation_lines_total": total_lines,
            "annotation_lines_invalid": invalid_lines, "annotated_images": n_annotated,
            "empty_label_images": sum(1 for i in images if i.label_status == "empty"),
            "missing_label_images": sum(1 for i in images if i.label_status == "missing"),
            "orphan_labels": orphan_labels, "classes_declared": declared,
            "classes_used": sum(1 for c in cvals if c > 0),
            "annotations_per_image": round(boxes_total / len(ok), 3) if ok else 0.0,
            "total_bytes": int(sum(sizes)),
        },
        "splits": splits,
        "classes": classes,
        "class_balance": balance,
        "resolution": {
            "top": [{"label": k, "count": v} for k, v in res_counter.most_common(12)],
            "unique": len(res_counter), "megapixels": histogram(megapixels, MP_EDGES, MP_LABELS),
            "width": _describe(widths), "height": _describe(heights),
        },
        "aspect_ratio": {"histogram": histogram(aspect, ASPECT_EDGES, ASPECT_LABELS), **_describe(aspect)},
        "annotation_density": {"histogram": histogram(density, DENSITY_EDGES, DENSITY_LABELS),
                               **_describe(density)},
        "box_size": {"histogram": histogram(box_areas, BOX_AREA_EDGES, BOX_AREA_LABELS)},
        "quality": {
            "blur": {"histogram": histogram(blur, BLUR_EDGES, BLUR_LABELS), **_describe(blur)},
            "brightness": {"histogram": histogram(bright, BRIGHT_EDGES, BRIGHT_LABELS), **_describe(bright)},
            "contrast": {"histogram": histogram(contrast, CONTRAST_EDGES, CONTRAST_LABELS), **_describe(contrast)},
            "flag_counts": {k: tag_counts.get(k, 0) for k in
                            ("blurry", "low_resolution", "extreme_aspect", "dark", "bright", "low_contrast")},
        },
        "formats": dict(Counter(i.format or "unknown" for i in ok)),
        "channels": dict(Counter(str(i.channels) for i in ok if i.channels)),
        "grayscale_images": sum(1 for i in ok if i.is_grayscale),
        "issue_counts": dict(issue_counts),
        "tag_counts": dict(tag_counts),
        "duplicates": duplicate_summary,
    }
