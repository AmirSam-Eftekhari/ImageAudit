"""ImageAudit command line interface.

Exit codes (stable, for CI):
    0  success / validation passed
    1  validation failed (a configured threshold was exceeded)
    2  usage, configuration, dataset or I/O error
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from .. import __version__
from ..core.cache import AnalysisCache
from ..core.config import SEVERITIES, AuditConfig, find_config, load_config
from ..core.engine import AuditEngine
from ..core.errors import ImageAuditError
from ..core.models import AuditResult
from ..core.paths import imageaudit_home
from ..core.store import AuditStore
from ..demo import generate_sample_dataset
from ..reports.generator import CSV_KINDS, FORMATS, ReportGenerator

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2
SEV_CHOICES = click.Choice(list(SEVERITIES[:-1]))


def _common(fn: Callable[..., Any]) -> Callable[..., Any]:
    opts = [
        click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False),
                     help="YAML config file (default: imageaudit.yaml inside the dataset, if present)."),
        click.option("--workers", type=click.IntRange(min=1), default=None,
                     help="Worker threads for image analysis (default: auto)."),
        click.option("--no-cache", is_flag=True, help="Do not read or write the analysis cache."),
    ]
    for o in reversed(opts):
        fn = o(fn)
    return fn


def _build_config(dataset: Path | None, config_path: str | None, workers: int | None,
                  no_cache: bool) -> AuditConfig:
    path: Path | None = Path(config_path) if config_path else None
    if path is None and dataset is not None and dataset.is_dir():
        path = find_config(dataset)
    overrides: dict[str, Any] = {}
    if workers:
        overrides["workers"] = workers
    if no_cache:
        overrides["use_cache"] = False
    return load_config(path, overrides)


class _Progress:
    """Single-line stderr progress; silent when stderr is not a terminal."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled and sys.stderr.isatty()
        self._last = ""

    def __call__(self, stage: str, done: int = 0, total: int = 0) -> None:
        if not self.enabled:
            return
        text = f"  {stage:<11}" + (f" {done}/{total}" if total else "")
        if text != self._last:
            click.echo("\r" + text.ljust(40), nl=False, err=True)
            self._last = text

    def finish(self) -> None:
        if self.enabled and self._last:
            click.echo("\r" + " " * 40 + "\r", nl=False, err=True)


def _run_audit(dataset: str, cfg: AuditConfig, mode: str, show_progress: bool) -> AuditResult:
    cache = AnalysisCache(imageaudit_home() / "cache.sqlite") if cfg.use_cache else None
    progress = _Progress(show_progress)
    try:
        return AuditEngine(cfg, cache=cache).run(dataset, mode=mode, progress=progress)
    finally:
        progress.finish()
        if cache is not None:
            cache.close()


def _save(result: AuditResult) -> None:
    try:
        AuditStore().save(result)
    except OSError as exc:  # persisting is a convenience; never fail the audit for it
        click.echo(f"warning: could not save audit to the local store: {exc}", err=True)


def _rate(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2%}"


def _print_summary(result: AuditResult, top: int = 12) -> None:
    t = result.statistics["totals"]
    h = result.health
    click.echo(f"ImageAudit {result.version} - {result.dataset.name} ({result.dataset.format}, mode={result.mode})")
    click.echo(f"  path        {result.dataset.root}")
    click.echo(f"  images      {t['images_total']} total, {t['images_valid']} valid, {t['images_invalid']} invalid")
    click.echo(f"  annotations {t['annotations_total']} in {t['annotated_images']} images "
               f"({t['empty_label_images']} empty, {t['missing_label_images']} missing labels)")
    splits = result.statistics["splits"]
    if splits:
        click.echo("  splits      " + ", ".join(f"{d['split']}={d['images']}" for d in splits))
    score = "n/a" if h["overall"] is None else f"{h['overall']:.1f}/100 (grade {h['grade']})"
    click.echo(f"  health      {score}   scanned in {result.duration_s}s")
    if result.mode == "validate":
        click.echo("  note        validate mode skips blur, exposure, duplicate and leakage analysis")
    click.echo("")
    click.echo("Component scores:")
    for c in h["components"]:
        if c["applicable"]:
            click.echo(f"  {c['label']:<22} {c['score']:>6.1f}   weight {c['weight']:g}   metric {c['metric']}")
        else:
            click.echo(f"  {c['label']:<22}    n/a")
    click.echo("")
    if not result.findings:
        click.echo("Findings: none")
        return
    counts: dict[str, int] = {}
    for f in result.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    click.echo("Findings: " + ", ".join(f"{counts[s]} {s}" for s in SEVERITIES if s in counts))
    for f in result.findings[:top]:
        click.echo(f"  [{f.severity.upper():<8}] {f.title}  (affected: {f.affected_count})")
    if len(result.findings) > top:
        click.echo(f"  ... {len(result.findings) - top} more (use `imageaudit report` for the full list)")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", prog_name="imageaudit")
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
def cli(verbose: bool) -> None:
    """ImageAudit - local-first dataset quality and diagnostics for computer-vision datasets.

    Everything runs on this machine; dataset files are only ever read.
    """
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")


