"""High-level install/uninstall/list/freeze operations."""
from __future__ import annotations
import datetime as _dt
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .manifest import Manifest, ManifestError
from .index import GlyphIndex
from .integrity import IntegrityChecker, IntegrityError
from .resolution import DependencyResolver, ResolutionError, spec_matches
from .gate import get_gate, GateDecision


class InstallError(Exception):
    pass


@dataclass
class InstallResult:
    name: str
    version: str
    location: Path
    gate: GateDecision


# --- helpers ---------------------------------------------------------------

def _read_manifest_from_zip(glyph_path: Path) -> Manifest:
    with zipfile.ZipFile(glyph_path, "r") as zf:
        try:
            raw = zf.read("manifest.json")
        except KeyError:
            raise InstallError(f"{glyph_path.name}: missing manifest.json")
    try:
        return Manifest.from_dict(json.loads(raw.decode("utf-8")))
    except (json.JSONDecodeError, ManifestError) as e:
        raise InstallError(f"{glyph_path.name}: invalid manifest ({e})")


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Zip-slip-safe extraction."""
    dest_resolved = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        try:
            target.relative_to(dest_resolved)
        except ValueError:
            raise InstallError(f"unsafe path in archive: {member.filename!r}")
    zf.extractall(dest)


# --- public API ------------------------------------------------------------

def install(glyph_path: str | Path,
            *, index: Optional[GlyphIndex] = None,
            force: bool = False) -> InstallResult:
    """Install a .glyph archive into the local GlyphIndex."""
    src = Path(glyph_path)
    if not src.is_file():
        raise InstallError(f"not a file: {src}")

    idx = index or GlyphIndex()
    idx.bootstrap()

    manifest = _read_manifest_from_zip(src)

    # 1. integrity over code/ subtree
    actual = IntegrityChecker.digest_zip_subtree(src, "code/")
    if manifest.sha256:
        try:
            IntegrityChecker.verify(manifest.sha256, actual)
        except IntegrityError as e:
            raise InstallError(f"integrity check failed: {e}")
    else:
        manifest.sha256 = actual  # accept-and-record on first install

    # 2. runtime compatibility (requires_glyph)
    from . import __version__ as _glyph_runtime
    if not spec_matches(_glyph_runtime, manifest.requires_glyph):
        raise InstallError(
            f"glyph runtime mismatch: package requires {manifest.requires_glyph!r}, "
            f"have {_glyph_runtime}"
        )

    # 3. emotional gate
    decision = get_gate()(manifest)
    # Append a ledger entry for every gate decision (approve OR deny).
    try:
        from . import ledger as _ledger
        _ledger.append({
            "event": "gate",
            "name": manifest.name,
            "version": manifest.version,
            "approved": bool(decision),
            "reason": decision.reason,
            "risk": manifest.risk_level,
            "cost": manifest.cost_estimate,
            "emotion": dict(manifest.emotion),
        }, root=idx.root)
    except Exception:  # noqa: BLE001 — ledger must never block install
        pass
    if not decision:
        raise InstallError(f"emotional gate denied install: {decision.reason}")

    # 4. dependency resolution against what's already installed
    resolver = DependencyResolver(available=idx.versions)
    try:
        resolver.resolve(manifest)
    except ResolutionError as e:
        raise InstallError(f"dependency resolution failed: {e}")

    # 5. unpack to store
    target = idx.location(manifest.name, manifest.version)
    if target.exists():
        if not force:
            raise InstallError(
                f"already installed: {manifest.name}=={manifest.version} "
                f"(use force=True to reinstall)"
            )
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(src, "r") as zf:
            _safe_extract(zf, Path(td))
        for item in Path(td).iterdir():
            shutil.move(str(item), str(target / item.name))

    # 6. record + persist updated manifest (with computed sha if needed)
    (target / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")
    idx.record_installed(manifest.name, manifest.version)

    # 7. write native .glyph-meta/ sidecar (identity, trust, install record)
    meta = target / ".glyph-meta"
    meta.mkdir(exist_ok=True)
    _now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    (meta / "install.json").write_text(json.dumps({
        "installed_at": _now,
        "glyph_runtime": _glyph_runtime,
        "environment": manifest.environment,
        "glyph_type": manifest.glyph_type,
        "runtime": manifest.runtime,
        "gate_reason": decision.reason,
        "sha256": manifest.sha256,
    }, indent=2), encoding="utf-8")
    if not (meta / "trust.json").exists():
        (meta / "trust.json").write_text(json.dumps({
            "score": 0.5,
            "updated": _now,
        }, indent=2), encoding="utf-8")

    return InstallResult(manifest.name, manifest.version, target, decision)


def uninstall(name: str, version: Optional[str] = None,
              *, index: Optional[GlyphIndex] = None) -> list[tuple[str, str]]:
    """Remove one version (or all versions if `version` is None)."""
    idx = index or GlyphIndex()
    if not idx.store.exists():
        return []
    removed: list[tuple[str, str]] = []
    base = idx.store / name
    if not base.exists():
        return []
    targets = [base / version] if version else [p for p in base.iterdir() if p.is_dir()]
    for t in targets:
        if not t.exists():
            continue
        v = t.name
        shutil.rmtree(t)
        idx.record_removed(name, v)
        removed.append((name, v))
    if base.exists() and not any(base.iterdir()):
        base.rmdir()
    return removed


def list_installed(index: Optional[GlyphIndex] = None) -> list[tuple[str, str]]:
    return (index or GlyphIndex()).all_installed()


def freeze(index: Optional[GlyphIndex] = None) -> str:
    """pip-freeze style output: `name==version` per line, sorted."""
    return "\n".join(f"{n}=={v}" for n, v in list_installed(index))
