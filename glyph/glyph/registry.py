"""Glyph registry — read-only view of installed glyphs.

Used by Seraphina-side integration (and `glyph doctor`) to discover every
installed glyph package without importing or executing its code. Lazy by
design: nothing scans the filesystem until ``discover()`` is called.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Optional

from .index import GlyphIndex, DEFAULT_ROOT
from .manifest import Manifest, ManifestError


@dataclass(frozen=True)
class GlyphRecord:
    name: str
    version: str
    location: Path
    manifest: Manifest

    @property
    def meta_dir(self) -> Path:
        return self.location / ".glyph-meta"

    def signals(self) -> list[dict]:
        """Read this glyph's signals.jsonl (empty list if none)."""
        f = self.meta_dir / "signals.jsonl"
        if not f.exists():
            return []
        out: list[dict] = []
        for line in f.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


def discover(root: Optional[Path] = None) -> dict[str, GlyphRecord]:
    """Return a name->GlyphRecord map for the highest installed version of each glyph.

    Skips packages with unreadable/invalid manifests rather than raising.
    """
    if root is None:
        env = os.environ.get("GLYPH_HOME")
        if env:
            root = Path(env)
    idx = GlyphIndex(root) if root is not None else GlyphIndex()
    found: dict[str, GlyphRecord] = {}
    for name, version in idx.all_installed():
        loc = idx.location(name, version)
        mpath = loc / "manifest.json"
        try:
            m = Manifest.from_path(mpath)
        except (ManifestError, json.JSONDecodeError, OSError):
            continue
        prior = found.get(name)
        if prior is None or _semver_key(version) > _semver_key(prior.version):
            found[name] = GlyphRecord(name=name, version=version,
                                      location=loc, manifest=m)
    return found


def _semver_key(v: str) -> tuple:
    parts = v.split(".")
    out: list[int] = []
    for p in parts[:3]:
        try:
            out.append(int(p.split("-")[0].split("+")[0]))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)
