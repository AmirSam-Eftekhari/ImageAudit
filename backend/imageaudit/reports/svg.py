"""Tiny dependency-free SVG helpers used by the self-contained HTML report."""

from __future__ import annotations

from html import escape
from typing import Any

ACCENT = "#22d3ee"


def bar_chart(items: list[dict[str, Any]], *, width: int = 520, bar_h: int = 18, gap: int = 6,
              label_w: int = 110, color: str = ACCENT, max_items: int = 14) -> str:
    items = items[:max_items]
    if not items:
        return '<p class="muted">No data.</p>'
    top = max((i["count"] for i in items), default=0) or 1
    h = len(items) * (bar_h + gap) + 4
    plot_w = width - label_w - 60
    rows = []
    for n, it in enumerate(items):
        y = n * (bar_h + gap) + 2
        w = max(1.0, plot_w * it["count"] / top) if it["count"] else 0
        rows.append(
            f'<text x="{label_w - 8}" y="{y + bar_h - 5}" text-anchor="end" class="lab">{escape(str(it["label"]))[:18]}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="3" fill="{color}" opacity="0.85"/>'
            f'<text x="{label_w + w + 6:.1f}" y="{y + bar_h - 5}" class="val">{it["count"]}</text>')
    return (f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg">'
            + "".join(rows) + "</svg>")


def score_ring(score: float | None, size: int = 150) -> str:
    r = size / 2 - 10
    circ = 2 * 3.14159265 * r
    pct = 0 if score is None else max(0, min(100, score)) / 100
    color = "#34d399" if pct >= 0.8 else "#facc15" if pct >= 0.6 else "#fb923c" if pct >= 0.4 else "#f87171"
    text = "n/a" if score is None else f"{score:.0f}"
    c = size / 2
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
            f'aria-label="Health score {text}" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="#1e293b" stroke-width="10"/>'
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round" '
            f'stroke-dasharray="{circ * pct:.1f} {circ:.1f}" transform="rotate(-90 {c} {c})"/>'
            f'<text x="{c}" y="{c + 10}" text-anchor="middle" font-size="34" font-weight="600" fill="#e2e8f0">{text}</text></svg>')
