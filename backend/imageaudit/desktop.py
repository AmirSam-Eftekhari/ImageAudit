"""Entry point of the packaged desktop build (``ImageAudit.exe``).

Starts the FastAPI app (which also serves the bundled, pre-built web UI) on a loopback port and
opens the default browser. This is *not* used in development: there, run ``imageaudit serve`` plus
``next dev`` as before. The regular CLI (``imageaudit scan ...``) is unaffected.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_PORT = 8765
HOST = "127.0.0.1"


def _log_file() -> Path:
    from .core.paths import imageaudit_home

    logs = imageaudit_home() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / "imageaudit.log"


def _setup_logging() -> Path:
    """Log to a file. A windowed (no-console) build has ``sys.stdout``/``sys.stderr`` set to ``None``."""
    path = _log_file()
    stream = open(path, "a", buffering=1, encoding="utf-8", errors="replace")  # noqa: SIM115 - process lifetime
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(path, encoding="utf-8")],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    return path


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
        except OSError:
            return False
    return True


def _pick_port(preferred: int) -> int:
    if _port_free(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return int(s.getsockname()[1])


def _imageaudit_running(port: int) -> bool:
    """True if an ImageAudit API already answers on this port (second launch -> just open the UI)."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=1.5) as r:
            return bool(json.load(r).get("local_only"))
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _open_when_ready(url: str, port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _imageaudit_running(port):
            webbrowser.open(url)
            return
        time.sleep(0.25)


def _fatal(message: str) -> None:
    logging.getLogger("imageaudit.desktop").error(message)
    if sys.platform == "win32":  # a windowed build has no console to print to
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "ImageAudit", 0x10)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass
    else:
        print(message, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ImageAudit", description="ImageAudit local web app")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Preferred port (default {DEFAULT_PORT}).")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    parser.add_argument("--version", action="store_true", help="Print the version and exit.")
    args = parser.parse_args(argv)

    from . import __version__

    if args.version:
        print(f"ImageAudit {__version__}")
        return 0

    log_path = _setup_logging()
    log = logging.getLogger("imageaudit.desktop")
    try:
        if _imageaudit_running(args.port):
            log.info("ImageAudit is already running on port %d; opening the UI", args.port)
            if not args.no_browser:
                webbrowser.open(f"http://{HOST}:{args.port}/")
            return 0

        import uvicorn

        from .api.app import create_app
        from .api.settings import Settings
        from .core.resources import frontend_dir

        if frontend_dir() is None:
            _fatal("The bundled web UI was not found. Rebuild with: scripts\\dev.ps1 build-exe")
            return 2
        port = _pick_port(args.port)
        url = f"http://{HOST}:{port}/"
        settings = Settings.from_env()
        log.info("ImageAudit %s starting on %s (data: %s)", __version__, url, settings.home)
        if not args.no_browser:
            threading.Thread(target=_open_when_ready, args=(url, port), daemon=True).start()
        print(f"ImageAudit {__version__} is running at {url}\nKeep this window open; close it (or press Ctrl+C) to quit.", flush=True)
        server = uvicorn.Server(uvicorn.Config(create_app(settings), host=HOST, port=port,
                                               log_config=None, access_log=False))
        server.run()
        return 0
    except Exception as exc:  # noqa: BLE001 - last-resort reporting for a GUI-less process
        log.exception("fatal error")
        _fatal(f"ImageAudit failed to start: {exc}\n\nDetails: {log_path}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
