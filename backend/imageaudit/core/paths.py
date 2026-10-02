"""Filesystem locations used for persisted state (audits, caches, thumbnails)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle (the single-file Windows EXE)."""
    return bool(getattr(sys, "frozen", False))


def imageaudit_home() -> Path:
    """Return the *writable* state directory, creating it if needed.

    Resolution order:

    1. ``IMAGEAUDIT_HOME`` environment variable (always wins).
    2. Packaged Windows build: ``%LOCALAPPDATA%\\ImageAudit``. This is deliberately never the
       PyInstaller extraction directory, which is temporary and read-only by intent.
    3. Otherwise ``~/.imageaudit`` (unchanged development / CLI default).

    Dataset directories are never written to; everything ImageAudit persists lives here.
    """
    env = os.environ.get("IMAGEAUDIT_HOME")
    if env:
        home = Path(env).expanduser()
    elif is_frozen() and sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        home = Path(os.environ["LOCALAPPDATA"]) / "ImageAudit"
    else:
        home = Path.home() / ".imageaudit"
    home.mkdir(parents=True, exist_ok=True)
    return home
