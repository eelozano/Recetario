# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — freezes server.py into a single-file backend binary.

Produces `dist/recetario-server`, the self-contained sidecar Tauri launches. It
bundles the Alembic migration scripts (so the binary self-migrates the user's DB)
and the data-bearing third-party packages the running app needs.

Build:
    cd backend
    .venv/bin/pyinstaller packaging/recetario-server.spec --noconfirm

All optional features are bundled, including `yt_dlp` (video ingestion). It and
its transitive deps add ~9 MB (the 1k+ extractor modules compress well in the
PYZ), which is a fair price for "import from a video URL" working in the shipped
app. Note: extracting audio for ASR fallback would still require a system ffmpeg;
the captions-first path does not.
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))  # noqa: F821

datas = []
binaries = []
hiddenimports = []

# 1) Bundle the Alembic migration scripts so the frozen binary can upgrade the DB
#    to head on startup (server.py resolves them under sys._MEIPASS).
datas.append((os.path.join(backend_dir, "alembic"), "alembic"))

# 2) Our own package: the lazy adapter imports (LLM/FDC/Google/security) live
#    inside function bodies, so collect every submodule explicitly.
hiddenimports += collect_submodules("recetario")

# 3) Server internals PyInstaller's static analysis can miss.
hiddenimports += collect_submodules("uvicorn")

# 4) Third-party packages with data files or dynamic submodule imports. Wrapped
#    so an awkward/namespace package never breaks the whole build.
for pkg in (
    "recipe_scrapers",   # URL recipe import
    "anthropic",         # LLM enrichment
    "googleapiclient",   # Google Tasks export
    "google.auth",
    "google.oauth2",
    "google_auth_oauthlib",
    "cryptography",      # encrypted token store
    "yt_dlp",            # video-URL recipe ingestion (captions)
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001
        print(f"[recetario-server.spec] skipping {pkg}: {exc}")

a = Analysis(
    [os.path.join(backend_dir, "server.py")],
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
    name="recetario-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
)
