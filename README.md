# ImageAudit

**Local-first dataset quality and diagnostics for computer-vision datasets.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python\&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v1.0.0-blue.svg)](#)
[![Data](https://img.shields.io/badge/Data-local--first-22d3ee.svg)](#data-and-privacy)

ImageAudit audits YOLO computer-vision datasets for **integrity, image quality, annotation errors, duplicates, and train/validation/test leakage**.

It produces a transparent dataset health score and actionable reports in **HTML, PDF, JSON, and CSV**.

Run it from the **CLI**, integrate it into **Python workflows and CI**, use the **local web dashboard**, or build the **single-file Windows executable**.

> **v1.0.0**
>
> The first stable public release of ImageAudit. The v1 scope focuses on YOLO detection datasets, local-first operation, reproducible diagnostics, security-conscious archive handling, and practical reporting.

---

## Why ImageAudit?

Dataset problems are often discovered only after training has already started.

ImageAudit moves that validation step earlier.

It checks the dataset itself for problems such as:

* corrupt or truncated images
* invalid YOLO annotations
* missing or orphaned labels
* suspicious bounding boxes
* duplicate images
* cross-split leakage
* extremely low-resolution or unusual images
* dark, bright, low-contrast, or blurry images
* inconsistent dataset structure

Instead of returning only raw errors, ImageAudit organizes these problems into **structured findings**, severity levels, recommended actions, and an overall health score.

---

## Features

### Image integrity

* Corrupt, truncated, and zero-byte images
* Oversized files
* Unsupported extensions and formats
* Image dimensions
* EXIF-aware dimension handling
* Channel information
* Grayscale detection

### Image quality

* Blur detection using Laplacian variance
* Low-resolution detection
* Extreme aspect-ratio detection
* Brightness statistics
* Contrast statistics
* Dark / bright image detection

### YOLO annotation validation

* Malformed annotation lines with file and line number
* Invalid class IDs
* Negative coordinates
* Out-of-range coordinates
* Zero-area boxes
* Tiny and unusually large boxes
* Out-of-bounds boxes
* Duplicate boxes
* Missing label files
* Empty label files
* Orphan label files

### Duplicates and leakage

* Exact duplicates using SHA-256
* Perceptual duplicates using pHash and dHash
* Duplicate classification within a split
* Cross-split leakage detection

### Transparent health score

ImageAudit calculates a dataset health score from **eight weighted components**.

The formula, weights, and scoring methodology are documented and configurable.

See [`docs/health-score.md`](docs/health-score.md).

### Structured findings

Every finding can include:

* severity
* category
* title
* explanation
* affected count
* representative examples
* recommended action

### Reports

Generate:

* JSON
* CSV
* self-contained HTML
* PDF

HTML reports are designed to work without external scripts or network dependencies.

### Multiple interfaces

Use the same audit engine through:

* CLI
* Python API
* FastAPI service
* Next.js dashboard
* Windows single-file executable

### Local-first

ImageAudit is designed to run locally:

* source datasets are read in place
* uploaded archives are handled inside the application data directory
* no telemetry
* no analytics
* no external network calls from the application itself
* archive extraction includes security limits and traversal protection

---

## Screenshots

### HTML report

Generated with `imageaudit report` using the bundled sample dataset.

![HTML report overview](docs/img/html-report-overview.png)

![HTML report findings](docs/img/html-report-findings.png)

> Web dashboard screenshots are not included in v1.0.0 yet.

---

## Architecture

```text
backend/imageaudit/
├── core/          Engine, configuration, security, paths, store, cache
├── datasets/      YOLO adapter and DatasetAdapter abstraction
├── analyzers/     Image integrity, quality, annotations, hashing
├── detectors/     Duplicate and leakage detection
├── scoring/       Health score and structured findings
├── reports/       JSON, CSV, HTML, PDF
├── api/           Service layer and FastAPI routes
├── cli/           scan, validate, report, serve
└── desktop.py     Packaged Windows EXE entry point

frontend/          Next.js 14 App Router UI
packaging/         PyInstaller configuration, build and smoke tests
examples/          Synthetic sample dataset and example configuration
docs/              API contract, methodology and health-score documentation
```

### Design principles

The architecture deliberately keeps the core audit engine independent from the interfaces around it.

```text
                 ┌──────────────────┐
                 │   CLI / Python   │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │    AuditEngine    │
                 └────────┬─────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
     Analyzers        Detectors        Scoring
          │               │               │
          └───────────────┼───────────────┘
                          │
                 ┌────────▼─────────┐
                 │ Findings / Result │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │     Reports      │
                 └──────────────────┘
```

The FastAPI layer uses the same engine rather than maintaining a separate audit implementation.

`api/service.py` contains application logic such as jobs, filtering, thumbnails, and report generation, while `api/app.py` remains the HTTP layer.

For the packaged Windows application, the static-exported Next.js UI is served directly by FastAPI. The application therefore requires **no separate Node.js process at runtime**.

---

## Supported platforms

| Mode                            | Platform              |
| ------------------------------- | --------------------- |
| Source — CLI / API / Web UI     | Windows, macOS, Linux |
| Python                          | 3.11+                 |
| Packaged single-file executable | Windows               |
| Docker                          | Windows, macOS, Linux |

The Windows executable is built with PyInstaller on Windows.

---

## Dataset support

### YOLO detection

YOLO detection datasets are first-class in v1.0.0.

Supported layouts include:

```text
dataset/
├── images/
│   ├── train/
│   ├── val/
│   └── test/
└── labels/
    ├── train/
    ├── val/
    └── test/
```

and:

```text
dataset/
├── train/
│   ├── images/
│   └── labels/
├── val/
│   ├── images/
│   └── labels/
└── test/
    ├── images/
    └── labels/
```

An optional `data.yaml` is supported.

Polygon labels are validated and reduced to bounding boxes for the relevant diagnostics.

### Image formats

* JPEG
* PNG
* BMP
* WebP
* TIFF

### Not implemented in v1.0.0

* COCO datasets
* Classification-folder datasets
* Oriented bounding boxes
* Keypoint datasets

---

# Installation

## Quick start

### 1. Clone

```bash
git clone https://github.com/AmirSam-Eftekhari/ImageAudit.git
cd ImageAudit
```

### 2. Install the backend

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -e "./backend[api,dev]"
```

### 3. Run an audit

```bash
imageaudit scan path/to/dataset
```

Validate a dataset:

```bash
imageaudit validate path/to/dataset --full
```

Generate a report:

```bash
imageaudit report path/to/audit.json -o report.html
```

---

# Usage

## CLI

```text
imageaudit scan DATASET [--config F] [--workers N] [--no-cache] [-o audit.json]

imageaudit validate DATASET [--full] [--fail-on SEVERITY] [--fail-under SCORE]

imageaudit report AUDIT.json [-f html|pdf|json|csv] [-o OUT]

imageaudit serve [--host 127.0.0.1] [--port 8000]

imageaudit demo DEST_DIR
```

### CI validation

`validate` can be used as a CI gate.

For example:

```bash
imageaudit validate data/ --full --fail-on critical --fail-under 80
```

The command returns a non-zero exit code when the configured failure policy is triggered.

---

## Web dashboard

For local development, install Node.js 18.18+ and run:

### Windows

```powershell
.\scripts\dev.ps1 setup

.\scripts\dev.ps1 api
```

In another terminal:

```powershell
.\scripts\dev.ps1 web
```

Open:

**http://127.0.0.1:3000**

The development API runs on:

**http://127.0.0.1:8000**

### macOS / Linux

```bash
sh scripts/dev.sh setup
```

Terminal 1:

```bash
make api
```

Terminal 2:

```bash
make web
```

---

# Windows executable

ImageAudit can be packaged as a single Windows executable containing the backend and static web UI.

### Build

Requirements:

* Windows
* Python 3.11+
* Node.js 18.18+

```powershell
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 build-exe
```

Output:

```text
dist/ImageAudit.exe
```

The resulting executable is approximately **80–85 MB**.

The build process also runs an automated smoke test against the produced binary unless `-SkipSmoke` is specified.

### Run

Double-click:

```text
ImageAudit.exe
```

or run it from a terminal.

The application:

1. starts the local API
2. binds to loopback
3. opens the system browser
4. serves the UI and API from the same origin

The default port is:

```text
8765
```

Persistent application data is stored under:

```text
%LOCALAPPDATA%\ImageAudit
```

Set `IMAGEAUDIT_HOME` to override the location.

**Dataset directories are never written to by the application.**

### Smoke test

```powershell
python packaging\smoke_test.py dist\ImageAudit.exe --dataset examples\sample_dataset
```

---

# Docker

Docker support is optional.

```bash
DATASETS=/path/to/datasets docker compose up --build
```

The development container exposes:

* API: `http://127.0.0.1:8000`
* UI: `http://127.0.0.1:3000`

Datasets are mounted read-only under `/datasets`.

The API only scans paths under the configured dataset root.

---

# Python API

The audit engine can also be used directly from Python:

```python
from imageaudit import AuditEngine, load_config
from imageaudit.reports.generator import ReportGenerator

config = load_config("imageaudit.yaml")

result = AuditEngine(config).run("path/to/dataset")

print(result.health["overall"])

critical = [
    finding
    for finding in result.findings
    if finding.severity == "critical"
]

print([finding.title for finding in critical])

ReportGenerator().write(
    result,
    "html",
    "report.html",
)
```

The CLI, API, and Python integration all operate on the same underlying audit engine.

---

# Configuration

ImageAudit accepts an optional `imageaudit.yaml` in the dataset root or through `--config`.

Example:

[`examples/imageaudit.example.yaml`](examples/imageaudit.example.yaml)

Unknown configuration keys are rejected.

## Environment variables

| Variable                   | Purpose                                      |
| -------------------------- | -------------------------------------------- |
| `IMAGEAUDIT_HOME`          | Writable application state directory         |
| `IMAGEAUDIT_ALLOWED_ROOTS` | Optional dataset path allow-list             |
| `IMAGEAUDIT_CORS_ORIGINS`  | Comma-separated CORS origins for development |
| `IMAGEAUDIT_MAX_UPLOAD_MB` | Maximum uploaded ZIP size; default `2048`    |
| `IMAGEAUDIT_STATIC_DIR`    | Override static-exported UI directory        |
| `NEXT_PUBLIC_API_URL`      | Development frontend API base URL            |

---

# Data and privacy

ImageAudit follows a **local-first** architecture.

### Source datasets

Source datasets are read in place.

They are not copied into the application data directory unless the user explicitly uploads an archive through the application.

### Uploaded archives

Uploaded archives are:

1. extracted inside the application data directory
2. scanned
3. cleaned up when the corresponding audit is deleted

Temporary extraction state is also cleaned up on process exit where applicable.

### Persistent state

Packaged Windows builds store application state in:

```text
%LOCALAPPDATA%\ImageAudit
```

Source and other platforms use:

```text
~/.imageaudit
```

This can be overridden with:

```text
IMAGEAUDIT_HOME
```

Persistent state includes:

* audit results
* thumbnails
* SQLite measurement cache
* logs

### Network behavior

ImageAudit itself does not send telemetry, analytics, or dataset data to external services.

The desktop application opens the local dashboard in the system browser; that is the intended browser interaction.

> If you expose the API beyond localhost, add authentication and review the deployment security model first. ImageAudit does not provide built-in authentication in v1.0.0.

---

# Security

Dataset paths and uploaded archives are treated as untrusted input.

ImageAudit includes protections such as:

* path containment checks using resolved filesystem paths
* protected per-image reads
* archive traversal protection
* rejection of absolute archive paths
* rejection of `..` traversal
* symlink rejection
* encrypted archive rejection
* archive member-count limits
* per-member size limits
* total extraction-size limits
* compression-ratio limits
* opaque audit/image identifiers
* Jinja2 HTML autoescaping
* restrictive Content Security Policy for generated HTML reports
* loopback binding by default
* explicit CORS allow-listing
* no `shell=True`
* no `os.system` usage in the application

For vulnerability reporting, see [`SECURITY.md`](SECURITY.md).

---

# Health score

ImageAudit's health score is intentionally designed to be inspectable rather than opaque.

The score is composed of **eight weighted components**, each representing a different aspect of dataset quality.

The complete formula and weighting model are documented here:

[`docs/health-score.md`](docs/health-score.md)

The score is a **dataset hygiene indicator**. It should not be interpreted as a direct prediction of model accuracy or training performance.

---

# Testing

The v1.0.0 release was verified across the backend, frontend, and packaged Windows application.

### Backend

```powershell
cd backend

ruff check .

pytest -q
```

### Frontend

```powershell
cd frontend

npm run lint
npm run typecheck
npm run build
```

### Packaged application

```powershell
python packaging\smoke_test.py dist\ImageAudit.exe --dataset examples\sample_dataset
```

The smoke test covers the packaged application end-to-end, including:

* static UI assets
* API health
* scan creation and completion
* audit results
* image explorer
* thumbnails
* HTML/PDF/CSV/JSON reports
* archive upload
* audit deletion
* persistence
* restart behavior
* cleanup of temporary extraction state
* path validation

---

# Project structure

```text
.
├── backend/              Python package and tests
├── frontend/             Next.js UI
├── packaging/            Windows EXE build and smoke tests
├── examples/             Sample dataset and configuration
├── docs/                 API, methodology and health-score documentation
├── scripts/              Development helpers
├── .github/workflows/    CI workflows
├── LICENSE               MIT license
├── SECURITY.md           Security policy
└── README.md
```

---

# Limitations

v1.0.0 intentionally keeps the scope focused.

* YOLO detection is the primary supported dataset format
* Polygon labels are reduced to boxes for relevant diagnostics
* Oriented bounding boxes and keypoints are not interpreted
* Blur and exposure thresholds are heuristic
* Duplicate detection is hash-based; semantic embedding similarity is not implemented
* Findings describe dataset hygiene, not expected model accuracy
* The current audit store uses in-memory state plus on-disk JSON persistence
* Extremely large datasets may benefit from a different storage and pagination strategy
* The packaged single-file build targets Windows
* Authentication is not included
* Shared or internet-facing deployments require additional security controls

---

# Roadmap

Planned areas for future releases include:

* COCO dataset adapter
* Classification-folder adapter
* Embedding-based near-duplicate detection
* Stronger storage and pagination for very large datasets
* Optional authentication for shared deployments
* Per-class quality metrics
* Additional dataset diagnostics and quality signals

The roadmap is intentionally non-binding; priorities may change based on real-world usage and feedback.

---

# Contributing

Contributions, bug reports, and technical feedback are welcome.

Please read:

[`CONTRIBUTING.md`](CONTRIBUTING.md)

before opening a pull request.

---

# License

ImageAudit is released under the **MIT License**.

See [`LICENSE`](LICENSE) for the full license text.
