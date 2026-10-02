"""Per-file image analysis: integrity, geometry, sharpness, exposure and hashes.

`ImageAnalyzer.analyze` never raises: every failure mode becomes a `status` plus a message so
that one bad file cannot abort a scan and problems are never silently ignored.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from ..core.config import AuditConfig
from ..core.models import ImageMeasurements
from . import hashing

ALLOWED_FORMATS = {"JPEG", "PNG", "BMP", "WEBP", "TIFF"}
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
_GRAY_MODES = {"1", "L", "LA", "La", "I", "I;16", "I;16L", "I;16B", "F"}
_CHANNELS = {"1": 1, "L": 1, "LA": 2, "La": 2, "I": 1, "I;16": 1, "I;16L": 1, "I;16B": 1, "F": 1,
             "RGB": 3, "RGBA": 4, "CMYK": 4, "YCbCr": 3, "LAB": 3, "HSV": 3}

# Bump when the meaning of any stored measurement changes; invalidates the analysis cache.
ANALYZER_VERSION = "1"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def _to_uint8(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == np.uint8:
        return arr
    a = arr.astype(np.float64)
    peak = a.max() if a.size else 0.0
    if peak <= 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    scale = 255.0 / (65535.0 if peak > 255 and np.issubdtype(arr.dtype, np.integer) else peak)
    return np.clip(a * scale, 0, 255).astype(np.uint8)


def _looks_gray(rgb: np.ndarray) -> bool:
    """True if an RGB array carries no colour information (channels nearly identical)."""
    step = max(1, max(rgb.shape[:2]) // 256)
    s = rgb[::step, ::step].astype(np.int16)
    return bool(np.abs(s[..., 0] - s[..., 1]).mean() < 1.0 and np.abs(s[..., 1] - s[..., 2]).mean() < 1.0)


def _exif_orientation(im: Image.Image) -> int:
    try:
        return int(im.getexif().get(0x0112, 1))
    except (OSError, ValueError, SyntaxError, TypeError):
        return 1  # unreadable EXIF is not an integrity problem


class ImageAnalyzer:
    def __init__(self, config: AuditConfig, *, full: bool = True) -> None:
        self.cfg = config
        self.full = full  # False => integrity + geometry only (used by `validate`)

    def cache_params(self) -> str:
        q = self.cfg
        return f"{ANALYZER_VERSION}:{q.quality.analysis_max_side}:{q.max_pixels}:{q.max_file_bytes}:{int(self.full)}"

    def analyze(self, path: Path, *, force_status: str | None = None) -> ImageMeasurements:
        m = ImageMeasurements()
        try:
            return self._analyze(path, m, force_status)
        except Exception as exc:  # last-resort guard: a scan must survive any single file
            m.status = "corrupted"
            m.error = f"Unexpected error while analysing: {type(exc).__name__}: {str(exc)[:160]}"
            return m

    # ------------------------------------------------------------------ internals
    def _analyze(self, path: Path, m: ImageMeasurements, force_status: str | None) -> ImageMeasurements:
        try:
            m.file_size = path.stat().st_size
        except OSError as exc:
            m.status, m.error = "corrupted", f"Cannot read file: {exc}"
            return m
        if force_status == "unsupported":
            m.status, m.error = "unsupported", f"Unsupported file type '{path.suffix or '(none)'}'"
            return m
        if m.file_size == 0:
            m.status, m.error = "zero_byte", "File is empty (0 bytes)"
            return m
        if m.file_size > self.cfg.max_file_bytes:
            m.status, m.error = "too_large", f"File exceeds size limit ({self.cfg.max_file_bytes} bytes)"
            return m

        m.sha256 = sha256_file(path)

        try:
            with Image.open(path) as probe:
                fmt = probe.format
                m.format, m.mode = fmt, probe.mode
                m.width, m.height = probe.size
                if fmt not in ALLOWED_FORMATS:
                    m.status, m.error = "unsupported", f"Unsupported image format: {fmt}"
                    return m
                if m.width * m.height > self.cfg.max_pixels:
                    m.status = "too_large"
                    m.error = f"Image has {m.width * m.height} pixels (limit {self.cfg.max_pixels})"
                    return m
                probe.verify()
        except UnidentifiedImageError:
            m.status, m.error = "corrupted", "Cannot identify image file (unreadable or not an image)"
            return m
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            m.status, m.error = "corrupted", f"Image failed verification: {str(exc)[:160]}"
            return m

        try:
            with Image.open(path) as im:
                if _exif_orientation(im) in (5, 6, 7, 8):  # labels refer to the displayed (rotated) image
                    m.width, m.height = m.height, m.width
                if im.format == "JPEG" and self.full:
                    im.draft(im.mode, (self.cfg.quality.analysis_max_side,) * 2)
                im.load()
                self._measure(im, m)
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            m.status, m.error = "corrupted", f"Image failed to decode: {str(exc)[:160]}"
            m.blur_score = m.brightness = m.contrast = None
            m.phash = m.dhash = None
        return m

    def _measure(self, im: Image.Image, m: ImageMeasurements) -> None:
        mode = im.mode
        if mode == "P":
            im = im.convert("RGBA" if "transparency" in im.info else "RGB")
            mode = im.mode
        if mode in _GRAY_MODES:
            m.is_grayscale = True
            m.channels = _CHANNELS.get(mode, 1)
            arr = np.asarray(im if mode not in ("LA", "La") else im.convert("L"))
            gray_full = _to_uint8(arr if arr.ndim == 2 else arr[..., 0])
        else:
            rgb = im if mode == "RGB" else im.convert("RGB")
            m.channels = _CHANNELS.get(mode, 3)
            rgb_arr = np.asarray(rgb)
            m.is_grayscale = _looks_gray(rgb_arr)
            gray_full = np.asarray(rgb.convert("L"))

        if not self.full:
            return

        side = self.cfg.quality.analysis_max_side
        h, w = gray_full.shape[:2]
        if max(h, w) > side:
            s = side / max(h, w)
            gray = cv2.resize(gray_full, (max(1, round(w * s)), max(1, round(h * s))),
                              interpolation=cv2.INTER_AREA)
        else:
            gray = gray_full
        m.blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        m.brightness = float(gray.mean())
        m.contrast = float(gray.std())
        m.phash = hashing.to_hex(hashing.phash(gray))
        m.dhash = hashing.to_hex(hashing.dhash(gray))
        m.hash_reliable = m.contrast >= self.cfg.duplicates.min_hash_std
