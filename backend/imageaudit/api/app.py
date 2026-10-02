"""FastAPI application: thin HTTP layer over ``AuditService``.

The business logic lives in ``api/service.py`` (unit-tested). See docs/api.md for the endpoint contract.

Run:  imageaudit serve      (or)      uvicorn imageaudit.api.app:create_app --factory
"""

import tempfile
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..core.config import AuditConfig
from ..core.errors import ConfigError, DatasetError, ImageAuditError, SecurityError
from ..reports.generator import CSV_KINDS, FORMATS
from .service import THUMB_SIZES, AuditService, BadRequest, ImageFilter, NotFound
from .settings import Settings

HTML_REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


class ScanRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096, description="Absolute path of a dataset directory on this machine")
    mode: Literal["scan", "validate"] = "scan"
    config: dict[str, Any] | None = Field(
        default=None, description="Partial config override, same shape as imageaudit.yaml")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = AuditService(settings)
        try:
            yield
        finally:
            app.state.service.close()

    app = FastAPI(title="ImageAudit API", version=__version__, lifespan=lifespan,
                  description="Local-first dataset auditing. Dataset files never leave this machine.")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])

    # ------------------------------------------------------------------ error handling
    @app.exception_handler(NotFound)
    async def _nf(_: Request, exc: NotFound) -> JSONResponse:
        return _error(404, "not_found", str(exc))

    @app.exception_handler(BadRequest)
    async def _br(_: Request, exc: BadRequest) -> JSONResponse:
        return _error(400, "bad_request", str(exc))

    @app.exception_handler(ConfigError)
    async def _cfg(_: Request, exc: ConfigError) -> JSONResponse:
        return _error(400, "invalid_config", str(exc))

    @app.exception_handler(SecurityError)
    async def _sec(_: Request, exc: SecurityError) -> JSONResponse:
        return _error(400, "invalid_path", str(exc))

    @app.exception_handler(DatasetError)
    async def _ds(_: Request, exc: DatasetError) -> JSONResponse:
        return _error(422, "invalid_dataset", str(exc))

    @app.exception_handler(ImageAuditError)
    async def _ia(_: Request, exc: ImageAuditError) -> JSONResponse:
        return _error(400, "error", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        return _error(422, "validation_error", detail)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return _error(500, "internal_error", f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ dependencies
    def get_service(request: Request) -> AuditService:
        return request.app.state.service

    Svc = Annotated[AuditService, Depends(get_service)]

    def image_filter(
        split: str | None = None,
        tag: Annotated[list[str] | None, Query()] = None,
        class_name: Annotated[str | None, Query(alias="class")] = None,
        q: str | None = None,
        status: str | None = None,
        min_width: int | None = Query(None, ge=0),
        max_width: int | None = Query(None, ge=0),
        min_height: int | None = Query(None, ge=0),
        max_height: int | None = Query(None, ge=0),
        finding: str | None = None,
        sort: str = "path",
        order: Literal["asc", "desc"] = "asc",
        page: int = Query(1, ge=1),
        page_size: int = Query(48, ge=1, le=200),
    ) -> ImageFilter:
        return ImageFilter(split=split, tags=tag or [], class_name=class_name, q=q, status=status,
                           min_width=min_width, max_width=max_width, min_height=min_height,
                           max_height=max_height, finding=finding, sort=sort, order=order,
                           page=page, page_size=page_size)

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health(svc: Svc) -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "local_only": True,
                "allowed_roots": [str(p) for p in svc.settings.allowed_roots],
                "max_upload_bytes": svc.settings.max_upload_bytes,
                "report_formats": list(FORMATS), "csv_kinds": list(CSV_KINDS),
                "thumbnail_sizes": list(THUMB_SIZES)}

    @app.get("/api/config/defaults")
    def config_defaults() -> dict[str, Any]:
        return AuditConfig().to_dict()

    # ------------------------------------------------------------------ scans (jobs)
    @app.post("/api/scans", status_code=202)
    def start_scan(body: ScanRequest, svc: Svc) -> dict[str, Any]:
        return svc.submit_path(body.path, mode=body.mode, config=body.config).public()

    @app.post("/api/scans/upload", status_code=202)
    def upload_scan(svc: Svc, file: Annotated[UploadFile, File()],
                    mode: Literal["scan", "validate"] = "scan") -> dict[str, Any]:
        name = Path(file.filename or "upload.zip").name
        if not name.lower().endswith(".zip"):
            raise BadRequest("Only .zip archives are supported for upload")
        tmp_dir = svc.home / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        limit = svc.settings.max_upload_bytes
        written = 0
        with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".zip", delete=False) as out:
            tmp = Path(out.name)
            try:
                while chunk := file.file.read(1024 * 1024):
                    written += len(chunk)
                    if written > limit:
                        raise BadRequest(f"Upload exceeds the {limit // (1024 * 1024)} MB limit")
                    out.write(chunk)
            except BaseException:
                out.close()
                tmp.unlink(missing_ok=True)
                raise
        return svc.submit_archive(tmp, name, mode=mode).public()

    @app.get("/api/scans")
    def list_scans(svc: Svc) -> list[dict[str, Any]]:
        return svc.jobs()

    @app.get("/api/scans/{job_id}")
    def get_scan(job_id: str, svc: Svc) -> dict[str, Any]:
        return svc.job(job_id).public()

    @app.delete("/api/scans/{job_id}", status_code=202)
    def cancel_scan(job_id: str, svc: Svc) -> dict[str, Any]:
        return svc.cancel(job_id).public()

    # ------------------------------------------------------------------ audits
    @app.get("/api/audits")
    def list_audits(svc: Svc) -> list[dict[str, Any]]:
        return svc.audits()

    @app.get("/api/audits/{audit_id}")
    def get_audit(audit_id: str, svc: Svc) -> dict[str, Any]:
        return svc.overview(audit_id)

    @app.delete("/api/audits/{audit_id}", status_code=204)
    def delete_audit(audit_id: str, svc: Svc) -> Response:
        svc.delete_audit(audit_id)
        return Response(status_code=204)

    @app.get("/api/audits/{audit_id}/images")
    def list_images(audit_id: str, svc: Svc, flt: Annotated[ImageFilter, Depends(image_filter)]) -> dict[str, Any]:
        return svc.image_page(audit_id, flt)

    @app.get("/api/audits/{audit_id}/images/{image_id}")
    def get_image(audit_id: str, image_id: str, svc: Svc) -> dict[str, Any]:
        return svc.image_detail(audit_id, image_id)

    @app.get("/api/audits/{audit_id}/images/{image_id}/thumbnail")
    def get_thumbnail(audit_id: str, image_id: str, svc: Svc,
                      size: int = Query(256, ge=32, le=1600)) -> FileResponse:
        path = svc.thumbnail(audit_id, image_id, size)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/audits/{audit_id}/annotations/issues")
    def list_issues(audit_id: str, svc: Svc, code: str | None = None, level: str | None = None,
                    split: str | None = None, q: str | None = None, page: int = Query(1, ge=1),
                    page_size: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        return svc.issues_page(audit_id, code=code, level=level, split=split, q=q, page=page, page_size=page_size)

    @app.get("/api/audits/{audit_id}/duplicates")
    def list_duplicates(audit_id: str, svc: Svc, kind: str | None = None, scope: str | None = None,
                        split: str | None = None, page: int = Query(1, ge=1),
                        page_size: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
        return svc.duplicates_page(audit_id, kind=kind, scope=scope, split=split, page=page, page_size=page_size)

    @app.get("/api/audits/{audit_id}/leakage")
    def get_leakage(audit_id: str, svc: Svc) -> dict[str, Any]:
        return svc.leakage(audit_id)

    @app.get("/api/audits/{audit_id}/findings")
    def list_findings(audit_id: str, svc: Svc, severity: str | None = None, category: str | None = None,
                      split: str | None = None,
                      class_name: Annotated[str | None, Query(alias="class")] = None) -> dict[str, Any]:
        return svc.findings(audit_id, severity=severity, category=category, split=split, class_name=class_name)

    @app.get("/api/audits/{audit_id}/reports/{fmt}")
    def get_report(audit_id: str, fmt: str, svc: Svc, csv_kind: str = "images",
                   include_images: bool = False, inline: bool = False) -> Response:
        data, content_type, filename = svc.report(audit_id, fmt, csv_kind, include_images)
        disposition = "inline" if inline and fmt in ("html", "pdf") else "attachment"
        headers = {"Content-Disposition": f'{disposition}; filename="{filename}"'}
        if fmt == "html":
            headers["Content-Security-Policy"] = HTML_REPORT_CSP
        return Response(content=data, media_type=content_type, headers=headers)

    # Unknown /api/* paths (including decoded traversal attempts such as /api/audits/../x) get the
    # same JSON 404 whether or not the UI mount below exists. Declared after every real route.
    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def unknown_api(rest: str) -> JSONResponse:
        return _error(404, "not_found", "Unknown API endpoint")

    # ------------------------------------------------------------------ bundled web UI
    # Mounted last so every /api route above wins. Only active when an exported UI exists
    # (the packaged EXE, or IMAGEAUDIT_STATIC_DIR); a plain `imageaudit serve` is API-only.
    if settings.static_dir is not None:
        app.mount("/", StaticFiles(directory=str(settings.static_dir), html=True), name="ui")

    return app


def iter_routes(app: FastAPI) -> Iterator[str]:  # used by docs tooling/tests
    for route in app.routes:
        methods = ",".join(sorted(getattr(route, "methods", None) or []))
        yield f"{methods} {getattr(route, 'path', '')}"
