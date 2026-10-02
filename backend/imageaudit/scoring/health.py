"""Transparent dataset health score.

overall = sum(weight_i * score_i) / sum(weight_i) over *applicable* components.
Each component score is 100 * (1 - min(1, metric / zero_at)) - a linear penalty that reaches 0
at the configured ``zero_at`` value (see docs/health-score.md). class_balance uses a log ratio.
Nothing here is learned or hidden; every input is a measured rate exposed in the output.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from ..core.config import ScoreConfig
from ..core.models import INVALID_STATUSES, ImageRecord

FORMULA_VERSION = "1"
GRADES = ((90, "A"), (80, "B"), (70, "C"), (60, "D"))

LABELS: dict[str, tuple[str, str, str]] = {
    "integrity": ("Image integrity", "Share of files that are corrupted, unsupported, empty or oversized",
                  "of files unusable"),
    "duplicates": ("Duplicates", "Redundant images inside a split (exact + near duplicates)",
                   "of images redundant"),
    "leakage": ("Split leakage", "Val/test images that also appear in another split",
                "of eval images leaked"),
    "annotation_validity": ("Annotation validity", "Label lines that fail validation",
                            "of label lines invalid"),
    "annotation_coverage": ("Annotation coverage", "Images without a label file", "of images unlabeled"),
    "class_balance": ("Class balance", "Ratio between most and least frequent class",
                      "imbalance ratio"),
    "blur": ("Sharpness", "Images below the Laplacian-variance blur threshold", "of images blurry"),
    "image_stats": ("Image statistics", "Images that are low-res, extreme aspect, dark, bright or "
                    "low contrast", "of images suspicious"),
}


def _linear(metric: float, zero_at: float) -> float:
    return round(100.0 * (1.0 - min(1.0, max(0.0, metric) / zero_at)), 2)


def _grade(score: float) -> str:
    for cut, letter in GRADES:
        if score >= cut:
            return letter
    return "F"


class HealthScorer:
    def __init__(self, cfg: ScoreConfig) -> None:
        self.cfg = cfg

    def score(self, images: Sequence[ImageRecord], *, invalid_lines: int, total_lines: int,
              has_labels: bool, class_counts: Sequence[int], leakage: dict[str, Any],
              duplicate_summary: dict[str, Any]) -> dict[str, Any]:
        n_files = len(images)
        ok = [i for i in images if i.status == "ok"]
        measured = [i for i in ok if i.blur_score is not None]
        comps: list[dict[str, Any]] = []

        def add(key: str, metric: float | None, score: float | None, detail: dict[str, Any]) -> None:
            label, description, unit = LABELS[key]
            comps.append({
                "key": key, "label": label, "description": description, "unit": unit,
                "weight": self.cfg.weights[key], "zero_at": self.cfg.zero_at[key],
                "metric": None if metric is None else round(metric, 6),
                "score": score, "applicable": score is not None, "detail": detail,
            })

        bad = sum(1 for i in images if i.status in INVALID_STATUSES or i.status == "corrupted")
        rate = bad / n_files if n_files else None
        add("integrity", rate, None if rate is None else _linear(rate, self.cfg.zero_at["integrity"]),
            {"unusable_files": bad, "files": n_files})

        # Extra copies *inside* a split. Copies across splits are scored under "leakage" instead,
        # so nothing is counted twice.
        red_within = duplicate_summary.get("redundant_within_split", 0)
        rate = red_within / len(ok) if ok and not duplicate_summary.get("skipped") else None
        add("duplicates", rate, None if rate is None else _linear(rate, self.cfg.zero_at["duplicates"]),
            {"redundant_images": red_within, "valid_images": len(ok)})

        lrate = leakage.get("leakage_rate")
        applicable = leakage.get("applicable", False) and lrate is not None
        add("leakage", lrate if applicable else None,
            _linear(lrate, self.cfg.zero_at["leakage"]) if applicable else None,
            {"leaked_images": leakage.get("leaked_images", 0), "eval_images": leakage.get("eval_images", 0)})

        if has_labels and total_lines > 0:
            rate = invalid_lines / total_lines
            add("annotation_validity", rate, _linear(rate, self.cfg.zero_at["annotation_validity"]),
                {"invalid_lines": invalid_lines, "total_lines": total_lines})
        else:
            add("annotation_validity", None, None, {"invalid_lines": invalid_lines, "total_lines": total_lines})

        if has_labels and ok:
            missing = sum(1 for i in ok if i.label_status == "missing")
            rate = missing / len(ok)
            add("annotation_coverage", rate, _linear(rate, self.cfg.zero_at["annotation_coverage"]),
                {"missing_label_files": missing, "valid_images": len(ok)})
        else:
            add("annotation_coverage", None, None, {})

        counts = [c for c in class_counts if c > 0]  # unused classes are a separate finding
        if len(counts) >= 2:
            ratio = max(counts) / min(counts)
            score = 100.0 * (1.0 - min(1.0, math.log(ratio) / math.log(self.cfg.zero_at["class_balance"])))
            add("class_balance", ratio, round(max(0.0, score), 2),
                {"max_count": max(counts), "min_count": min(counts), "classes": len(counts)})
        else:
            add("class_balance", None, None, {"classes": len(counts)})

        if measured:
            blurry = sum(1 for i in measured if "blurry" in i.tags)
            rate = blurry / len(measured)
            add("blur", rate, _linear(rate, self.cfg.zero_at["blur"]),
                {"blurry_images": blurry, "measured_images": len(measured)})
        else:
            add("blur", None, None, {})

        if ok:
            flagged = {"low_resolution", "extreme_aspect", "dark", "bright", "low_contrast"}
            sus = sum(1 for i in ok if flagged.intersection(i.tags))
            rate = sus / len(ok)
            add("image_stats", rate, _linear(rate, self.cfg.zero_at["image_stats"]),
                {"suspicious_images": sus, "valid_images": len(ok)})
        else:
            add("image_stats", None, None, {})

        active = [c for c in comps if c["applicable"] and c["weight"] > 0]
        wsum = sum(c["weight"] for c in active)
        overall = round(sum(c["weight"] * c["score"] for c in active) / wsum, 1) if wsum else None
        for c in comps:
            c["effective_weight"] = round(c["weight"] / wsum, 4) if (c in active and wsum) else 0.0
        return {"overall": overall, "grade": _grade(overall) if overall is not None else None,
                "components": comps, "formula_version": FORMULA_VERSION}
