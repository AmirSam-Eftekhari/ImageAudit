# HTTP API (v0.1)

> **Status:** the service layer behind these endpoints (`backend/imageaudit/api/service.py`) is covered by
> unit tests. The FastAPI route layer (`api/app.py`) and `tests/test_api_routes.py` were **written but could not be
> executed in the build sandbox** (FastAPI not installable there). Run `pytest` after `pip install -e ".[api,dev]"`.

Base URL: `http://127.0.0.1:8000` (override with `imageaudit serve --host/--port`). Interactive OpenAPI docs are
served by FastAPI at `/docs`. The server binds to loopback by default and reads dataset files in place.

## Errors

Every non-2xx response has the same shape:

```json
{ "error": { "code": "invalid_path", "message": "Path does not exist: /nope" } }
```

| HTTP | `code` | meaning |
|---|---|---|
| 400 | `bad_request`, `invalid_config`, `invalid_path`, `error` | bad parameter, unknown config key, path missing / outside allowed roots |
| 404 | `not_found` | unknown scan, audit, image or finding |
| 422 | `validation_error`, `invalid_dataset` | malformed request body/query; directory is not a recognised dataset |
| 500 | `internal_error` | unexpected failure (message includes the exception type) |

## Scans (background jobs)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/scans` | Body `{ "path": str, "mode": "scan"\|"validate", "config": {…partial imageaudit.yaml…} }` -> `202 Job` |
| `POST` | `/api/scans/upload?mode=` | `multipart/form-data` field `file` (.zip only, size-limited, safely extracted) -> `202 Job` |
| `GET` | `/api/scans` | Jobs since server start, newest first |
| `GET` | `/api/scans/{job_id}` | Poll for progress |
| `DELETE` | `/api/scans/{job_id}` | Request cancellation |

`Job`: `{ id, path, mode, source: "path"|"upload", status: "queued"|"running"|"done"|"failed"|"cancelled", stage, done, total, progress (0..1), error, audit_id, created_at, finished_at }`.
`audit_id` is set when `status == "done"`.

## Audits

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/audits` | `Summary[]` (also includes audits created by the CLI) |
| `GET` | `/api/audits/{id}` | `Overview`: summary + `dataset`, `config`, `health`, `statistics`, `findings`, `leakage` |
| `DELETE` | `/api/audits/{id}` | `204` (no body); removes the stored audit (result, summary, leftover temp files), its thumbnails and - for zip uploads - the extracted copy; never your dataset path. Unknown / malformed / already-deleted id -> `404` `not_found`. Unknown `/api/*` paths also return a JSON `404` |
| `GET` | `/api/audits/{id}/images` | `ImagePage` — query: `split`, `tag` (repeatable; all must match), `class`, `q` (path substring), `status`, `min_width`, `max_width`, `min_height`, `max_height`, `finding`, `sort` (`path|size|width|height|blur|brightness|annotations`), `order`, `page`, `page_size` (<= 200) |
| `GET` | `/api/audits/{id}/images/{image_id}` | `ImageDetail`: metrics, hashes, `boxes[]` (normalised cx,cy,w,h + class name), `issues[]`, `duplicate_groups[]` |
| `GET` | `/api/audits/{id}/images/{image_id}/thumbnail?size=` | `image/jpeg`, bounded to 128/256/512/1024/1600 px, cached on disk |
| `GET` | `/api/audits/{id}/annotations/issues` | `code`, `level`, `split`, `q`, `page`, `page_size` |
| `GET` | `/api/audits/{id}/duplicates` | `kind` (`exact|perceptual`), `scope` (`within_split|cross_split`), `split`, `page`, `page_size` (<= 100) |
| `GET` | `/api/audits/{id}/leakage` | pairwise split relationships + disclaimer |
| `GET` | `/api/audits/{id}/findings` | `severity`, `category`, `split`, `class` |
| `GET` | `/api/audits/{id}/reports/{fmt}` | `fmt` = `html|pdf|json|csv`; `csv_kind` = `images|findings|issues|duplicates`; `include_images=true` (json); `inline=true` (html/pdf preview) |

Images are addressed by an opaque `image_id`; the API never accepts a file path from the client for reading
files, and re-checks that every resolved path stays inside the dataset root.

## Other

| `GET` | `/api/health` | `{ status, version, local_only, allowed_roots, max_upload_bytes, report_formats, … }` |
|---|---|---|
| `GET` | `/api/config/defaults` | the default `AuditConfig` as JSON |

## Environment variables

| Variable | Effect |
|---|---|
| `IMAGEAUDIT_HOME` | where audits, cache and thumbnails are stored (default `~/.imageaudit`) |
| `IMAGEAUDIT_ALLOWED_ROOTS` | `os.pathsep`-separated allow-list of dataset roots for `POST /api/scans` |
| `IMAGEAUDIT_CORS_ORIGINS` | comma-separated browser origins (default `http://localhost:3000,http://127.0.0.1:3000`) |
| `IMAGEAUDIT_MAX_UPLOAD_MB` | upload cap (default 2048) |
| `IMAGEAUDIT_WORKERS`, `IMAGEAUDIT_NO_CACHE` | engine overrides |

The TypeScript types in `frontend/lib/types.ts` mirror these payloads.
