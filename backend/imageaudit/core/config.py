"""Configuration: dataclass defaults, YAML loading, environment overrides.

Unknown keys are rejected so typos in ``imageaudit.yaml`` fail loudly instead of being ignored.
All thresholds are heuristics; see docs/health-score.md and README "Limitations".
"""

from __future__ import annotations

import dataclasses
import os
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

SEVERITIES = ("critical", "high", "medium", "low", "info")
CONFIG_FILENAMES = ("imageaudit.yaml", "imageaudit.yml")


@dataclass
class QualityConfig:
    blur_threshold: float = 100.0  # Laplacian variance below this => "blurry" (heuristic)
    min_side_px: int = 64  # shorter side below this => low resolution
    max_aspect_ratio: float = 4.0  # max(w/h, h/w) above this => extreme aspect ratio
    dark_brightness: float = 35.0  # mean gray level (0-255) below this => dark
    bright_brightness: float = 220.0  # mean gray level above this => bright
    low_contrast_std: float = 20.0  # gray-level std below this => low contrast
    analysis_max_side: int = 1024  # pixel statistics/hashes are computed at <= this longest side


@dataclass
class AnnotationConfig:
    tiny_box_area: float = 0.0004  # normalised w*h below this => tiny box
    large_box_area: float = 0.95  # normalised w*h above this => suspiciously large box
    bounds_tolerance: float = 0.005  # tolerated overhang past the image edge (normalised)
    duplicate_iou: float = 0.95  # same-class boxes with IoU >= this => duplicate annotation
    max_boxes_for_duplicate_check: int = 2000  # skip the O(n^2) check above this per image
    max_label_bytes: int = 16 * 1024 * 1024


@dataclass
class DuplicateConfig:
    enabled: bool = True
    phash_max_distance: int = 6  # max Hamming distance (of 64 bits) between pHashes
    dhash_max_distance: int = 10  # confirmation distance between dHashes
    min_hash_std: float = 2.0  # near-flat images are excluded from perceptual matching


@dataclass
class ScoreConfig:
    """Weights and 'zero-at' points for the health score (see docs/health-score.md)."""

    weights: dict[str, float] = field(default_factory=lambda: {
        "integrity": 20.0, "leakage": 20.0, "annotation_validity": 20.0, "duplicates": 10.0,
        "annotation_coverage": 10.0, "class_balance": 10.0, "blur": 5.0, "image_stats": 5.0,
    })
    # Rate at which a component reaches 0. class_balance is the max/min class-count ratio.
    zero_at: dict[str, float] = field(default_factory=lambda: {
        "integrity": 0.05, "leakage": 0.05, "annotation_validity": 0.05, "duplicates": 0.20,
        "annotation_coverage": 0.25, "class_balance": 100.0, "blur": 0.30, "image_stats": 0.30,
    })


@dataclass
class CIConfig:
    """Thresholds used by ``imageaudit validate``. ``None`` disables a check."""

    fail_on: str | None = "high"  # fail if any finding at or above this severity exists
    fail_under: float | None = None  # fail if the health score is below this
    max_corrupt_rate: float | None = None
    max_leakage_rate: float | None = None
    max_invalid_annotation_rate: float | None = None
    max_duplicate_rate: float | None = None
    max_blur_rate: float | None = None


