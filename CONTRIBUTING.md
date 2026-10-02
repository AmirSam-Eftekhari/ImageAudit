# Contributing to ImageAudit

Thanks for your interest in contributing to ImageAudit.

ImageAudit is a local-first dataset auditing tool focused on practical diagnostics for computer-vision datasets. Contributions that improve correctness, security, test coverage, usability, documentation, or supported dataset formats are welcome.

---

## Development Setup

### Prerequisites

* Python 3.11+
* Node.js 18.18+
* Git

### Windows

Open PowerShell from the repository root:

```powershell
.\scripts\dev.ps1 setup
```

Start the backend in terminal 1:

```powershell
.\scripts\dev.ps1 api
```

Start the frontend in terminal 2:

```powershell
.\scripts\dev.ps1 web
```

The development services are:

* Web UI: `http://127.0.0.1:3000`
* FastAPI: `http://127.0.0.1:8000`

### macOS / Linux

```bash
sh scripts/dev.sh setup
```

Start the backend:

```bash
make api
```

Start the frontend in another terminal:

```bash
make web
```

Equivalent `scripts/dev.sh` commands can also be used where available.

---

## Repository Structure

The project is divided into a Python backend and a Next.js frontend:

```text
backend/
├── imageaudit/
│   ├── core/          Core engine, configuration, security and persistence
│   ├── datasets/      Dataset adapters
│   ├── analyzers/     Image and annotation analysis
│   ├── detectors/     Duplicate and leakage detection
│   ├── scoring/       Health scoring and findings
│   ├── reports/       Report generation
│   ├── api/           FastAPI application and service layer
│   └── cli/           Command-line interface
└── tests/              Backend test suite

frontend/               Next.js dashboard
packaging/              Windows executable build and smoke tests
examples/               Sample dataset and configuration
docs/                   Project documentation
scripts/                Development helpers
```

Keep responsibilities separated when making changes.

---

## Checks Before Opening a Pull Request

Run the relevant checks locally before submitting a PR.

### Backend

```bash
cd backend

ruff check .
pytest -q
```

### Frontend

```bash
cd frontend

npm run lint
npm run typecheck
npm run build
```

### Windows executable

If your changes affect packaging, static assets, startup behavior, API routing, or the packaged UI, also run:

```powershell
python packaging\smoke_test.py dist\ImageAudit.exe --dataset examples\sample_dataset
```

For a complete packaging verification:

```powershell
.\scripts\dev.ps1 build-exe
```

The packaging workflow produces `dist\ImageAudit.exe` and runs the smoke test unless explicitly skipped.

---

## Before Opening a PR

Please make sure that:

* The relevant tests pass.
* New behavior has appropriate test coverage.
* Existing functionality is not unnecessarily changed.
* Security-sensitive paths have regression tests.
* Documentation is updated when behavior or configuration changes.
* No secrets or machine-specific files are committed.
* The frontend does not introduce hard-coded audit or demo data.
* New dependencies are justified.
* The PR description clearly explains what changed and why.

Keep pull requests focused. A small, well-scoped change is easier to review, test, and maintain.

---

## Architecture Guidelines

### 1. Keep the audit engine framework-independent

The core audit engine should not depend on FastAPI, Next.js, or other web-framework concerns.

Prefer:

```text
CLI / API / Python
       │
       ▼
  AuditEngine
       │
       ├── Analyzers
       ├── Detectors
       ├── Scoring
       └── Reports
```

HTTP-specific behavior belongs in the API layer.

`api/app.py` should remain the HTTP/application boundary, while `api/service.py` contains API-facing business logic that can be tested independently.

---

### 2. Keep the frontend data-driven

UI values representing audits, findings, scores, images, or reports should come from the API or application state.

Do not add hard-coded demo data to production UI components.

If a feature needs sample data, use the existing synthetic dataset or dedicated test fixtures.

---

### 3. Preserve local-first behavior

Changes should not introduce telemetry, analytics, or unexpected external network requests.

Any feature that intentionally requires network access should document:

* why it is needed
* what data leaves the machine
* when the connection occurs
* how the behavior can be disabled

---

### 4. Treat filesystem and archive input as untrusted

Dataset paths, uploaded archives, filenames, and annotation contents should not be assumed to be safe.

When modifying security-sensitive code, consider regression tests for:

* path traversal
* absolute paths
* symlinks
* archive extraction
* archive size limits
* compression-ratio limits
* audit ID validation
* unauthorized filesystem access
* deletion and cleanup behavior

See [`SECURITY.md`](SECURITY.md) for the project's security model.

---

## Testing Guidelines

Prefer deterministic, synthetic fixtures over large real-world datasets.

Useful existing test infrastructure includes:

```text
backend/tests/helpers.py
imageaudit.demo
examples/sample_dataset
```

Tests should:

* be deterministic
* avoid network access
* avoid machine-specific paths
* clean up temporary files
* test observable behavior rather than implementation details where practical

When fixing a bug, prefer adding a regression test that would have failed before the fix.

---

## Dataset Adapters

Additional dataset formats should be implemented through:

```text
imageaudit.datasets.base.DatasetAdapter
```

A dataset adapter is responsible for format-specific concerns such as:

* dataset discovery
* split discovery
* image discovery
* annotation loading
* format-specific metadata

The audit engine, analyzers, duplicate detection, leakage detection, and scoring logic should remain format-independent wherever possible.

This separation is intentional: adding a dataset format should not require rewriting the core audit pipeline.

---

## Dependencies

Avoid adding new runtime dependencies unless they provide clear value.

Before introducing a dependency, consider:

* Can the functionality be implemented with the standard library?
* Is an existing dependency already capable of providing it?
* Is the dependency actively maintained?
* Does it increase the packaged executable size significantly?
* Does it introduce additional security or licensing considerations?

Development-only dependencies are preferable when a package is not required at runtime.

---

## Secrets and Local Files

Never commit:

* API keys
* passwords
* access tokens
* private certificates
* `.env` files containing secrets
* personal filesystem paths
* machine-specific configuration
* generated local state
* build artifacts

Before committing, review:

```bash
git status
git diff
git diff --cached
```

If you accidentally expose a secret, treat it as compromised and rotate it rather than simply deleting it from the working tree.

---

## Commit Messages

Keep commit messages short and action-oriented.

Prefer:

```text
Add archive extraction regression tests
Fix image path containment check
Improve report generation
Add COCO dataset adapter
Update Windows packaging
```

Avoid vague messages such as:

```text
changes
fix stuff
update
final
```

Reference an issue or discussion when appropriate.

---

## Pull Requests

A good PR should explain:

### What

What changed?

### Why

What problem does the change solve?

### Verification

What tests or checks were run?

For example:

```text
Tests:
- pytest -q
- ruff check .
- npm run lint
- npm run typecheck
- npm run build

Packaging:
- ImageAudit.exe smoke test
```

If a check was not run, state that explicitly.

---

## Documentation

Update documentation when a change affects:

* CLI commands
* configuration
* environment variables
* supported datasets
* API behavior
* installation
* security behavior
* packaging
* user-visible functionality

Documentation should describe the behavior that actually exists in the current release rather than planned functionality.

---

## Security Issues

Do **not** open a public GitHub issue for an exploitable security vulnerability.

Report security issues privately according to [`SECURITY.md`](SECURITY.md).

---

## License

By contributing to ImageAudit, you agree that your contributions are provided under the project's [MIT License](LICENSE).
