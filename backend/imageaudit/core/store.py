"""Persistence for audit results: one JSON file per audit plus a small summary file."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .errors import ImageAuditError
from .models import AuditResult
from .paths import imageaudit_home

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


class AuditNotFound(ImageAuditError):
    pass


class AuditStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or (imageaudit_home() / "audits"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, audit_id: str, suffix: str = ".json") -> Path:
        if not _ID_RE.match(audit_id):
            raise AuditNotFound(f"Invalid audit id: {audit_id!r}")
        return self.root / f"{audit_id}{suffix}"

    def save(self, result: AuditResult) -> None:
        self._atomic_write(self._path(result.id), result.to_dict())
        self._atomic_write(self._path(result.id, ".meta.json"), result.summary())

    def load(self, audit_id: str) -> AuditResult:
        path = self._path(audit_id)
        if not path.is_file():
            raise AuditNotFound(f"Audit '{audit_id}' not found")
        return AuditResult.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in self.root.glob("*.meta.json"):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)

    def exists(self, audit_id: str) -> bool:
        """True if any persisted file for this audit exists. Raises ``AuditNotFound`` on a malformed id."""
        return any(self._path(audit_id, s).exists() for s in (".json", ".meta.json"))

    def delete(self, audit_id: str) -> None:
        """Remove every persisted file of one audit (including leftovers of an interrupted write).

        The id is validated against a strict pattern first, so no path component can escape ``root``.
        The summary file is removed first: once it is gone the audit no longer appears in listings,
        even if removing the (large) result file then fails.
        """
        for suffix in (".meta.json", ".json", ".meta.json.tmp", ".json.tmp"):
            self._path(audit_id, suffix).unlink(missing_ok=True)

    @staticmethod
    def _atomic_write(path: Path, payload: Any) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