@dataclass
class AuditConfig:
    quality: QualityConfig = field(default_factory=QualityConfig)
    annotations: AnnotationConfig = field(default_factory=AnnotationConfig)
    duplicates: DuplicateConfig = field(default_factory=DuplicateConfig)
    scoring: ScoreConfig = field(default_factory=ScoreConfig)
    ci: CIConfig = field(default_factory=CIConfig)
    workers: int = 0  # 0 = auto (min(8, cpu_count))
    use_cache: bool = True
    max_file_bytes: int = 512 * 1024 * 1024
    max_pixels: int = 178_000_000  # decompression-bomb guard (~Pillow's hard limit)

    def effective_workers(self) -> int:
        return self.workers if self.workers > 0 else max(1, min(8, os.cpu_count() or 2))

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def validate(self) -> AuditConfig:
        if self.ci.fail_on not in (None, *SEVERITIES[:-1]):
            raise ConfigError(f"ci.fail_on must be one of {SEVERITIES[:-1]} or null")
        if self.workers < 0:
            raise ConfigError("workers must be >= 0")
        w, z = self.scoring.weights, self.scoring.zero_at
        if any(v < 0 for v in w.values()) or sum(w.values()) <= 0:
            raise ConfigError("scoring.weights must be non-negative with a positive sum")
        if any(v <= 0 for v in z.values()) or z.get("class_balance", 2.0) <= 1.0:
            raise ConfigError("scoring.zero_at values must be > 0 (class_balance > 1)")
        if not 0 <= self.duplicates.phash_max_distance <= 7:
            # the multi-index search splits the hash into 8 chunks: exhaustive only up to distance 7
            raise ConfigError("duplicates.phash_max_distance must be in [0, 7]")
        if self.quality.analysis_max_side < 64:
            raise ConfigError("quality.analysis_max_side must be >= 64")
        return self


_DICT_FIELDS = ("weights", "zero_at")


def _merge(base: dict[str, Any], override: dict[str, Any], path: str = "") -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        where = f"{path}{key}"
        if key not in base:
            raise ConfigError(f"Unknown config key '{where}'. Valid keys here: {sorted(base)}")
        if key in _DICT_FIELDS:
            if not isinstance(value, dict):
                raise ConfigError(f"Config key '{where}' must be a mapping")
            unknown = set(value) - set(base[key])
            if unknown:
                raise ConfigError(f"Unknown keys in '{where}': {sorted(unknown)}")
            out[key] = {**base[key], **value}
        elif isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ConfigError(f"Config key '{where}' must be a mapping")
            out[key] = _merge(base[key], value, where + ".")
        else:
            out[key] = value
    return out


def _build(cls: Any, data: dict[str, Any]) -> Any:
    hints = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        tp, value = hints[f.name], data[f.name]
        if dataclasses.is_dataclass(tp):
            kwargs[f.name] = _build(tp, value)
        else:
            kwargs[f.name] = _coerce(tp, value, f.name)
    return cls(**kwargs)


def _coerce(tp: Any, value: Any, name: str) -> Any:
    args = [a for a in typing.get_args(tp) if a is not type(None)]
    is_union = typing.get_origin(tp) in (typing.Union, types.UnionType)
    target = args[0] if is_union and len(args) == 1 else tp
    if value is None:
        return None
    try:
        if target is bool:
            if not isinstance(value, bool):
                raise TypeError
            return value
        if target in (int, float):
            if isinstance(value, bool):
                raise TypeError
            return target(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Config key '{name}' must be {target.__name__}, got {value!r}") from exc
    return value


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> AuditConfig:
    """Defaults <- YAML file <- overrides <- IMAGEAUDIT_WORKERS / IMAGEAUDIT_NO_CACHE."""
    data = AuditConfig().to_dict()
    if path is not None:
        p = Path(path)
        try:
            loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except OSError as exc:
            raise ConfigError(f"Cannot read config file {p}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {p}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"Config file {p} must contain a mapping at the top level")
        data = _merge(data, loaded)
    if overrides:
        data = _merge(data, overrides)
    if env := os.environ.get("IMAGEAUDIT_WORKERS"):
        try:
            data["workers"] = max(0, int(env))
        except ValueError as exc:
            raise ConfigError("IMAGEAUDIT_WORKERS must be an integer") from exc
    if os.environ.get("IMAGEAUDIT_NO_CACHE", "").lower() in ("1", "true", "yes"):
        data["use_cache"] = False
    return _build(AuditConfig, data).validate()


def find_config(dataset_root: Path) -> Path | None:
    for name in CONFIG_FILENAMES:
        candidate = dataset_root / name
        if candidate.is_file():
            return candidate
    return None
