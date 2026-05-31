"""`glyph bootstrap` — initialize Seraphina's Glyph environment.

Creates the native filesystem layout, writes env.json, and self-registers
Glyph itself as a `core` package at the current runtime version. After this
runs, no further pip interaction is required to manage glyphs.

Can also be invoked as a standalone script:
    python glyph-bootstrap.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from . import __version__
from .index import GlyphIndex, DEFAULT_ROOT


def bootstrap(root: Path | None = None, *, verbose: bool = True) -> dict:
    idx = GlyphIndex(root)
    idx.bootstrap()

    # self-register the Glyph runtime as a core package (no code, just identity).
    core_name, core_version = "glyph", __version__
    core_dir = idx.location(core_name, core_version)
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / ".glyph-meta").mkdir(exist_ok=True)
    manifest = {
        "schema": 3,
        "name": core_name,
        "version": core_version,
        "entrypoint": "code/main.py",
        "sha256": "",
        "dependencies": [],
        "cost_estimate": 0.0,
        "risk_level": "low",
        "description": "Glyph runtime self-registration (core)",
        "geometry_refs": [],
        "glyph_type": "core",
        "runtime": "python",
        "requires_glyph": "*",
        "environment": "seraphina",
    }
    (core_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    idx.record_installed(core_name, core_version)

    summary = {
        "root": str(idx.root),
        "packages": str(idx.store),
        "env_file": str(idx.env_file),
        "glyph_runtime_version": __version__,
        "self_registered": f"{core_name}=={core_version}",
    }
    if verbose:
        print("Glyph environment bootstrapped:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
        print("\nYou can now use `glyph install <pkg.glyph>` — pip is no longer required.")
    return summary


if __name__ == "__main__":
    bootstrap()
    sys.exit(0)
