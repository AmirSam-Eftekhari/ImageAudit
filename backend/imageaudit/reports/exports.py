"""Machine-readable exports: JSON and CSV."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from ..core.models import AuditResult

CSV_KINDS = ("images", "findings", "issues", "duplicates")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: Any) -> Any:
    """Neutralise spreadsheet formula injection from attacker-controlled file names/labels."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def report_dict(result: AuditResult, include_images: bool = False) -> dict[str, Any]:
    data = result.to_dict()
    if not include_images:
        data.pop("images")
    return data


def json_report(result: AuditResult, include_images: bool = False) -> bytes:
    return json.dumps(report_dict(result, include_images), indent=2, ensure_ascii=False).encode("utf-8")


def _class_name(result: AuditResult, cid: int) -> str:
    names = result.dataset.class_names
    return names[cid] if 0 <= cid < len(names) else f"class_{cid}"


def csv_frame(result: AuditResult, kind: str = "images") -> pd.DataFrame:
    if kind == "images":
        rows = [{
            "id": i.id, "path": i.path, "split": i.split, "status": i.status, "error": i.error,
            "format": i.format, "width": i.width, "height": i.height, "channels": i.channels,
            "file_size": i.file_size, "aspect_ratio": i.aspect_ratio, "grayscale": i.is_grayscale,
            "brightness": None if i.brightness is None else round(i.brightness, 2),
            "contrast": None if i.contrast is None else round(i.contrast, 2),
            "blur_score": None if i.blur_score is None else round(i.blur_score, 2),
            "sha256": i.sha256, "phash": i.phash, "dhash": i.dhash, "label_status": i.label_status,
            "annotations": len(i.boxes), "invalid_annotation_lines": i.invalid_annotation_count,
            "classes": ";".join(sorted({_class_name(result, b.class_id) for b in i.boxes})),
            "tags": ";".join(i.tags),
        } for i in result.images]
    elif kind == "findings":
        rows = [{"severity": f.severity, "category": f.category, "title": f.title,
                 "affected_count": f.affected_count, "description": f.description,
                 "recommendation": f.recommendation, "splits": ";".join(f.splits),
                 "classes": ";".join(f.classes)} for f in result.findings]
    elif kind == "issues":
        rows = [{"code": i.code, "level": i.level, "split": i.split, "image_path": i.image_path,
                 "label_path": i.label_path, "line": i.line, "message": i.message, "raw": i.raw}
                for i in result.issues]
    elif kind == "duplicates":
        rows = [{"group_id": g.id, "kind": g.kind, "scope": g.scope, "splits": ";".join(g.splits),
                 "max_phash_distance": g.max_distance, "member_path": m.path, "member_split": m.split,
                 "member_sha256": m.sha256} for g in result.duplicates for m in g.members]
    else:
        raise ValueError(f"Unknown CSV kind '{kind}'. Choose from {CSV_KINDS}")
    df = pd.DataFrame(rows)
    for col in ("width", "height", "channels", "line"):
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_safe_cell)
    return df


def csv_report(result: AuditResult, kind: str = "images") -> bytes:
    return csv_frame(result, kind).to_csv(index=False).encode("utf-8")
