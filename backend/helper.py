"""Frozen entry point for the recipe-import helper (Architecture v2, step 4).

PyInstaller analyses this module to build the `recetario-helper` sidecar the
desktop app spawns for URL/video/from-HTML import. It's a thin shim so the spec
has a stable script path; all logic lives in `recetario.cli.import_helper`.
"""

from recetario.cli.import_helper import main

if __name__ == "__main__":
    raise SystemExit(main())
