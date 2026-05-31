#!/usr/bin/env bash
# Seraphina.AGI + Glyph - one-shot installer for Git Bash, Linux, and macOS.
#
# Quick install (anywhere with curl + python3):
#   curl -fsSL https://raw.githubusercontent.com/SynerGro-AI/Seraphina.AGIv1.0.8/main/install.sh | bash
#
# Or from a local clone:
#   git clone https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8.git
#   cd Seraphina.AGIv1.0.8
#   bash install.sh
set -euo pipefail

REPO_URL="${SERAPHINA_REPO_URL:-https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8.git}"
REPO_BRANCH="${SERAPHINA_REPO_BRANCH:-main}"

say()  { printf '\033[1;36m[seraphina]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[seraphina]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[seraphina]\033[0m %s\n' "$*" >&2; exit 1; }

# --- locate or clone the repo ------------------------------------------------
if [[ -f "./pyproject.toml" && -d "./glyph" && -d "./seraphina" ]]; then
  REPO_DIR="$(pwd)"
  say "running from local clone: $REPO_DIR"
else
  command -v git >/dev/null 2>&1 || die "git not found - install git first"
  REPO_DIR="${SERAPHINA_INSTALL_DIR:-$HOME/.seraphina-src}"
  if [[ -d "$REPO_DIR/.git" ]]; then
    say "updating existing clone at $REPO_DIR"
    git -C "$REPO_DIR" fetch --quiet origin "$REPO_BRANCH"
    git -C "$REPO_DIR" checkout --quiet "$REPO_BRANCH"
    git -C "$REPO_DIR" pull --quiet --ff-only
  else
    say "cloning $REPO_URL -> $REPO_DIR"
    git clone --quiet --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$REPO_DIR"
  fi
fi
cd "$REPO_DIR"

# --- locate python -----------------------------------------------------------
PY="${SERAPHINA_PYTHON:-}"
if [[ -z "$PY" ]]; then
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
[[ -n "$PY" ]] || die "python 3.9+ not found - install Python first"

PY_VER="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
say "using python: $PY ($PY_VER)"
"$PY" -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' \
  || die "Python 3.9+ required (found $PY_VER)"

# --- ensure pip --------------------------------------------------------------
if ! "$PY" -m pip --version >/dev/null 2>&1; then
  say "bootstrapping pip"
  "$PY" -m ensurepip --upgrade >/dev/null 2>&1 \
    || die "pip not available; install python3-pip"
fi

# --- install glyph + seraphina ----------------------------------------------
PIP_USER_FLAG=""
if [[ -z "${VIRTUAL_ENV:-}" && "${SERAPHINA_SYSTEM_INSTALL:-0}" != "1" ]]; then
  PIP_USER_FLAG="--user"
  say "installing into user site (no venv detected); set SERAPHINA_SYSTEM_INSTALL=1 to override"
fi

say "installing glyph package manager"
"$PY" -m pip install $PIP_USER_FLAG --upgrade --quiet ./glyph

say "installing seraphina core"
"$PY" -m pip install $PIP_USER_FLAG --upgrade --quiet .

# --- bootstrap glyph env -----------------------------------------------------
say "bootstrapping glyph environment"
"$PY" -m glyph bootstrap || warn "glyph bootstrap returned non-zero (continuing)"

# --- PATH hint ---------------------------------------------------------------
USER_BIN="$("$PY" -c 'import sysconfig; print(sysconfig.get_path("scripts","posix_user") if True else "")')" || USER_BIN=""
if [[ -n "$USER_BIN" && ":$PATH:" != *":$USER_BIN:"* && -n "$PIP_USER_FLAG" ]]; then
  warn "add this to your shell profile so 'seraphina' and 'glyph' are on PATH:"
  warn "    export PATH=\"$USER_BIN:\$PATH\""
fi

cat <<EOF

  installed.

    seraphina            # interactive wizard
    seraphina --help
    python -m glyph list

  source: $REPO_DIR
EOF
