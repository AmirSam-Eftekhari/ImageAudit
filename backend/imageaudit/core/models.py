"""Plain dataclasses describing audit inputs and outputs.

Everything here is JSON-serialisable via ``to_dict`` / ``from_dict`` so results can be stored,
reported, and served by the API without a second schema layer.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

# Image statuses. Anything other than "ok" means pixel analysis was not possible.
STATUS_OK = "ok"
INVALID_STATUSES = ("corrupted", "unsupported", "zero_byte", "too_large")

# Annotation issue codes -> level. "error" issues invalidate the annotation line.
ISSUE_LEVELS: dict[str, str] = {
    "malformed_line": "error",
    "invalid_class_id": "error",
    "negative_coordinate": "error",
    "coordinate_out_of_range": "error",
    "invalid_size": "error",
    "zero_area": "error",
    "label_file_unreadable": "error",
    "label_file_too_large": "error",
    "box_out_of_bounds": "warning",
    "duplicate_annotation": "warning",
    "tiny_box": "warning",
    "large_box": "warning",
    "missing_label_file": "warning",
    "orphan_label": "warning",
    "empty_label_file": "info",
}


@dataclass
class ImageMeasurements:
    """Raw, threshold-free facts about one file. This is what the analysis cache stores."""

    status: str = STATUS_OK
    error: str | None = None
    file_size: int = 0
    format: str | None = None
    mode: str | None = None
    width: int | None = None
    height: int | None = None
    channels: int | None = None
    is_grayscale: bool = False
    sha256: str | None = None
    phash: str | None = None
    dhash: str | None = None
    hash_reliable: bool = False
    blur_score: float | None = None
    brightness: float | None = None
    contrast: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ImageMeasurements:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Box:
    """A validated bounding box in normalised YOLO coordinates (centre x/y, width, height)."""

    class_id: int
    cx: float
    cy: float
    w: float
    h: float
    line: int = 0
    flags: list[str] = field(default_factory=list)  # tiny, large, out_of_bounds, duplicate, polygon

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass
class AnnotationIssue:
    code: str
    message: str
    label_path: str | None = None
    image_id: str | None = None
    image_path: str | None = None
    split: str | None = None
    line: int | None = None
    raw: str | None = None

    @property
    def level(self) -> str:
        return ISSUE_LEVELS.get(self.code, "warning")

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["level"] = self.level
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnnotationIssue:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class ImageRecord(ImageMeasurements):
    id: str = ""
    path: str = ""  # POSIX path relative to the dataset root
    split: str = "unspecified"
    aspect_ratio: float | None = None
    tags: list[str] = field(default_factory=list)
    label_path: str | None = None  # relative path of the label file (expected or actual)
    label_status: str = "n/a"  # ok | missing | empty | n/a
    boxes: list[Box] = field(default_factory=list)
    invalid_annotation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ImageRecord:
        names = {f.name for f in dataclasses.fields(cls)}
        data = {k: v for k, v in d.items() if k in names and k != "boxes"}
        rec = cls(**data)
        rec.boxes = [Box(**b) for b in d.get("boxes", [])]
        return rec


@dataclass
class DuplicateMember:
    image_id: str
    path: str
    split: str
    sha256: str | None = None


@dataclass
class DuplicateGroup:
    id: str
    kind: str  # "exact" (byte-identical) | "perceptual" (visually near-identical)
    scope: str  # "within_split" | "cross_split"
    splits: list[str]
    members: list[DuplicateMember]
    unique_files: int  # number of distinct SHA-256 values in the group
    max_distance: int = 0  # largest pHash Hamming distance between linked members

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DuplicateGroup:
        data = dict(d)
        data["members"] = [DuplicateMember(**m) for m in d["members"]]
        return cls(**data)


@dataclass
class Finding:
    id: str
    severity: str
    category: str
    title: str
    description: str
    affected_count: int
    recommendation: str
    examples: list[dict[str, Any]] = field(default_factory=list)
    affected_image_ids: list[str] = field(default_factory=list)
    splits: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    metric: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Finding:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class DatasetInfo:
    name: str
    root: str
    format: str
    class_names: list[str] = field(default_factory=list)
    splits: list[str] = field(default_factory=list)
    has_labels: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class AuditResult:
    id: str
    version: str
    created_at: str
    duration_s: float
    mode: str
    dataset: DatasetInfo
    config: dict[str, Any]
    images: list[ImageRecord]
    issues: list[AnnotationIssue]
    duplicates: list[DuplicateGroup]
    leakage: dict[str, Any]
    statistics: dict[str, Any]
    health: dict[str, Any]
    findings: list[Finding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "created_at": self.created_at,
            "duration_s": self.duration_s,
            "mode": self.mode,
            "dataset": dataclasses.asdict(self.dataset),
            "config": self.config,
            "images": [i.to_dict() for i in self.images],
            "issues": [i.to_dict() for i in self.issues],
            "duplicates": [g.to_dict() for g in self.duplicates],
            "leakage": self.leakage,
            "statistics": self.statistics,
            "health": self.health,
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuditResult:
        return cls(
            id=d["id"],
            version=d["version"],
            created_at=d["created_at"],
            duration_s=d["duration_s"],
            mode=d.get("mode", "scan"),
            dataset=DatasetInfo(**d["dataset"]),
            config=d["config"],
            images=[ImageRecord.from_dict(i) for i in d["images"]],
            issues=[AnnotationIssue.from_dict(i) for i in d["issues"]],
            duplicates=[DuplicateGroup.from_dict(g) for g in d["duplicates"]],
            leakage=d["leakage"],
            statistics=d["statistics"],
            health=d["health"],
            findings=[Finding.from_dict(f) for f in d["findings"]],
        )

    def summary(self) -> dict[str, Any]:
        """Small, list-friendly description of the audit (no per-image data)."""
        t = self.statistics["totals"]
        sev: dict[str, int] = {}
        for f in self.findings:
            sev[f.severity] = sev.get(f.severity, 0) + 1
        return {
            "id": self.id,
            "name": self.dataset.name,
            "root": self.dataset.root,
            "format": self.dataset.format,
            "created_at": self.created_at,
            "duration_s": self.duration_s,
            "mode": self.mode,
            "images_total": t["images_total"],
            "images_valid": t["images_valid"],
            "annotations_total": t["annotations_total"],
            "score": self.health.get("overall"),
            "grade": self.health.get("grade"),
            "findings_by_severity": sev,
        }
