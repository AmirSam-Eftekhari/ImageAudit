"""Perceptual hashes implemented directly on NumPy/OpenCV.

pHash: 32x32 grayscale -> 2-D DCT -> top-left 8x8 low-frequency block -> threshold at the median.
dHash: 9x8 grayscale -> horizontal gradient sign.
Both are 64-bit and robust to resizing, re-encoding and mild brightness changes. They are NOT
robust to crops, flips, rotations or heavy edits, and they say nothing about semantic similarity.
"""

from __future__ import annotations

import cv2
import numpy as np


def _bits_to_int(bits: np.ndarray) -> int:
    value = 0
    for b in bits.astype(np.uint8).ravel():
        value = (value << 1) | int(b)
    return value


def phash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8]
    return _bits_to_int(low > np.median(low))


def dhash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    return _bits_to_int(small[:, 1:] > small[:, :-1])


def to_hex(value: int) -> str:
    return f"{value:016x}"


def from_hex(text: str) -> int:
    return int(text, 16)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()
