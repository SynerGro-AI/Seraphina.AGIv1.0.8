"""`glyph doctor` — environment health check.

Verifies the Glyph filesystem layout, the env.json file, that every installed
package has a readable manifest, and that each package's ``requires_glyph``
spec is satisfied by the current runtime. Returns a structured report; the
CLI command renders it for humans and exits non-zero on any failure.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Optional

from . import __version__
from .index import GlyphIndex
from .manifest import Manifest, ManifestError
from .resolution import spec_matches


@dataclass
class Finding:
    level: str   # "ok" | "warn" | "error"
    code: str
    message: str


@dataclass
class DoctorReport:
    root: Path
    runtime_version: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.level == "error" for f in self.findings)


def check(root: Optional[Path] = None) -> DoctorReport:
    idx = GlyphIndex(root) if root is not None else GlyphIndex()
    report = DoctorReport(root=idx.root, runtime_version=__version__)

    if not idx.root.exists():
        report.findings.append(Finding(
            "error", "no-root",
            f"GLYPH_HOME does not exist: {idx.root} (run `glyph bootstrap`)"))
        return report

    for label, p in (("packages", idx.store), ("index", idx.index), ("cache", idx.cache)):
        if not p.is_dir():
            report.findings.append(Finding(
                "error", f"missing-{label}", f"missing {label} directory: {p}"))

    if not idx.env_file.is_file():
        report.findings.append(Finding(
            "error", "no-env", f"env.json missing: {idx.env_file}"))
    else:
        try:
            env = json.loads(idx.env_file.read_text("utf-8"))
            if env.get("environment") != "seraphina":
                report.findings.append(Finding(
                    "warn", "env-name",
                    f"env.json environment != 'seraphina': {env.get('environment')!r}"))
        except (json.JSONDecodeError, OSError) as e:
            report.findings.append(Finding(
                "error", "bad-env", f"env.json unreadable: {e}"))

    installed = idx.all_installed()
    seen = 0
    on_disk_pairs: set[tuple[str, str]] = set()
    for name, version in installed:
        loc = idx.location(name, version)
        mpath = loc / "manifest.json"
        if not mpath.is_file():
            report.findings.append(Finding(
                "error", "orphan",
                f"index lists {name}=={version} but manifest.json missing at {mpath}"))
            continue
        on_disk_pairs.add((name, version))
        try:
            m = Manifest.from_path(mpath)
        except (ManifestError, json.JSONDecodeError, OSError) as e:
            report.findings.append(Finding(
                "error", "bad-manifest",
                f"{name}=={version}: invalid manifest ({e})"))
            continue
        seen += 1
        if m.requires_glyph and m.requires_glyph != "*":
            try:
                ok = spec_matches(__version__, m.requires_glyph)
            except Exception as e:  # noqa: BLE001
                ok = False
                report.findings.append(Finding(
                    "warn", "bad-spec",
                    f"{name}=={version}: requires_glyph spec invalid ({e})"))
                continue
            if not ok:
                report.findings.append(Finding(
                    "error", "runtime-mismatch",
                    f"{name}=={version}: requires_glyph {m.requires_glyph!r} "
                    f"not satisfied by runtime {__version__}"))

    # Detect packages on disk not recorded in the index.
    if idx.store.exists():
        recorded = set(installed)
        for name_dir in idx.store.iterdir():
            if not name_dir.is_dir():
                continue
            for ver_dir in name_dir.iterdir():
                if (ver_dir / "manifest.json").is_file():
                    pair = (name_dir.name, ver_dir.name)
                    if pair not in recorded:
                        report.findings.append(Finding(
                            "warn", "unindexed",
                            f"{pair[0]}=={pair[1]} present on disk but not in index"))

    # Detect index entries with no package directory on disk (true orphans).
    if idx.index.exists():
        for f in idx.index.glob("*.json"):
            try:
                data = json.loads(f.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            name = f.stem
            for v in data.get("versions", []):
                if (name, v) not in on_disk_pairs and (name, v) in installed:
                    pass  # handled above
                elif (name, v) not in on_disk_pairs:
                    # listed in index but missing on disk
                    report.findings.append(Finding(
                        "error", "orphan",
                        f"index lists {name}=={v} but no manifest at {idx.location(name, v) / 'manifest.json'}"))

    report.findings.append(Finding(
        "ok", "summary",
        f"{seen} healthy package(s) at {idx.root}"))
    return report
