# PyInstaller spec for the single-file build. Run via packaging/build_exe.ps1 (or build_bundle.py).
# Nothing here modifies the source tree: the frontend export directory is only *read*.
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is injected by PyInstaller
UI = Path(os.environ.get("IMAGEAUDIT_UI_DIR", ROOT / "frontend" / ".next-export"))
if not (UI / "index.html").is_file():
    raise SystemExit(f"Static frontend export not found at {UI}. Build it first (see packaging/build_exe.ps1).")

datas = [(str(UI), "frontend")]  # read-only UI assets -> <extraction dir>/frontend
datas += collect_data_files("imageaudit")  # report templates (reports/templates/*.j2)

hiddenimports = (
    collect_submodules("uvicorn")  # uvicorn picks loops/protocols dynamically
    + collect_submodules("imageaudit")
    + ["multipart", "python_multipart", "email.mime.multipart"]
)

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "backend")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "mypy", "ruff", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz, a.scripts, a.binaries, a.datas, [],
    name="ImageAudit",
    debug=False,
    strip=False,
    upx=False,
    # A console window is kept on purpose: the server has no other window, so the console is how a
    # user sees the URL, quits (close the window / Ctrl+C) and reads startup errors.
    console=True,
)
