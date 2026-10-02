"""Deterministic generator for a small, intentionally problematic YOLO dataset.

The images are synthetic (coloured shapes on noisy gradients): no copyrighted or sensitive data.
Every defect is recorded in the returned manifest so tests can assert that the audit finds it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

CLASS_NAMES = ["square", "circle", "triangle", "star"]  # "star" is declared but never used
W, H = 320, 240


def _encode(img: np.ndarray, ext: str, quality: int = 92) -> bytes:
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext == ".jpg" else []
    ok, buf = cv2.imencode(ext, img, params)
    assert ok
    return buf.tobytes()


def _canvas(rng: np.random.Generator) -> np.ndarray:
    theta = rng.uniform(0, np.pi)
    ys, xs = np.mgrid[0:H, 0:W]
    t = (xs / W * np.cos(theta) + ys / H * np.sin(theta))
    t = (t - t.min()) / (t.max() - t.min())
    c1, c2 = rng.uniform(30, 140, 3), rng.uniform(30, 140, 3)
    img = c1[None, None, :] * (1 - t[..., None]) + c2[None, None, :] * t[..., None]
    img += rng.normal(0, 5, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def _draw(img: np.ndarray, cls: int, rng: np.random.Generator) -> tuple[float, float, float, float]:
    size = int(rng.integers(36, 84))
    x0 = int(rng.integers(8, W - size - 8))
    y0 = int(rng.integers(8, H - size - 8))
    color = tuple(int(v) for v in rng.integers(170, 255, 3))
    if cls == 0:
        cv2.rectangle(img, (x0, y0), (x0 + size, y0 + size), color, -1)
    elif cls == 1:
        cv2.circle(img, (x0 + size // 2, y0 + size // 2), size // 2, color, -1)
    else:
        pts = np.array([[x0 + size // 2, y0], [x0, y0 + size], [x0 + size, y0 + size]], np.int32)
        cv2.fillPoly(img, [pts], color)
    return ((x0 + size / 2) / W, (y0 + size / 2) / H, size / W, size / H)


def _scene(rng: np.random.Generator, probs: tuple[float, ...] = (0.65, 0.31, 0.04)
           ) -> tuple[np.ndarray, list[tuple[int, float, float, float, float]]]:
    img = _canvas(rng)
    boxes = []
    for _ in range(int(rng.integers(1, 4))):
        cls = int(rng.choice(3, p=probs))
        boxes.append((cls, *_draw(img, cls, rng)))
    return img, boxes


def _label(boxes: list[tuple[int, float, float, float, float]]) -> str:
    return "".join(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n" for c, x, y, w, h in boxes)


def generate_sample_dataset(dest: str | Path, seed: int = 7) -> dict[str, Any]:
    """Create the dataset under ``dest`` (created if missing) and return a manifest of defects."""
    root = Path(dest)
    rng = np.random.default_rng(seed)
    for split in ("train", "val", "test"):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)

    def put(split: str, name: str, img: np.ndarray, boxes_text: str | None, ext: str = ".jpg",
            quality: int = 92) -> None:
        (root / "images" / split / f"{name}{ext}").write_bytes(_encode(img, ext, quality))
        if boxes_text is not None:
            (root / "labels" / split / f"{name}.txt").write_text(boxes_text, encoding="utf-8")

    scenes: dict[str, tuple[np.ndarray, list]] = {}
    for split, n in (("train", 36), ("val", 9), ("test", 7)):
        for i in range(n):
            img, boxes = _scene(rng)
            scenes[f"{split}_{i:03d}"] = (img, boxes)
            put(split, f"{split}_{i:03d}", img, _label(boxes), ext=".png" if i % 9 == 8 else ".jpg")

    manifest: dict[str, Any] = {"classes": CLASS_NAMES, "defects": {}}
    d = manifest["defects"]

    # --- duplicates -------------------------------------------------------------
    for src, dup in (("train_001", "train_dup_a"), ("train_002", "train_dup_b")):
        img, boxes = scenes[src]
        put("train", dup, img, _label(boxes))          # byte-identical re-encode of same pixels
    (root / "images/train/train_dup_a.jpg").write_bytes((root / "images/train/train_001.jpg").read_bytes())
    (root / "images/train/train_dup_b.jpg").write_bytes((root / "images/train/train_002.jpg").read_bytes())
    d["exact_duplicates_within_train"] = 2
    img, boxes = scenes["train_003"]
    (root / "images/val/val_leak_exact.jpg").write_bytes((root / "images/train/train_003.jpg").read_bytes())
    (root / "labels/val/val_leak_exact.txt").write_text(_label(boxes), encoding="utf-8")
    d["exact_leak_train_val"] = 1
    img, boxes = scenes["train_007"]
    small = cv2.resize(img, (256, 192), interpolation=cv2.INTER_AREA)
    put("test", "test_leak_near", small, _label(boxes), quality=60)
    d["near_leak_train_test"] = 1
    img, boxes = scenes["train_012"]
    put("train", "train_near_dup", np.clip(img.astype(np.int16) + 8, 0, 255).astype(np.uint8), _label(boxes), quality=70)
    d["near_duplicate_within_train"] = 1

    # --- quality ------------------------------------------------------------------
    for i, split in enumerate(("train", "train", "train", "val")):
        img, boxes = _scene(rng)
        put(split, f"{split}_blurry_{i}", cv2.GaussianBlur(img, (0, 0), 6), _label(boxes))
    d["blurry_images"] = 4
    img, boxes = _scene(rng)
    put("train", "train_dark", (img * 0.06).astype(np.uint8), _label(boxes))
    img, boxes = _scene(rng)
    put("train", "train_bright", np.clip(img.astype(np.int16) * 0.2 + 215, 0, 255).astype(np.uint8), _label(boxes))
    d["dark_images"], d["bright_images"] = 1, 1
    img, boxes = _scene(rng)
    put("train", "train_lowres", cv2.resize(img, (60, 45), interpolation=cv2.INTER_AREA), _label(boxes))
    d["low_resolution_images"] = 1
    pano = np.concatenate([_canvas(rng)[:, :250] for _ in range(4)], axis=1)  # 1000x240 => 4.2:1 (> 4:1 threshold)
    put("train", "train_panorama", pano, "0 0.5 0.5 0.1 0.3\n")
    d["extreme_aspect_images"] = 1
    for i in range(3):
        img, boxes = _scene(rng)
        put("train", f"train_gray_{i}", cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), _label(boxes), ext=".png")
    d["grayscale_images"] = 3

    # --- integrity ----------------------------------------------------------------
    (root / "images/train/train_corrupt.jpg").write_bytes(b"\xff\xd8\xff\xe0 this is not a real jpeg" + bytes(range(64)))
    good = (root / "images/train/train_005.jpg").read_bytes()
    (root / "images/train/train_truncated.jpg").write_bytes(good[: len(good) // 2])
    (root / "images/train/train_empty.jpg").write_bytes(b"")
    gif_path = root / "images/train/train_animation.gif"
    cv2.imwrite(str(root / "images/train/_tmp.png"), scenes["train_004"][0])
    from PIL import Image
    with Image.open(root / "images/train/_tmp.png") as im:
        im.convert("P").save(gif_path, format="GIF")
    (root / "images/train/_tmp.png").unlink()
    for name in ("train_corrupt", "train_truncated", "train_empty", "train_animation"):
        (root / "labels/train" / f"{name}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    d["corrupted_images"] = 2
    d["zero_byte_images"] = 1
    d["unsupported_images"] = 1

    # --- annotations ----------------------------------------------------------------
    (root / "labels/train/train_010.txt").write_text(
        "0 0.5 0.5 0.2\n"                       # 4 fields => malformed
        "square 0.5 0.5 0.2 0.2\n"              # non-integer class => malformed
        "9 0.4 0.4 0.1 0.1\n"                   # class id out of range
        "0 160 120 50 40\n"                     # pixel coordinates (>1)
        "1 -0.2 0.5 0.1 0.1\n"                  # negative cx
        "1 0.5 0.5 0.0 0.2\n"                   # zero width
        "0 0.3 0.3 0.1 0.1\n0 0.3 0.3 0.1 0.1\n"  # duplicate annotation
        "1 0.8 0.8 0.004 0.004\n"               # tiny box
        "0 0.5 0.5 0.99 0.99\n",                # covers 98% of the image
        encoding="utf-8")
    d["annotation_error_lines"] = 6
    for name in ("train_020", "train_021", "train_022"):
        (root / "labels/train" / f"{name}.txt").unlink()
    (root / "labels/val/val_005.txt").unlink()
    d["missing_label_files"] = 4
    for name in ("train_030", "train_031"):
        (root / "labels/train" / f"{name}.txt").write_text("", encoding="utf-8")
    d["empty_label_files"] = 2
    (root / "labels/train/ghost_0001.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    d["orphan_labels"] = 1

    (root / "data.yaml").write_text(
        "# Synthetic ImageAudit sample dataset (intentionally problematic)\n"
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASS_NAMES)), encoding="utf-8")
    return manifest
