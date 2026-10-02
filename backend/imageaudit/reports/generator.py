"""ReportGenerator: one entry point for every report format."""

from __future__ import annotations

import re
from pathlib import Path

from ..core.models import AuditResult
from .exports import CSV_KINDS, csv_report, json_report
from .html_report import html_report
from .pdf_report import pdf_report

FORMATS = ("json", "csv", "html", "pdf")
CONTENT_TYPES = {"json": "application/json", "csv": "text/csv; charset=utf-8",
                 "html": "text/html; charset=utf-8", "pdf": "application/pdf"}


class ReportGenerator:
    def generate(self, result: AuditResult, fmt: str, *, csv_kind: str = "images",
                 include_images: bool = False) -> bytes:
        fmt = fmt.lower()
        if fmt == "json":
            return json_report(result, include_images)
        if fmt == "csv":
            return csv_report(result, csv_kind)
        if fmt == "html":
            return html_report(result)
        if fmt == "pdf":
            return pdf_report(result)
        raise ValueError(f"Unsupported report format '{fmt}'. Choose from {FORMATS}")

    def write(self, result: AuditResult, fmt: str, path: str | Path, **kwargs) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(self.generate(result, fmt, **kwargs))
        return out

    @staticmethod
    def filename(result: AuditResult, fmt: str, csv_kind: str = "images") -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", result.dataset.name).strip("_") or "dataset"
        suffix = f"-{csv_kind}" if fmt == "csv" else ""
        return f"imageaudit-{safe}{suffix}.{fmt}"


__all__ = ["CONTENT_TYPES", "CSV_KINDS", "FORMATS", "ReportGenerator"]
