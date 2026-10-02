"""SQLite cache of raw per-image measurements.

Only threshold-independent measurements are stored, so changing quality thresholds never forces a
re-decode. Entries are keyed by absolute path + (size, mtime_ns) + an analyzer-parameter string;
any change to the file or to the parameters is a cache miss.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .models import ImageMeasurements

_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    path TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    params TEXT NOT NULL,
    payload TEXT NOT NULL
)
"""


class AnalysisCache:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, path: str, size: int, mtime_ns: int, params: str) -> ImageMeasurements | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM measurements WHERE path=? AND size=? AND mtime_ns=? AND params=?",
                (path, size, mtime_ns, params),
            ).fetchone()
        return ImageMeasurements.from_dict(json.loads(row[0])) if row else None

    def put_many(self, rows: list[tuple[str, int, int, str, ImageMeasurements]]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO measurements VALUES (?,?,?,?,?)",
                [(p, s, m, prm, json.dumps(meas.to_dict())) for p, s, m, prm, meas in rows],
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
