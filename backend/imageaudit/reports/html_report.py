"""Self-contained HTML report (inline CSS, inline SVG, embedded thumbnails)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from jinja2 import Environment, PackageLoader, select_autoescape

from ..core.models import AuditResult
from .svg import bar_chart, score_ring

_env = Environment(loader=PackageLoader("imageaudit.reports", "templates"),
                   autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)
MAX_GROUPS = 12
THUMB = 104


def _thumb(path: Path) -> str | None:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_REDUCED_COLOR_4)
        if img is None:
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        s = THUMB * 2 / max(h, w)
        if s < 1:
            img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode() if ok else None
    except Exception:
        return None


def html_report(result: AuditResult, *, embed_thumbnails: bool = True) -> bytes:
    stats, d = result.statistics, result.dataset
    t = stats["totals"]
    groups = result.duplicates[:MAX_GROUPS]
    thumbs: dict[str, str] = {}
    if embed_thumbnails:
        root = Path(d.root)
        for g in groups:
            for m in g.members[:6]:
                data = _thumb(root / m.path)
                if data:
                    thumbs[m.image_id] = data
    ctx: dict[str, Any] = {
        "r": result, "d": d, "stats": stats, "h": result.health, "lk": result.leakage,
        "ring": score_ring(result.health.get("overall")),
        "kpis": [("images", t["images_total"]), ("valid images", t["images_valid"]),
                 ("invalid images", t["images_invalid"]), ("annotations", t["annotations_total"]),
                 ("annotated images", t["annotated_images"]), ("empty-label images", t["empty_label_images"]),
                 ("classes used / declared", f"{t['classes_used']} / {t['classes_declared']}"),
                 ("annotations / image", t["annotations_per_image"])],
        "class_chart": bar_chart([{"label": c["name"], "count": c["count"]} for c in stats["classes"]]),
        "res_chart": bar_chart(stats["resolution"]["top"], color="#3b82f6"),
        "aspect_chart": bar_chart(stats["aspect_ratio"]["histogram"], color="#3b82f6"),
        "density_chart": bar_chart(stats["annotation_density"]["histogram"]),
        "box_chart": bar_chart(stats["box_size"]["histogram"]),
        "blur_chart": bar_chart(stats["quality"]["blur"]["histogram"]),
        "bright_chart": bar_chart(stats["quality"]["brightness"]["histogram"], color="#3b82f6"),
        "issue_rows": sorted(((c, _level(c), n) for c, n in stats["issue_counts"].items()), key=lambda x: -x[2]),
        "groups": groups, "thumbs": thumbs,
    }
    return _env.get_template("report.html.j2").render(**ctx).encode("utf-8")


def _level(code: str) -> str:
    from ..core.models import ISSUE_LEVELS
    return ISSUE_LEVELS.get(code, "warning")
