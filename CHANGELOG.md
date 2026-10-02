# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-02

### Added

- Local-first YOLO dataset auditor (integrity, quality, annotations, exact/perceptual duplicates, train/val/test leakage)
- Documented, configurable health score
- CLI: `scan`, `validate`, `report`, `serve`, `demo`
- FastAPI service with job-based scans, image explorer, thumbnails, findings, reports
- Next.js dashboard (dev + static export for packaging)
- Windows one-file EXE packaging (PyInstaller) with same-origin UI/API
- Synthetic sample dataset and packaging smoke tests
- Path/archive security guards and persistence under a dedicated application data directory
