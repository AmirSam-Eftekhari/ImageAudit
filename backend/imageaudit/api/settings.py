"""API runtime settings, read from environment variables (no hidden global state)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..core.paths import imageaudit_home
from ..core.resources import frontend_dir
from ..core.security import allowed_roots_from_env

DEFAULT_CORS = ("http://localhost:3000", "http://127.0.0.1:3000")


@dataclass
class Settings:
    home: Path = field(default_factory=imageaudit_home)
    allowed_roots: list[Path] = field(default_factory=allowed_roots_from_env)
    cors_origins: tuple[str, ...] = DEFAULT_CORS
    max_upload_bytes: int = 2 * 1024**3
    max_concurrent_scans: int = 1
    static_dir: Path | None = field(default_factory=frontend_dir)  # exported web UI, if any

    @classmethod
    def from_env(cls) -> Settings:
        origins = os.environ.get("IMAGEAUDIT_CORS_ORIGINS")
        upload_mb = os.environ.get("IMAGEAUDIT_MAX_UPLOAD_MB")
        return cls(
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()) if origins else DEFAULT_CORS,
            max_upload_bytes=int(float(upload_mb) * 1024 * 1024) if upload_mb else 2 * 1024**3,
        )