@cli.command()
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@_common
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="Write the full audit JSON here.")
@click.option("--json", "as_json", is_flag=True, help="Print a machine-readable summary to stdout.")
@click.option("--no-save", is_flag=True, help="Do not store the audit for the web UI / `report`.")
def scan(dataset: str, config_path: str | None, workers: int | None, no_cache: bool,
         output: str | None, as_json: bool, no_save: bool) -> None:
    """Run the full audit (integrity, quality, annotations, duplicates, leakage, score)."""
    cfg = _build_config(Path(dataset), config_path, workers, no_cache)
    result = _run_audit(dataset, cfg, "scan", show_progress=not as_json)
    if not no_save:
        _save(result)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    if as_json:
        click.echo(json.dumps({"summary": result.summary(), "health": result.health,
                               "findings": [f.to_dict() for f in result.findings]}, indent=2))
    else:
        _print_summary(result)
        if not no_save:
            click.echo(f"\nAudit id: {result.id}  (view it in the web UI, or: imageaudit report {result.id})")


def _evaluate(result: AuditResult, cfg: AuditConfig, opts: dict[str, Any]) -> list[str]:
    """Return human-readable failure reasons (empty list = pass)."""
    ci = cfg.ci
    fail_on = opts["fail_on"] if opts["fail_on"] is not None else ci.fail_on
    fail_under = opts["fail_under"] if opts["fail_under"] is not None else ci.fail_under
    limits = {
        "integrity": ("corrupt rate", opts["max_corrupt_rate"] if opts["max_corrupt_rate"] is not None else ci.max_corrupt_rate),
        "leakage": ("leakage rate", opts["max_leakage_rate"] if opts["max_leakage_rate"] is not None else ci.max_leakage_rate),
        "annotation_validity": ("invalid annotation rate", opts["max_invalid_annotation_rate"] if opts["max_invalid_annotation_rate"] is not None else ci.max_invalid_annotation_rate),
        "duplicates": ("duplicate rate", opts["max_duplicate_rate"] if opts["max_duplicate_rate"] is not None else ci.max_duplicate_rate),
        "blur": ("blur rate", opts["max_blur_rate"] if opts["max_blur_rate"] is not None else ci.max_blur_rate),
    }
    reasons: list[str] = []
    comps = {c["key"]: c for c in result.health["components"]}
    for key, (label, limit) in limits.items():
        if limit is None:
            continue
        metric = comps[key]["metric"]
        if metric is None:
            if result.mode == "validate" and key in ("duplicates", "leakage", "blur"):
                raise click.UsageError(f"--max-{label.replace(' ', '-')} needs --full (not computed in validate mode)")
            continue
        if metric > limit:
            reasons.append(f"{label} {metric:.2%} exceeds limit {limit:.2%}")
    if fail_under is not None:
        overall = result.health["overall"]
        if overall is not None and overall < fail_under:
            reasons.append(f"health score {overall:.1f} is below {fail_under:g}")
    if fail_on:
        cutoff = SEVERITIES.index(fail_on)
        hits = [f for f in result.findings if SEVERITIES.index(f.severity) <= cutoff]
        if hits:
            worst = ", ".join(sorted({f.severity for f in hits}, key=SEVERITIES.index))
            reasons.append(f"{len(hits)} finding(s) at or above '{fail_on}' severity ({worst})")
    return reasons


@cli.command()
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@_common
@click.option("--full", is_flag=True, help="Also run quality, duplicate and leakage analysis (slower).")
@click.option("--fail-on", type=SEV_CHOICES, default=None, help="Fail if any finding is at/above this severity.")
@click.option("--fail-under", type=click.FloatRange(0, 100), default=None, help="Fail if health score is below this (needs --full).")
@click.option("--max-corrupt-rate", type=click.FloatRange(0, 1), default=None)
@click.option("--max-invalid-annotation-rate", type=click.FloatRange(0, 1), default=None)
@click.option("--max-leakage-rate", type=click.FloatRange(0, 1), default=None, help="Needs --full.")
@click.option("--max-duplicate-rate", type=click.FloatRange(0, 1), default=None, help="Needs --full.")
@click.option("--max-blur-rate", type=click.FloatRange(0, 1), default=None, help="Needs --full.")
@click.option("--json", "as_json", is_flag=True, help="Print a machine-readable verdict to stdout.")
def validate(dataset: str, config_path: str | None, workers: int | None, no_cache: bool, full: bool,
             as_json: bool, **opts: Any) -> None:
    """Validate a dataset for CI. Exit code 0 = pass, 1 = threshold exceeded, 2 = error.

    By default runs the fast structural checks (file integrity + annotation validation). Thresholds
    can also come from the `ci:` section of imageaudit.yaml; command-line flags take precedence.
    """
    if opts["fail_under"] is not None and not full:
        raise click.UsageError("--fail-under requires --full (the score is partial in validate mode)")
    cfg = _build_config(Path(dataset), config_path, workers, no_cache)
    result = _run_audit(dataset, cfg, "scan" if full else "validate", show_progress=not as_json)
    reasons = _evaluate(result, cfg, opts)
    if as_json:
        click.echo(json.dumps({"passed": not reasons, "reasons": reasons, "summary": result.summary()}, indent=2))
    else:
        _print_summary(result, top=8)
        click.echo("")
        if reasons:
            click.echo("VALIDATION FAILED")
            for r in reasons:
                click.echo(f"  - {r}")
        else:
            click.echo("VALIDATION PASSED")
    sys.exit(EXIT_FAIL if reasons else EXIT_OK)


