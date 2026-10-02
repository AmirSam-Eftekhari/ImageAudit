# Changelog

All notable changes to ImageAudit are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-10-02

Initial stable public release of ImageAudit.

### Added

* Local-first YOLO dataset auditing covering:

  * image integrity
  * image quality
  * YOLO annotations
  * exact duplicates
  * perceptual duplicates
  * train/validation/test leakage
* Documented and configurable dataset health score
* Structured findings with severity, explanations, affected counts, examples, and recommended actions
* CLI commands:

  * `scan`
  * `validate`
  * `report`
  * `serve`
  * `demo`
* CI-oriented validation with configurable failure thresholds
* Python API built around the shared `AuditEngine`
* FastAPI service with:

  * job-based scans
  * audit history
  * filtering
  * image explorer
  * thumbnails
  * findings
  * report generation
  * archive upload
* Next.js dashboard for local development and static export
* Single-file Windows executable packaging with PyInstaller
* Same-origin UI/API integration for the packaged Windows application
* JSON, CSV, self-contained HTML, and PDF reports
* Synthetic sample dataset and example configuration
* Automated Windows packaging smoke tests
* Path containment and archive extraction security controls
* Persistent local application state and cleanup behavior
* Configurable application data directory through `IMAGEAUDIT_HOME`
* Local-first operation without application telemetry or analytics

### Documentation

* Architecture documentation
* Health-score methodology
* API documentation
* Security policy and threat model
* Contribution guidelines
* Dataset and configuration examples

### Verification

The v1.0.0 release was verified through:

* Backend unit and integration tests
* Ruff static analysis
* Frontend linting
* Frontend type checking
* Next.js production build
* End-to-end Windows executable smoke testing
* Packaged UI/API integration testing
* Persistence, deletion, archive-upload, and restart checks

---

[1.0.0]: https://github.com/AmirSam-Eftekhari/ImageAudit/releases/tag/v1.0.0
[Keep a Changelog]: https://keepachangelog.com/en/1.1.0/
[Semantic Versioning]: https://semver.org/spec/v2.0.0.html
