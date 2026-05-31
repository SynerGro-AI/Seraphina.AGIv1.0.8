"""Glyph manifest schema + loader.

A `.glyph` package is a ZIP archive containing:
    manifest.json   — this schema
    code/...        — Python source tree, entrypoint is manifest['entrypoint']
    (optional) geometry/...  — OctaLang geometry refs (see seraphina-glyph/)

Schema (v1):
{
  "schema": 1,
  "name":  "<identifier>",
  "version": "<semver-ish, e.g. 0.1.0>",
  "entrypoint": "code/main.py",
  "sha256": "<hex digest of code/ tree, computed by IntegrityChecker>",
  "dependencies": [ {"name": "...", "spec": "==1.2.3" | ">=1.0.0" | "*"} ],
  "cost_estimate": 0.0,          # arbitrary units, used by emotional gate
  "risk_level": "low|medium|high",
  "description": "...",
  "geometry_refs": []            # optional list of glyph file names
}
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    """Manifest is missing required fields or has invalid values."""


_NAME_RE = re.compile(r"^[a-z][a-z0-9_\-]{0,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([\-+][\w.\-]+)?$")
_VALID_RISK = {"low", "medium", "high"}


@dataclass
class Dependency:
    name: str
    spec: str = "*"

    def to_dict(self) -> dict:
        return {"name": self.name, "spec": self.spec}

    @classmethod
    def from_dict(cls, d: dict) -> "Dependency":
        if "name" not in d:
            raise ManifestError("dependency missing 'name'")
        return cls(name=str(d["name"]), spec=str(d.get("spec", "*")))


_VALID_GLYPH_TYPE = {"native", "bridge", "core", "experimental"}
_VALID_RUNTIME = {"python", "octalang", "wasm", "shell"}


@dataclass
class Manifest:
    name: str
    version: str
    entrypoint: str = "code/main.py"
    sha256: str = ""
    dependencies: list[Dependency] = field(default_factory=list)
    cost_estimate: float = 0.0
    risk_level: str = "low"
    description: str = ""
    geometry_refs: list[str] = field(default_factory=list)
    # --- v2 native-identity fields ---
    glyph_type: str = "native"          # native | bridge | core | experimental
    runtime: str = "python"             # python | octalang | wasm | shell
    requires_glyph: str = "*"           # version spec on the Glyph runtime itself
    environment: str = "seraphina"      # logical environment / namespace
    schema: int = 3                     # v0.4 bumped to 3; loader still accepts 2
    emotion: dict = field(default_factory=dict)   # v0.6: joy/fear/curiosity/... weights

    def validate(self) -> None:
        if not _NAME_RE.match(self.name or ""):
            raise ManifestError(f"invalid name: {self.name!r}")
        if not _VERSION_RE.match(self.version or ""):
            raise ManifestError(f"invalid version: {self.version!r}")
        if not self.entrypoint:
            raise ManifestError("entrypoint is required")
        if self.risk_level not in _VALID_RISK:
            raise ManifestError(f"risk_level must be one of {_VALID_RISK}")
        if self.cost_estimate < 0:
            raise ManifestError("cost_estimate must be >= 0")
        if self.glyph_type not in _VALID_GLYPH_TYPE:
            raise ManifestError(f"glyph_type must be one of {_VALID_GLYPH_TYPE}")
        if self.runtime not in _VALID_RUNTIME:
            raise ManifestError(f"runtime must be one of {_VALID_RUNTIME}")
        if not self.environment:
            raise ManifestError("environment is required")
        if self.schema not in (2, 3):
            raise ManifestError(f"schema must be 2 or 3, got {self.schema!r}")
        if not isinstance(self.emotion, dict):
            raise ManifestError("emotion must be an object/dict")
        for k, v in self.emotion.items():
            if not isinstance(k, str) or not isinstance(v, (int, float)):
                raise ManifestError(f"emotion entries must be str->number, got {k!r}: {v!r}")
            if not (0.0 <= float(v) <= 1.0):
                raise ManifestError(f"emotion[{k!r}] must be in [0.0, 1.0], got {v!r}")
        for dep in self.dependencies:
            if not _NAME_RE.match(dep.name):
                raise ManifestError(f"invalid dep name: {dep.name!r}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["dependencies"] = [dep.to_dict() if isinstance(dep, Dependency) else dep
                             for dep in self.dependencies]
        return d

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        if not isinstance(d, dict):
            raise ManifestError("manifest must be a JSON object")
        try:
            deps = [Dependency.from_dict(x) for x in d.get("dependencies", [])]
            m = cls(
                name=d["name"],
                version=d["version"],
                entrypoint=d.get("entrypoint", "code/main.py"),
                sha256=d.get("sha256", ""),
                dependencies=deps,
                cost_estimate=float(d.get("cost_estimate", 0.0)),
                risk_level=d.get("risk_level", "low"),
                description=d.get("description", ""),
                geometry_refs=list(d.get("geometry_refs", [])),
                glyph_type=d.get("glyph_type", "native"),
                runtime=d.get("runtime", "python"),
                requires_glyph=d.get("requires_glyph", "*"),
                environment=d.get("environment", "seraphina"),
                schema=int(d.get("schema", 2)),
                emotion=dict(d.get("emotion", {}) or {}),
            )
        except KeyError as e:
            raise ManifestError(f"missing required field: {e.args[0]}") from None
        m.validate()
        return m

    @classmethod
    def from_path(cls, path: str | Path) -> "Manifest":
        p = Path(path)
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
