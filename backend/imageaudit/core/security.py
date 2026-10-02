"""Guards for untrusted paths and archives.

Dataset paths and uploaded archives are treated as hostile: nothing here shells out, nothing
follows a path outside the intended root, and archive extraction enforces hard size limits
based on bytes actually written (not on sizes claimed by the archive headers).
"""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .errors import SecurityError

MAX_ARCHIVE_FILES = 200_000
MAX_ARCHIVE_BYTES = 20 * 1024**3
MAX_MEMBER_BYTES = 2 * 1024**3
MAX_COMPRESSION_RATIO = 200
_DATASET_DIRS = {"images", "labels", "train", "val", "valid", "validation", "test"}


def is_within(root: Path, path: Path) -> bool:
    """True if ``path`` resolves to ``root`` or something beneath it."""
    try:
        resolved_root = root.resolve()
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == resolved_root or resolved_root in resolved.parents


def resolve_within(root: Path, relative: str | Path) -> Path:
    """Join ``relative`` onto ``root`` and refuse anything that escapes it."""
    candidate = (root / relative).resolve()
    if not is_within(root, candidate):
        raise SecurityError(f"Path escapes dataset root: {relative}")
    return candidate


def allowed_roots_from_env() -> list[Path]:
    raw = os.environ.get("IMAGEAUDIT_ALLOWED_ROOTS", "")
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]


def validate_dataset_path(path: str | Path, allowed_roots: list[Path] | None = None) -> Path:
    """Resolve a user-supplied dataset directory and enforce the optional allow-list."""
    if not str(path).strip():
        raise SecurityError("Dataset path is empty")
    if "\x00" in str(path):
        raise SecurityError("Dataset path contains a NUL byte")
    p = Path(path).expanduser()
    try:
        resolved = p.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SecurityError(f"Dataset path does not exist: {path}") from exc
    if not resolved.is_dir():
        raise SecurityError(f"Dataset path is not a directory: {path}")
    roots = allowed_roots if allowed_roots is not None else allowed_roots_from_env()
    if roots and not any(is_within(r, resolved) for r in roots):
        raise SecurityError(
            "Dataset path is outside the directories allowed by IMAGEAUDIT_ALLOWED_ROOTS"
        )
    return resolved


def _check_member_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if p.is_absolute() or normalized.startswith("/"):
        raise SecurityError(f"Archive contains an absolute path: {name!r}")
    if ".." in p.parts:
        raise SecurityError(f"Archive contains a path traversal entry: {name!r}")
    if any(":" in part for part in p.parts):
        raise SecurityError(f"Archive entry has a drive/stream marker: {name!r}")
    if "\x00" in name:
        raise SecurityError("Archive entry contains a NUL byte")
    return p


def safe_extract_zip(
    archive: Path,
    dest: Path,
    *,
    max_files: int = MAX_ARCHIVE_FILES,
    max_total_bytes: int = MAX_ARCHIVE_BYTES,
    max_member_bytes: int = MAX_MEMBER_BYTES,
) -> Path:
    """Extract ``archive`` into ``dest`` and return the dataset root inside it.

    Rejects: path traversal, absolute paths, symlinks, encrypted members, too many members,
    oversized members/totals and suspicious compression ratios.
    """
    dest.mkdir(parents=True, exist_ok=True)
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        raise SecurityError(f"Not a valid zip archive: {exc}") from exc
    total = 0
    with zf:
        infos = [i for i in zf.infolist() if not i.filename.startswith("__MACOSX/")]
        if len(infos) > max_files:
            raise SecurityError(f"Archive has too many entries ({len(infos)} > {max_files})")
        for info in infos:
            rel = _check_member_name(info.filename)
            if info.flag_bits & 0x1:
                raise SecurityError(f"Encrypted archive member not supported: {info.filename!r}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                raise SecurityError(f"Archive contains a symlink: {info.filename!r}")
            if info.file_size > max_member_bytes:
                raise SecurityError(f"Archive member too large: {info.filename!r}")
            if (
                info.compress_size > 0
                and info.file_size > 1024 * 1024
                and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise SecurityError(f"Suspicious compression ratio: {info.filename!r}")
            target = resolve_within(dest, Path(*rel.parts)) if rel.parts else dest
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(1024 * 1024):
                    written += len(chunk)
                    total += len(chunk)
                    if written > max_member_bytes or total > max_total_bytes:
                        raise SecurityError("Archive exceeds the maximum allowed extracted size")
                    out.write(chunk)
    return find_dataset_root(dest)


def find_dataset_root(extracted: Path) -> Path:
    """Descend through single-directory wrappers (``dataset.zip`` -> ``dataset/...``)."""
    current = extracted
    for _ in range(4):
        entries = [e for e in current.iterdir() if not e.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir() and entries[0].name.lower() not in _DATASET_DIRS:
            current = entries[0]
        else:
            break
    return current


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
