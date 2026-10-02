"""YOLO label validation. Never silently drops a line: every rejected line yields an issue."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..core.config import AnnotationConfig
from ..core.models import ISSUE_LEVELS, AnnotationIssue, Box

_INT_RE = re.compile(r"^[+-]?\d+$")
_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_RAW_LIMIT = 200


@dataclass
class ParsedAnnotations:
    status: str  # ok | missing | empty
    boxes: list[Box] = field(default_factory=list)
    issues: list[AnnotationIssue] = field(default_factory=list)
    total_lines: int = 0  # non-blank lines
    invalid_lines: int = 0  # lines with at least one error-level issue


class YoloAnnotationAnalyzer:
    """Parses and validates YOLO detection (``cls cx cy w h``) and segmentation lines.

    Segmentation polygons (``cls x1 y1 x2 y2 ...``) are reduced to their bounding box so the
    dataset can still be audited; the box carries a ``polygon`` flag.
    """

    def __init__(self, cfg: AnnotationConfig, class_count: int | None) -> None:
        self.cfg = cfg
        self.class_count = class_count

    def analyze_file(self, path: Path | None, rel_label: str | None) -> ParsedAnnotations:
        if path is None or not path.is_file():
            return ParsedAnnotations(status="missing")
        try:
            size = path.stat().st_size
            if size > self.cfg.max_label_bytes:
                return self._file_error(rel_label, "label_file_too_large",
                                        f"Label file is {size} bytes (limit {self.cfg.max_label_bytes})")
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
        except OSError as exc:
            return self._file_error(rel_label, "label_file_unreadable", f"Cannot read label file: {exc}")
        return self.parse_text(text, rel_label)

    def _file_error(self, rel: str | None, code: str, msg: str) -> ParsedAnnotations:
        return ParsedAnnotations(status="ok", issues=[AnnotationIssue(code=code, message=msg, label_path=rel)],
                                 total_lines=1, invalid_lines=1)

    def parse_text(self, text: str, rel_label: str | None = None) -> ParsedAnnotations:
        out = ParsedAnnotations(status="ok")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            out.total_lines += 1
            codes: list[tuple[str, str]] = []
            box = self._parse_line(stripped, codes)
            errors = [c for c in codes if ISSUE_LEVELS[c[0]] == "error"]
            for code, msg in codes:
                out.issues.append(AnnotationIssue(code=code, message=msg, label_path=rel_label,
                                                  line=lineno, raw=stripped[:_RAW_LIMIT]))
            if errors:
                out.invalid_lines += 1
            elif box is not None:
                box.line = lineno
                out.boxes.append(box)
        if out.total_lines == 0:
            out.status = "empty"
            out.issues.append(AnnotationIssue(code="empty_label_file", label_path=rel_label,
                                              message="Label file has no annotations (background image?)"))
        self._flag_duplicates(out, rel_label)
        return out

    # --------------------------------------------------------------------- lines
    def _parse_line(self, line: str, codes: list[tuple[str, str]]) -> Box | None:
        tok = line.split()
        n = len(tok)
        polygon = n >= 7 and (n - 1) % 2 == 0
        if n != 5 and not polygon:
            codes.append(("malformed_line", f"Expected 5 values (class cx cy w h) or a polygon, found {n}"))
            return None
        if not _INT_RE.match(tok[0]):
            codes.append(("malformed_line", f"Class id '{tok[0][:20]}' is not an integer"))
            return None
        bad = [t for t in tok[1:] if not _NUM_RE.match(t)]
        if bad:
            codes.append(("malformed_line", f"Non-numeric coordinate '{bad[0][:20]}'"))
            return None
        vals = [float(t) for t in tok[1:]]
        if not all(math.isfinite(v) for v in vals):
            codes.append(("malformed_line", "Coordinate is not a finite number"))
            return None
        cls = int(tok[0])
        if cls < 0 or (self.class_count is not None and cls >= self.class_count):
            limit = f" (dataset declares {self.class_count} classes)" if self.class_count is not None else ""
            codes.append(("invalid_class_id", f"Class id {cls} is out of range{limit}"))

        if polygon:
            xs, ys = vals[0::2], vals[1::2]
            if min(vals) < 0:
                codes.append(("negative_coordinate", "Polygon has a negative coordinate"))
            if max(vals) > 1:
                codes.append(("coordinate_out_of_range", "Polygon has a coordinate greater than 1"))
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
            flags = ["polygon"]
            if w == 0 or h == 0:
                codes.append(("zero_area", "Polygon has zero-area bounding box"))
        else:
            cx, cy, w, h = vals
            flags = []
            if cx < 0 or cy < 0:
                codes.append(("negative_coordinate", f"Negative centre coordinate (cx={cx:g}, cy={cy:g})"))
            if max(cx, cy, w, h) > 1:
                codes.append(("coordinate_out_of_range", "A value is greater than 1 (not normalised?)"))
            if w < 0 or h < 0:
                codes.append(("invalid_size", f"Negative width/height (w={w:g}, h={h:g})"))
            elif w == 0 or h == 0:
                codes.append(("zero_area", f"Zero-area box (w={w:g}, h={h:g})"))

        if any(ISSUE_LEVELS[c] == "error" for c, _ in codes):
            return None
        tol = self.cfg.bounds_tolerance
        if cx - w / 2 < -tol or cy - h / 2 < -tol or cx + w / 2 > 1 + tol or cy + h / 2 > 1 + tol:
            codes.append(("box_out_of_bounds", "Box extends beyond the image boundary"))
            flags.append("out_of_bounds")
        area = w * h
        if area < self.cfg.tiny_box_area:
            codes.append(("tiny_box", f"Suspiciously tiny box (area {area:.2e} of image)"))
            flags.append("tiny")
        if area > self.cfg.large_box_area:
            codes.append(("large_box", f"Box covers {area:.0%} of the image"))
            flags.append("large")
        return Box(class_id=cls, cx=cx, cy=cy, w=w, h=h, flags=flags)

    # ---------------------------------------------------------------- duplicates
    def _flag_duplicates(self, out: ParsedAnnotations, rel_label: str | None) -> None:
        boxes = out.boxes
        n = len(boxes)
        if n < 2 or n > self.cfg.max_boxes_for_duplicate_check:
            return
        a = np.array([[b.cx - b.w / 2, b.cy - b.h / 2, b.cx + b.w / 2, b.cy + b.h / 2] for b in boxes])
        cls = np.array([b.class_id for b in boxes])
        area = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
        iw = np.clip(np.minimum(a[:, None, 2], a[None, :, 2]) - np.maximum(a[:, None, 0], a[None, :, 0]), 0, None)
        ih = np.clip(np.minimum(a[:, None, 3], a[None, :, 3]) - np.maximum(a[:, None, 1], a[None, :, 1]), 0, None)
        inter = iw * ih
        union = area[:, None] + area[None, :] - inter
        iou = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
        same = cls[:, None] == cls[None, :]
        hit = np.tril((iou >= self.cfg.duplicate_iou) & same, k=-1)
        for j in range(n):
            earlier = np.flatnonzero(hit[j])
            if earlier.size:
                i = int(earlier[0])
                boxes[j].flags.append("duplicate")
                out.issues.append(AnnotationIssue(
                    code="duplicate_annotation", label_path=rel_label, line=boxes[j].line,
                    message=f"Duplicates the box on line {boxes[i].line} (IoU {iou[j, i]:.2f})"))
