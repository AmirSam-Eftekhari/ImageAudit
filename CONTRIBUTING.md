# Contributing to ImageAudit

Thanks for your interest in contributing.

## Development setup

**Windows (PowerShell):**

```powershell
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 api    # terminal 1 — FastAPI on :8000
.\scripts\dev.ps1 web    # terminal 2 — Next.js on :3000
```

**macOS / Linux:**

```bash
sh scripts/dev.sh setup   # or: make setup
make api                  # terminal 1
make web                  # terminal 2
```

Prerequisites: Python 3.11+, Node.js 18.18+.

## Checks before opening a PR

```bash
# Backend
cd backend
ruff check .
pytest -q

# Frontend
cd frontend
npm run lint
npm run typecheck
npm run build
```

Optional packaging smoke test (Windows, after a full EXE build):

```powershell
python packaging\smoke_test.py dist\ImageAudit.exe --dataset examples\sample_dataset
```

## Guidelines

1. **Preserve architecture.** Keep the audit engine free of web-framework imports. Put HTTP concerns in `api/app.py` and business logic in `api/service.py`.
2. **Tests.** Prefer synthetic fixtures generated in code (`backend/tests/helpers.py`, `imageaudit.demo`). Cover security-sensitive behaviour (path traversal, archive extraction, audit id validation, deletion cleanup) when you touch those paths.
3. **UI numbers come from the API.** Do not hard-code demo data in the frontend.
4. **No secrets.** Do not commit `.env`, credentials, personal paths, or machine-specific configuration.
5. **Dependencies.** Avoid adding new runtime dependencies unless necessary. Prefer stdlib and existing packages.
6. **Commit messages.** Short, imperative summary; reference issues when applicable.

## Dataset adapters

New formats implement `imageaudit.datasets.base.DatasetAdapter` (discovery + annotation reading). The engine, detectors, and scoring do not need to change for additional formats.

## Security

See [SECURITY.md](SECURITY.md). Report vulnerabilities privately; do not open public issues for exploitable flaws.
