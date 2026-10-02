"""Shared synthetic fixtures. Everything is generated in code: no binary test assets."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

CLASSES = ["square", "circle", "triangle"]


def textured(seed: int, w: int = 160, h: int = 120) -> np.ndarray:
    """Sharp, high-detail, low-frequency-distinct BGR image (distinct seeds => distinct pHash)."""
    rng = np.random.default_rng(seed)
    coarse = rng.integers(20, 235, (6, 8, 3), dtype=np.uint8)
    img = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.int16)
    img += rng.normal(0, 12, img.shape).astype(np.int16)
    for _ in range(6):
        x, y = int(rng.integers(0, max(1, w - 30))), int(rng.integers(0, max(1, h - 30)))
        cv2.rectangle(img, (x, y), (x + 24, y + 20), tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
    return np.clip(img, 0, 255).astype(np.uint8)


def write_img(path: Path, img: np.ndarray, quality: int = 92) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if path.suffix.lower() in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(path.suffix, img, params)
    assert ok
    path.write_bytes(buf.tobytes())
    return path


def write_label(root: Path, split: str, name: str, text: str) -> Path:
    p = root / "labels" / split / f"{name}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def write_yaml(root: Path, splits: tuple[str, ...] = ("train", "val", "test")) -> None:
    lines = ["path: ."] + [f"{s}: images/{s}" for s in splits] + ["names:"]
    lines += [f"  {i}: {n}" for i, n in enumerate(CLASSES)]
    (root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_clean_dataset(root: Path, n_train: int = 6, n_val: int = 2, n_test: int = 2) -> Path:
    """Small, healthy YOLO dataset: every image distinct, every label valid, classes balanced."""
    seed = 100
    for split, n in (("train", n_train), ("val", n_val), ("test", n_test)):
        for i in range(n):
            seed += 1
            write_img(root / "images" / split / f"{split}_{i}.jpg", textured(seed))
            write_label(root, split, f"{split}_{i}", f"{seed % 3} 0.5 0.5 0.3 0.3\n{(seed + 1) % 3} 0.25 0.25 0.2 0.2\n")
    write_yaml(root)
    return root


class TempCase(unittest.TestCase):
    """Provides an isolated temp dir and IMAGEAUDIT_HOME (cache/store) per test."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="imageaudit-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self._old_home = os.environ.get("IMAGEAUDIT_HOME")
        os.environ["IMAGEAUDIT_HOME"] = str(self.home)
        self.addCleanup(self._restore_env)
        self.root = self.tmp / "dataset"
        self.root.mkdir()

    def _restore_env(self) -> None:
        if self._old_home is None:
            os.environ.pop("IMAGEAUDIT_HOME", None)
        else:
            os.environ["IMAGEAUDIT_HOME"] = self._old_home
