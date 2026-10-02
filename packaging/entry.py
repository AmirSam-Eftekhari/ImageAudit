"""PyInstaller entry point for ImageAudit.exe (the regular CLI is `imageaudit` / `python -m imageaudit`)."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from imageaudit.desktop import main

    sys.exit(main())
