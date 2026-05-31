"""Build the official seraphina.glyph archive.

Stages a `dist/glyph-build/seraphina/` tree with `manifest.json` + `code/`
containing the `seraphina` and `glyph` packages, then runs `glyph pack` to
produce `dist/seraphina-<version>.glyph`. Prints the outer-archive SHA256
so the public glyph-index.json can be pinned.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERAPHINA_SRC = ROOT / "seraphina"
GLYPH_SRC = ROOT / "glyph" / "glyph"
# Stage outside OneDrive — its sync handles cause WinError 5 on rmtree.
BUILD_ROOT = (
    Path(os.environ.get("TEMP", tempfile.gettempdir()))
    / f"glyph-build-{os.getpid()}"
    / "seraphina"
)
DIST_DIR = ROOT / "dist"

MAIN_PY = '''"""Seraphina entrypoint when launched via `glyph run seraphina`."""
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import seraphina

print("seraphina " + seraphina.__version__ + " ready (loaded from glyph store)")
print("  code path: " + str(_here))
print("  to launch the CLI, run: python -m seraphina")
'''


def _stage_tree(dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    code = dst / "code"
    code.mkdir(parents=True)

    shutil.copytree(SERAPHINA_SRC, code / "seraphina")
    shutil.copytree(GLYPH_SRC, code / "glyph")

    # Drop bytecode and editor caches
    for p in list(code.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)

    (code / "main.py").write_text(MAIN_PY, encoding="utf-8")


def _read_version() -> str:
    init_text = (SERAPHINA_SRC / "__init__.py").read_text(encoding="utf-8")
    for line in init_text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("could not find __version__ in seraphina/__init__.py")


def _write_manifest(dst: Path, version: str) -> None:
    # sha256 left blank — `glyph pack` recomputes the digest over code/
    manifest = {
        "schema": 3,
        "name": "seraphina",
        "version": version,
        "entrypoint": "code/main.py",
        "sha256": "",
        "dependencies": [],
        "cost_estimate": 0.0,
        "risk_level": "low",
        "description": "Seraphina.AGI - deterministic Roman Wheel Triad core (binary-native install via Glyph)",
        "geometry_refs": [],
        "glyph_type": "core",
        "runtime": "python",
        "requires_glyph": ">=0.10.0",
        "environment": "seraphina",
        "emotion": {"curiosity": 0.7, "calm": 0.8},
    }
    (dst / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    version = _read_version()
    out_path = DIST_DIR / f"seraphina-{version}.glyph"

    print(f"[1/4] staging {BUILD_ROOT}")
    _stage_tree(BUILD_ROOT)

    print(f"[2/4] writing manifest for seraphina=={version}")
    _write_manifest(BUILD_ROOT, version)

    # Add glyph repo root to sys.path so we can import the in-tree glyph cli
    sys.path.insert(0, str(ROOT / "glyph"))
    from glyph.cli import main as glyph_main  # noqa: E402

    print(f"[3/4] packing -> {out_path}")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    rc = glyph_main(["pack", str(BUILD_ROOT), "-o", str(out_path)])
    if rc != 0:
        print(f"glyph pack failed (rc={rc})", file=sys.stderr)
        return rc

    digest = _sha256_file(out_path)
    print(f"[4/4] done")
    print(f"  archive : {out_path}")
    print(f"  size    : {out_path.stat().st_size} bytes")
    print(f"  sha256  : {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
