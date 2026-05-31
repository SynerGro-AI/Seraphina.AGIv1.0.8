"""Tiny version-pinned dependency resolver.

Supported spec grammar (intentionally minimal for v0.1):
    "*"            — any version
    "==X.Y.Z"      — exact
    ">=X.Y.Z"      — minimum (inclusive)
    "<X.Y.Z"       — strict maximum
    ">=A,<B"       — comma-joined conjunction of the above
No backtracking; conflicts raise ResolutionError.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Iterable

from .manifest import Manifest, Dependency


class ResolutionError(Exception):
    pass


_VTUPLE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _vtuple(v: str) -> tuple[int, int, int]:
    m = _VTUPLE_RE.match(v)
    if not m:
        raise ResolutionError(f"unparseable version: {v!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _match_one(version: str, atom: str) -> bool:
    atom = atom.strip()
    if atom in ("", "*"):
        return True
    v = _vtuple(version)
    for op in ("==", ">=", "<="):
        if atom.startswith(op):
            target = _vtuple(atom[len(op):].strip())
            if op == "==":
                return v == target
            if op == ">=":
                return v >= target
            if op == "<=":
                return v <= target
    if atom.startswith(">"):
        return v > _vtuple(atom[1:].strip())
    if atom.startswith("<"):
        return v < _vtuple(atom[1:].strip())
    raise ResolutionError(f"unsupported spec atom: {atom!r}")


def spec_matches(version: str, spec: str) -> bool:
    return all(_match_one(version, atom) for atom in spec.split(","))


@dataclass(frozen=True)
class ResolvedDep:
    name: str
    version: str


class DependencyResolver:
    """Resolves dependencies against a callable that returns available versions.

    `available(name) -> list[str]` should return version strings already
    installed locally (or known to the GlyphIndex).
    """

    def __init__(self, available):
        self._available = available

    def resolve(self, manifest: Manifest) -> list[ResolvedDep]:
        resolved: dict[str, str] = {}
        self._resolve_into(manifest.dependencies, resolved, chain=(manifest.name,))
        return [ResolvedDep(n, v) for n, v in resolved.items()]

    def _resolve_into(self, deps: Iterable[Dependency],
                      resolved: dict[str, str],
                      chain: tuple[str, ...]) -> None:
        for dep in deps:
            if dep.name in chain:
                raise ResolutionError(
                    f"circular dependency: {' -> '.join(chain + (dep.name,))}"
                )
            versions = list(self._available(dep.name) or [])
            if not versions:
                raise ResolutionError(
                    f"no candidates available for {dep.name!r} (required by {chain[-1]})"
                )
            matches = [v for v in versions if spec_matches(v, dep.spec)]
            if not matches:
                raise ResolutionError(
                    f"no version of {dep.name!r} satisfies {dep.spec!r} "
                    f"(have: {', '.join(versions)})"
                )
            # pick highest matching
            chosen = max(matches, key=_vtuple)
            prev = resolved.get(dep.name)
            if prev and prev != chosen:
                raise ResolutionError(
                    f"version conflict for {dep.name!r}: {prev} vs {chosen}"
                )
            resolved[dep.name] = chosen
