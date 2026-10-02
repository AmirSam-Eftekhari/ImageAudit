"""Format registry. Register additional adapters here (e.g. COCO) to extend detection."""

from __future__ import annotations

from pathlib import Path

from ..core.errors import DatasetError
from .base import DatasetAdapter
from .yolo import YoloAdapter

ADAPTERS: list[type[DatasetAdapter]] = [YoloAdapter]


def detect_adapter(root: Path) -> DatasetAdapter:
    for adapter_cls in ADAPTERS:
        if adapter_cls.detect(root):
            return adapter_cls()
    supported = ", ".join(a.name for a in ADAPTERS)
    raise DatasetError(
        f"Could not detect a supported dataset format in {root}. Supported formats: {supported}. "
        "Expected a YOLO layout (data.yaml, or images/ and labels/ folders).")