def _load_source(source: str, cfg_args: tuple[str | None, int | None, bool]) -> AuditResult:
    p = Path(source)
    if p.is_file() and p.suffix.lower() == ".json":
        try:
            return AuditResult.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise click.ClickException(
                f"{p} is not a full ImageAudit audit JSON (use `scan -o` to create one): {exc}") from exc
    if p.is_dir():
        cfg = _build_config(p, *cfg_args)
        result = _run_audit(source, cfg, "scan", show_progress=True)
        _save(result)
        return result
    return AuditStore().load(source)  # audit id; raises AuditNotFound (an ImageAuditError)


@cli.command()
@click.argument("source")
@_common
@click.option("-f", "--format", "formats", multiple=True, type=click.Choice([*FORMATS, "all"]),
              default=("html",), show_default=True, help="Report format (repeatable).")
@click.option("-o", "--output-dir", type=click.Path(file_okay=False), default="imageaudit-report",
              show_default=True)
@click.option("--include-images", is_flag=True, help="Include per-image records in the JSON report.")
def report(source: str, config_path: str | None, workers: int | None, no_cache: bool,
           formats: tuple[str, ...], output_dir: str, include_images: bool) -> None:
    """Generate reports from a dataset directory, a saved audit id, or an audit JSON file."""
    result = _load_source(source, (config_path, workers, no_cache))
    wanted = list(FORMATS) if "all" in formats else list(dict.fromkeys(formats))
    gen = ReportGenerator()
    out = Path(output_dir)
    for fmt in wanted:
        if fmt == "csv":
            for kind in CSV_KINDS:
                path = gen.write(result, "csv", out / gen.filename(result, "csv", kind), csv_kind=kind)
                click.echo(f"wrote {path}")
        else:
            path = gen.write(result, fmt, out / gen.filename(result, fmt), include_images=include_images)
            click.echo(f"wrote {path}")


@cli.command()
@click.argument("dest", type=click.Path(file_okay=False))
@click.option("--seed", type=int, default=7, show_default=True)
def demo(dest: str, seed: int) -> None:
    """Generate the small, intentionally problematic synthetic sample dataset."""
    target = Path(dest)
    if target.exists() and any(target.iterdir()):
        raise click.ClickException(f"{target} already exists and is not empty")
    manifest = generate_sample_dataset(target, seed=seed)
    click.echo(f"Sample dataset written to {target}")
    click.echo("Injected defects: " + ", ".join(f"{k}={v}" for k, v in manifest["defects"].items()))
    click.echo(f"Try: imageaudit scan {target}")


@cli.command()
def audits() -> None:
    """List audits stored on this machine (also shown in the web UI)."""
    rows = AuditStore().list()
    if not rows:
        click.echo("No stored audits yet. Run `imageaudit scan <dataset>`.")
        return
    for m in rows:
        score = "n/a" if m.get("score") is None else f"{m['score']:.1f}"
        click.echo(f"{m['id']}  {m['created_at']}  score={score}  images={m['images_total']}  {m['name']}")


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Bind address. Keep 127.0.0.1 unless you understand the exposure.")
@click.option("--port", type=int, default=8000, show_default=True)
@click.option("--reload", is_flag=True, help="Auto-reload (development).")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the local API server for the web UI (requires: pip install 'imageaudit[api]')."""
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException("The API needs extra dependencies: pip install 'imageaudit[api]'") from exc
    uvicorn.run("imageaudit.api.app:create_app", factory=True, host=host, port=port, reload=reload)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # never crash on legacy Windows code pages
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        cli(standalone_mode=False)
    except click.exceptions.Exit as exc:
        sys.exit(exc.exit_code)
    except click.Abort:
        click.echo("Aborted.", err=True)
        sys.exit(EXIT_ERROR)
    except click.ClickException as exc:
        exc.show()
        sys.exit(EXIT_ERROR)
    except ImageAuditError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    main()
