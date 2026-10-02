"""Dataset adapter interface. New formats (COCO, classification) implement `DatasetAdapter`."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..analyzers.annotation import ParsedAnnotations
from ..core.config import AnnotationConfig
from ..core.models import DatasetInfo

SPLIT_ALIASES = {"valid": "val", "validation": "val", "dev": "val", "training": "train",
                 "testing": "test"}
SPLIT_PRIORITY = {"train": 0, "val": 1, "test": 2}


def normalize_split(name: str) -> str:
    key = name.strip().lower()
    return SPLIT_ALIASES.get(key, key) or "unspecified"


def image_id(rel_path: str) -> str:
    return hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:12]


@dataclass
class Sample:
    """One image plus where its annotation is expected to live."""

    path: Path  # absolute
    rel_path: str  # POSIX, relative to dataset root
    split: str
    label_path: Path | None = None
    unsupported: bool = False  # extension not in the supported set


@dataclass
class DatasetLayout:
    info: DatasetInfo
    samples: list[Sample]
    label_files: list[Path] = field(default_factory=list)  # every annotation file found on disk


class DatasetAdapter(ABC):
    """Format plug-in. The engine only talks to this interface."""

    name: str = "unknown"

    @classmethod
    @abstractmethod
    def detect(cls, root: Path) -> bool: ...

    @abstractmethod
    def discover(self, root: Path) -> DatasetLayout: ...

    @abstractmethod
    def read_annotations(self, sample: Sample, layout: DatasetLayout,
                         cfg: AnnotationConfig) -> ParsedAnnotations: ...
