"""YOLO dataset discovery (Ultralytics-style ``data.yaml`` or plain ``images/`` + ``labels/``)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from ..analyzers.annotation import ParsedAnnotations, YoloAnnotationAnalyzer
from ..analyzers.image import SUPPORTED_EXTENSIONS
from ..core.config import AnnotationConfig
from ..core.errors import DatasetError
from ..core.models import DatasetInfo
from ..core.security import is_within
from .base import SPLIT_PRIORITY, DatasetAdapter, DatasetLayout, Sample, normalize_split

YAML_NAMES = ("data.yaml", "data.yml", "dataset.yaml", "dataset.yml")
SPLIT_KEYS = ("train", "val", "valid", "validation", "test")
IGNORED_SUFFIXES = {".txt", ".json", ".yaml", ".yml", ".cache", ".md", ".csv", ".xml", ".npy"}
IGNORED_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
NON_LABEL_TXT = {"classes.txt", "labels.txt", "obj.names", "readme.txt", "notes.txt"}


def _find_yaml(root: Path) -> Path | None:
    for name in YAML_NAMES:
        p = root / name
        if p.is_file():
            return p
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, yaml.YAMLError) as exc:
        raise DatasetError(f"Cannot parse {path.name}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _class_names(data: dict[str, Any]) -> list[str]:
    names = data.get("names")
    if isinstance(names, dict):
        try:
            items = sorted(((int(k), str(v)) for k, v in names.items()), key=lambda kv: kv[0])
        except (TypeError, ValueError):
            return []
        if items and [k for k, _ in items] == list(range(len(items))):
            return [v for _, v in items]
        size = (items[-1][0] + 1) if items else 0
        out = [f"class_{i}" for i in range(size)]
        for k, v in items:
            out[k] = v
        return out
    if isinstance(names, list):
        return [str(n) for n in names]
    nc = data.get("nc")
    if isinstance(nc, int) and nc > 0:
        return [f"class_{i}" for i in range(nc)]
    return []


def label_path_for(image_path: Path) -> Path:
    """Ultralytics convention: replace the last ``images`` path component with ``labels``."""
    parts = list(image_path.parts)
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].lower() == "images":
            parts[i] = "labels"
            return Path(*parts).with_suffix(".txt")
    return image_path.with_suffix(".txt")


class YoloAdapter(DatasetAdapter):
    name = "yolo"

    # ----------------------------------------------------------------- detection
    @classmethod
    def detect(cls, root: Path) -> bool:
        yaml_path = _find_yaml(root)
        if yaml_path is not None:
            data = _load_yaml(yaml_path)
            if "names" in data or "nc" in data or any(k in data for k in SPLIT_KEYS):
                return True
        if (root / "images").is_dir() and (root / "labels").is_dir():
            return True
        return any((root / s / "images").is_dir() and (root / s / "labels").is_dir()
                   for s in ("train", "val", "valid", "test"))

    # ----------------------------------------------------------------- discovery
    def discover(self, root: Path) -> DatasetLayout:
        notes: list[str] = []
        yaml_path = _find_yaml(root)
        data = _load_yaml(yaml_path) if yaml_path else {}
        class_names = _class_names(data)
        split_dirs = self._splits_from_yaml(root, yaml_path, data, notes) if data else {}
        if not split_dirs:
            split_dirs = self._splits_from_layout(root)
            if split_dirs and yaml_path:
                notes.append("data.yaml declares no usable split paths; splits inferred from folders")
        if not split_dirs:
            raise DatasetError("No YOLO images found: expected data.yaml split paths or "
                               "images/<split>/ folders")

        samples: list[Sample] = []
        seen: set[str] = set()
        for split, sources in split_dirs.items():
            for src in sources:
                for path in self._iter_images(root, src):
                    key = os.path.normcase(str(path))
                    if key in seen:
                        continue
                    seen.add(key)
                    rel = path.relative_to(root).as_posix()
                    samples.append(Sample(
                        path=path, rel_path=rel, split=split, label_path=label_path_for(path),
                        unsupported=path.suffix.lower() not in SUPPORTED_EXTENSIONS))
        samples.sort(key=lambda s: s.rel_path)

        label_dirs = {s.label_path.parent for s in samples if s.label_path}
        label_files = self._collect_label_files(root, label_dirs)
        info = DatasetInfo(name=str(data.get("name") or root.name), root=str(root), format=self.name,
                           class_names=class_names, splits=sorted({s.split for s in samples},
                           key=lambda s: (SPLIT_PRIORITY.get(s, 99), s)),
                           has_labels=True, notes=notes)
        if not class_names:
            notes.append("No class names found in data.yaml; class-id range checks are skipped")
        return DatasetLayout(info=info, samples=samples, label_files=label_files)

    def read_annotations(self, sample: Sample, layout: DatasetLayout,
                         cfg: AnnotationConfig) -> ParsedAnnotations:
        count = len(layout.info.class_names) or None
        analyzer = YoloAnnotationAnalyzer(cfg, count)
        rel = None
        if sample.label_path is not None:
            try:
                rel = sample.label_path.relative_to(Path(layout.info.root)).as_posix()
            except ValueError:
                rel = sample.label_path.name
        return analyzer.analyze_file(sample.label_path, rel)

    # ------------------------------------------------------------------- helpers
    def _splits_from_yaml(self, root: Path, yaml_path: Path | None, data: dict[str, Any],
                          notes: list[str]) -> dict[str, list[Path]]:
        base = root
        if isinstance(data.get("path"), str):
            declared = Path(data["path"])
            base = declared if declared.is_absolute() else (root / declared)
        out: dict[str, list[Path]] = {}
        for key in SPLIT_KEYS:
            value = data.get(key)
            if value is None:
                continue
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                if not isinstance(entry, str):
                    continue
                resolved = self._resolve_entry(root, base, entry)
                if resolved is None:
                    notes.append(f"Split '{key}': path '{entry}' not found inside the dataset; ignored")
                    continue
                out.setdefault(normalize_split(key), []).append(resolved)
        return out

    @staticmethod
    def _resolve_entry(root: Path, base: Path, entry: str) -> Path | None:
        candidates = [base / entry, root / entry]
        stripped = entry
        while stripped.startswith(("../", "..\\", "./")):  # Roboflow-style '../train/images'
            stripped = stripped[3:] if stripped.startswith("..") else stripped[2:]
        if stripped:
            candidates.append(root / stripped)
        for cand in candidates:
            try:
                if cand.exists() and is_within(root, cand):
                    return cand.resolve()
            except OSError:
                continue
        return None

    @staticmethod
    def _splits_from_layout(root: Path) -> dict[str, list[Path]]:
        out: dict[str, list[Path]] = {}
        images = root / "images"
        if images.is_dir():
            subs = [d for d in sorted(images.iterdir()) if d.is_dir()
                    and normalize_split(d.name) in ("train", "val", "test")]
            if subs:
                for d in subs:
                    out.setdefault(normalize_split(d.name), []).append(d)
            else:
                out["unspecified"] = [images]
        for name in ("train", "val", "valid", "validation", "test"):
            d = root / name / "images"
            if d.is_dir():
                out.setdefault(normalize_split(name), []).append(d)
        return out

    @staticmethod
    def _iter_images(root: Path, src: Path):
        """Yield files under ``src`` (a directory, or a .txt list of image paths)."""
        if src.is_file():
            if src.suffix.lower() != ".txt":
                return
            for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                p = Path(line)
                cand = p if p.is_absolute() else (src.parent / p)
                if not cand.exists():
                    cand = root / p
                if cand.is_file() and is_within(root, cand):
                    yield cand.resolve()
            return
        for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
            dirnames.sort()
            for fn in sorted(filenames):
                if fn.lower() in IGNORED_NAMES or fn.startswith("."):
                    continue
                suffix = Path(fn).suffix.lower()
                if suffix in IGNORED_SUFFIXES:
                    continue
                p = Path(dirpath) / fn
                if p.is_symlink() and not is_within(root, p):
                    continue
                yield p

    @staticmethod
    def _collect_label_files(root: Path, label_dirs: set[Path]) -> list[Path]:
        found: dict[str, Path] = {}
        for d in label_dirs:
            if not d.is_dir():
                continue
            for dirpath, _dirs, files in os.walk(d, followlinks=False):
                for fn in files:
                    if fn.lower().endswith(".txt") and fn.lower() not in NON_LABEL_TXT:
                        p = Path(dirpath) / fn
                        found[os.path.normcase(str(p))] = p
        return sorted(found.values())
