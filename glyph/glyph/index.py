"""Local filesystem GlyphIndex — analogous to PyPI but offline and native.

Default layout (v0.2 — Seraphina-native, NOT site-packages):
    ~/.seraphina/lib/glyph/
        packages/<name>/<version>/        <- unpacked .glyph package
        packages/<name>/<version>/.glyph-meta/   <- emotional state, usage, trust
        index/<name>.json                 <- {"versions": ["0.1.0", ...]}
        cache/                            <- raw .glyph archives
        env.json                          <- environment metadata (created by bootstrap)
"""
from __future__ import annotations
import json
import os
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get(
    "GLYPH_HOME",
    Path.home() / ".seraphina" / "lib" / "glyph",
))


def _resolve_root() -> Path:
    """Resolve the GLYPH_HOME root *now*, honoring runtime env mutations."""
    env = os.environ.get("GLYPH_HOME")
    if env:
        return Path(env)
    return Path.home() / ".seraphina" / "lib" / "glyph"


class GlyphIndex:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else _resolve_root()
        self.store = self.root / "packages"
        self.index = self.root / "index"
        self.cache = self.root / "cache"
        self.env_file = self.root / "env.json"

    def bootstrap(self) -> None:
        for p in (self.store, self.index, self.cache):
            p.mkdir(parents=True, exist_ok=True)
        if not self.env_file.exists():
            from . import __version__
            self.env_file.write_text(json.dumps({
                "environment": "seraphina",
                "glyph_runtime_version": __version__,
                "schema": 3,
            }, indent=2), encoding="utf-8")

    # ---- version listing ---------------------------------------------------
    def versions(self, name: str) -> list[str]:
        f = self.index / f"{name}.json"
        if not f.exists():
            return []
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return list(data.get("versions", []))
        except (json.JSONDecodeError, OSError):
            return []

    def is_installed(self, name: str, version: str) -> bool:
        return (self.store / name / version / "manifest.json").exists()

    def location(self, name: str, version: str) -> Path:
        return self.store / name / version

    def meta_dir(self, name: str, version: str) -> Path:
        return self.location(name, version) / ".glyph-meta"

    def all_installed(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not self.store.exists():
            return out
        for name_dir in sorted(self.store.iterdir()):
            if not name_dir.is_dir():
                continue
            for ver_dir in sorted(name_dir.iterdir()):
                if (ver_dir / "manifest.json").exists():
                    out.append((name_dir.name, ver_dir.name))
        return out

    # ---- mutations ---------------------------------------------------------
    def record_installed(self, name: str, version: str) -> None:
        self.index.mkdir(parents=True, exist_ok=True)
        f = self.index / f"{name}.json"
        versions = self.versions(name)
        if version not in versions:
            versions.append(version)
            versions.sort()
        f.write_text(json.dumps({"versions": versions}, indent=2), encoding="utf-8")

    def record_removed(self, name: str, version: str) -> None:
        f = self.index / f"{name}.json"
        if not f.exists():
            return
        versions = [v for v in self.versions(name) if v != version]
        if versions:
            f.write_text(json.dumps({"versions": versions}, indent=2), encoding="utf-8")
        else:
            f.unlink(missing_ok=True)
