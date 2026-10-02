"""Turns raw measurements into quality flags using the configured (heuristic) thresholds."""

from __future__ import annotations

from ..core.config import QualityConfig
from ..core.models import ImageMeasurements

QUALITY_FLAGS = ("blurry", "low_resolution", "extreme_aspect", "dark", "bright", "low_contrast")


def quality_flags(m: ImageMeasurements, q: QualityConfig) -> list[str]:
    if m.status != "ok" or not m.width or not m.height:
        return []
    flags: list[str] = []
    if min(m.width, m.height) < q.min_side_px:
        flags.append("low_resolution")
    if max(m.width / m.height, m.height / m.width) > q.max_aspect_ratio:
        flags.append("extreme_aspect")
    if m.blur_score is not None and m.blur_score < q.blur_threshold:
        flags.append("blurry")
    if m.brightness is not None:
        if m.brightness < q.dark_brightness:
            flags.append("dark")
        elif m.brightness > q.bright_brightness:
            flags.append("bright")
    if m.contrast is not None and m.contrast < q.low_contrast_std:
        flags.append("low_contrast")
    return flags
