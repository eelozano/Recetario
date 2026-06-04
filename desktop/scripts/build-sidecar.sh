#!/usr/bin/env bash
#
# Build the Python backend into a single-file binary and stage it where Tauri's
# `externalBin` expects it: src-tauri/binaries/recetario-server-<target-triple>.
#
# Tauri appends the Rust host target triple to the `externalBin` name when it
# bundles, so the staged file must carry that exact suffix. Run this before
# `npm run tauri build` (or `tauri dev`) on each machine/architecture.
#
# Usage:  desktop/scripts/build-sidecar.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(dirname "$SCRIPT_DIR")"
REPO_DIR="$(dirname "$DESKTOP_DIR")"
BACKEND_DIR="$REPO_DIR/backend"

# Resolve the Rust host target triple (e.g. aarch64-apple-darwin).
TRIPLE="$(rustc -vV | sed -n 's/host: //p')"
echo "Target triple: $TRIPLE"

# Prefer the backend venv's PyInstaller; fall back to PATH.
PYI="$BACKEND_DIR/.venv/bin/pyinstaller"
[ -x "$PYI" ] || PYI="pyinstaller"

echo "Freezing backend → recetario-server …"
( cd "$BACKEND_DIR" && "$PYI" packaging/recetario-server.spec --noconfirm \
    --distpath dist --workpath build/pyi )

DEST_DIR="$DESKTOP_DIR/src-tauri/binaries"
mkdir -p "$DEST_DIR"
cp "$BACKEND_DIR/dist/recetario-server" "$DEST_DIR/recetario-server-$TRIPLE"
chmod +x "$DEST_DIR/recetario-server-$TRIPLE"

echo "Staged: $DEST_DIR/recetario-server-$TRIPLE"
