"""Locate *read-only packaged resources* (built frontend, ...), in source and frozen builds.

Writable user data lives in :func:`imageaudit.core.paths.imageaudit_home`, never here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def bundle_root() -> Path | None:
    """PyInstaller's extraction directory when frozen, else ``None``."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def frontend_dir() -> Path | None:
    """Directory holding the exported (static) web UI, or ``None`` if there is none.

    ``IMAGEAUDIT_STATIC_DIR`` overrides; otherwise the frozen bundle's ``frontend/`` directory
    is used. A source checkout has no bundled UI (it runs ``next dev`` instead) unless the
    variable is set.
    """
    env = os.environ.get("IMAGEAUDIT_STATIC_DIR")
    if env:
        p = Path(env).expanduser()
        return p if (p / "index.html").is_file() else None
    root = bundle_root()
    if root is not None and (root / "frontend" / "index.html").is_file():
        return root / "frontend"
    return None
