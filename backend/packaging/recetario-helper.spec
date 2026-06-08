# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — freezes the recipe-import CLI into a single-file binary.

Produces `dist/recetario-helper`, the one-shot sidecar the desktop app spawns to
turn a URL / video / captured page into a structured draft recipe (it prints JSON
to stdout; the TS core persists). Unlike the old server binary this carries **no
database, no Alembic, and no Google/crypto** — import is pure extraction, so we
only bundle the scraping/LLM/video stack. That keeps the binary meaningfully
smaller than the former full backend.

Build:
    cd backend
    .venv/bin/pyinstaller packaging/recetario-helper.spec --noconfirm
"""

import os

from PyInstaller.utils.hooks import collect_all

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))  # noqa: F821

datas = []
binaries = []
hiddenimports = []

# helper.py imports the scraper/LLM/video adapters statically, so PyInstaller
# traces our own package automatically — and that import graph never touches
# sqlalchemy/fastapi/google, keeping the binary lean. The only dynamic imports
# (`anthropic`, `yt_dlp`, inside method bodies) are pulled by collect_all below.

# Third-party packages with data files or dynamic submodule imports. Wrapped so an
# awkward/namespace package never breaks the whole build.
for pkg in (
    "recipe_scrapers",   # URL recipe import
    # mf2py is a *transitive* dep (recipe_scrapers → extruct → mf2py). It loads
    # backcompat-rules/*.json at import time via __file__, so the frozen binary
    # crashes reaching it unless that data dir is bundled. collect_all is
    # per-package, not transitive, hence the explicit entry.
    "mf2py",
    "anthropic",         # LLM fallback + ingredient structuring
    "yt_dlp",            # video-URL import (captions)
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001
        print(f"[recetario-helper.spec] skipping {pkg}: {exc}")

a = Analysis(
    [os.path.join(backend_dir, "helper.py")],
    pathex=[os.path.join(backend_dir, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="recetario-helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
)
