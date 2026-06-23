#!/usr/bin/env bash
#
# install.sh — install the `exrate` CLI globally for the current user.
#
# What it does: symlinks exrate.py into ~/.local/bin/exrate (which is on PATH on
# this machine). A symlink means edits to exrate.py take effect immediately with
# no reinstall. Run `./install.sh` from the project directory.
#
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/exrate.py"
BIN_DIR="${HOME}/.local/bin"
TARGET="${BIN_DIR}/exrate"

mkdir -p "${BIN_DIR}"
chmod +x "${SRC}"
ln -sf "${SRC}" "${TARGET}"

echo "Installed: ${TARGET} -> ${SRC}"
echo "Run: exrate --help"
