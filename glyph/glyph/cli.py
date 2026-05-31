"""CLI entry point — `glyph <command>`. Mirrors pip's UX where sensible.

Commands:
    install <path.glyph> [--force]
    uninstall <name> [--version V]
    list
    freeze
    show <name>
    pack <src_dir> -o <out.glyph>     # bundle a project into .glyph
"""
from __future__ import annotations
import argparse
import json
import sys
import zipfile
from pathlib import Path

from . import __version__
from .manifest import Manifest, ManifestError
from .index import GlyphIndex
from .integrity import IntegrityChecker
from .operations import install, uninstall, list_installed, freeze, InstallError
from .bootstrap import bootstrap as _bootstrap
from .generator import (
    compile_file as _gl_compile_file,
    compile_tree as _gl_compile_tree,
    parse as _gl_parse,
    format_gl as _gl_format,
    GLSyntaxError,
)
from .doctor import check as _doctor_check
from . import ledger as _ledger


_LEVEL_PREFIX = {"ok": "  ok  ", "warn": "  warn", "error": " error"}


def _cmd_history(args) -> int:
    root = Path(args.root) if args.root else None
    entries = _ledger.read(root=root, name=args.name, limit=args.limit)
    if not entries:
        print("(no ledger entries)")
        return 0
    for rec in entries:
        ts = rec.get("ts", "?")
        if "approved" in rec or "version" in rec:
            verdict = "approved" if rec.get("approved") else "denied  "
            name = rec.get("name", "?")
            ver = rec.get("version", "?")
            reason = rec.get("reason", "")
            print(f"{ts}  [{verdict}] {name}=={ver}  {reason}")
        else:
            evt = rec.get("event", "event")
            name = rec.get("name", "?")
            extras = " ".join(
                f"{k}={rec[k]}" for k in ("url", "method", "payload_keys")
                if k in rec
            )
            print(f"{ts}  [{evt:<11}] {name}  {extras}")
    return 0


def _cmd_remote_add(args) -> int:
    from . import remote as _r
    h = _r.RemoteHost(
        name=args.name, base_url=args.base_url, auth=args.auth,
        token=args.token, header_name=args.header_name,
        default_path=args.default_path, method=args.method,
        timeout=args.timeout,
    )
    try:
        p = _r.register(h)
    except _r.RemoteError as e:
        print(f"glyph: {e}", file=sys.stderr)
        return 1
    print(f"Registered remote {h.name!r} -> {h.base_url}")
    print(f"  config: {p}")
    return 0


def _cmd_remote_list(_args) -> int:
    from . import remote as _r
    hosts = _r.list_remotes()
    if not hosts:
        print("(no remotes registered)")
        return 0
    width = max(len(h.name) for h in hosts)
    for h in hosts:
        auth = h.auth if h.auth == "none" else f"{h.auth}(***)"
        print(f"{h.name:<{width}}  {h.method:<5} {h.base_url}{h.default_path}   auth={auth}")
    return 0


def _cmd_remote_remove(args) -> int:
    from . import remote as _r
    if not _r.unregister(args.name):
        print(f"glyph: no such remote: {args.name}", file=sys.stderr)
        return 1
    print(f"Removed remote {args.name!r}")
    return 0


def _cmd_remote_call(args) -> int:
    from . import remote as _r
    if args.json_payload is not None:
        try:
            payload = json.loads(args.json_payload)
        except json.JSONDecodeError as e:
            print(f"glyph: invalid --json: {e}", file=sys.stderr)
            return 1
    elif args.prompt is not None:
        payload = {"prompt": args.prompt}
    else:
        payload = {}
    try:
        resp = _r.call(args.name, payload, path=args.path, method=args.method)
    except _r.RemoteError as e:
        print(f"glyph: remote call failed: {e}", file=sys.stderr)
        return 1
    print(f"status: {resp.status}")
    if resp.json is not None:
        print(json.dumps(resp.json, indent=2))
    else:
        try:
            print(resp.body.decode("utf-8"))
        except UnicodeDecodeError:
            print(f"<{len(resp.body)} bytes binary>")
    return 0 if resp.ok() else 1


def _cmd_forge(args) -> int:
    """Rule-24 binary-native forge: geometry params -> real .wasm glyph."""
    from . import rule24 as _r24
    try:
        geom = _r24.Geometry(
            sides=args.sides, points=args.points, dots=args.dots,
            intersections=args.intersections, spirals=args.spirals,
        )
    except ValueError as e:
        print(f"glyph: invalid geometry: {e}", file=sys.stderr)
        return 1
    res = _r24.forge(geom)
    print(f"Rule-24:  sides={geom.sides}*10 + points={geom.points}"
          f" + dots={geom.dots} + intersections={geom.intersections}"
          f" + spirals={geom.spirals}*8")
    print(f"  value:  {res.value}")
    print(f"  binary: {res.binary}")
    print(f"  wasm:   {len(res.wasm)} bytes")

    # Build a package tree in a temp dir (or user-provided source dir).
    import tempfile, shutil
    if args.source:
        pkg_dir = Path(args.source).resolve()
        if pkg_dir.exists():
            print(f"glyph: --source path already exists: {pkg_dir}", file=sys.stderr)
            return 1
        pkg_dir.mkdir(parents=True)
        _tmp_ctx = None
    else:
        _tmp_ctx = tempfile.TemporaryDirectory()
        pkg_dir = Path(_tmp_ctx.name) / args.name
        pkg_dir.mkdir()
    try:
        (pkg_dir / "code").mkdir()
        (pkg_dir / "code" / "main.wasm").write_bytes(res.wasm)
        (pkg_dir / "manifest.json").write_text(json.dumps({
            "schema": 3,
            "name": args.name,
            "version": args.version,
            "entrypoint": "code/main.wasm",
            "cost_estimate": 0.0,
            "risk_level": "low",
            "glyph_type": "native",
            "runtime": "wasm",
            "environment": "seraphina",
            "requires_glyph": ">=0.8.0",
            "description": f"Rule-24 binary-native glyph (value={res.value})",
        }, indent=2), encoding="utf-8")
        out = Path(args.output or f"{args.name}.glyph").resolve()
        # Reuse pack logic
        pack_ns = argparse.Namespace(src=str(pkg_dir), output=str(out))
        rc = _cmd_pack(pack_ns)
        if rc != 0:
            return rc
    finally:
        if _tmp_ctx is not None:
            _tmp_ctx.cleanup()
    return 0


def _cmd_run(args) -> int:
    idx = GlyphIndex()
    versions = idx.versions(args.name)
    if not versions:
        print(f"glyph: not installed: {args.name}", file=sys.stderr)
        return 1
    v = args.version or versions[-1]
    loc = idx.location(args.name, v)
    mpath = loc / "manifest.json"
    if not mpath.is_file():
        print(f"glyph: corrupted install (missing manifest): {loc}", file=sys.stderr)
        return 1
    m = Manifest.from_path(mpath)
    print(f"Running {m.name}=={m.version}  runtime={m.runtime}")
    if m.runtime == "wasm":
        from . import wasm as _wasm
        ep_rel = m.entrypoint[len("code/"):] if m.entrypoint.startswith("code/") else m.entrypoint
        try:
            inst = _wasm.load_module(loc / "code", ep_rel, host=args.host)
        except _wasm.WasmError as e:
            print(f"glyph: wasm load failed: {e}", file=sys.stderr)
            return 1
        print(f"  host: {inst.host}")
        print(f"  exports: {', '.join(inst.info.exports) or '(none)'}")
        if args.export:
            try:
                int_args = [int(a) for a in args.arg]
            except ValueError:
                print("glyph: --arg values must be integers", file=sys.stderr)
                return 1
            try:
                result = inst.invoke(args.export, *int_args)
            except _wasm.WasmError as e:
                print(f"glyph: wasm invoke failed: {e}", file=sys.stderr)
                return 1
            print(f"  invoke {args.export}({', '.join(args.arg)}) = {result!r}")
        return 0
    if m.runtime in ("python", "octalang"):
        from .sandbox import load_entrypoint, SandboxError
        try:
            mod = load_entrypoint(loc, m.entrypoint, module_name=f"glyph_run_{m.name}")
        except SandboxError as e:
            print(f"glyph: run failed: {e}", file=sys.stderr)
            return 1
        print(f"  loaded module: {mod.__name__}")
        return 0
    print(f"glyph: cannot run runtime={m.runtime!r}", file=sys.stderr)
    return 1


def _cmd_doctor(args) -> int:
    root = Path(args.root) if args.root else None
    report = _doctor_check(root)
    print(f"glyph doctor  (runtime {report.runtime_version})")
    print(f"  root: {report.root}")
    for f in report.findings:
        prefix = _LEVEL_PREFIX.get(f.level, f.level)
        print(f"  [{prefix}] {f.code}: {f.message}")
    return 1 if report.has_errors else 0


def _cmd_fmt(args) -> int:
    src = Path(args.src)
    if src.is_dir():
        files = sorted(src.rglob("*.GL"))
    elif src.is_file():
        files = [src]
    else:
        print(f"glyph: not found: {src}", file=sys.stderr)
        return 1
    if not files:
        print("(no .GL files found)")
        return 0
    rc = 0
    for f in files:
        try:
            original = f.read_text(encoding="utf-8")
            doc = _gl_parse(original)
            canonical = _gl_format(doc)
        except GLSyntaxError as e:
            print(f"glyph: .GL syntax error in {f}: {e}", file=sys.stderr)
            rc = 1
            continue
        if args.check:
            if original != canonical:
                print(f"would reformat {f}")
                rc = 1
        else:
            if original != canonical:
                f.write_text(canonical, encoding="utf-8")
                print(f"formatted {f}")
            else:
                print(f"unchanged {f}")
    return rc


def _cmd_generate(args) -> int:
    src = Path(args.src)
    if src.is_dir():
        try:
            generated = _gl_compile_tree(src)
        except GLSyntaxError as e:
            print(f"glyph: .GL syntax error: {e}", file=sys.stderr)
            return 1
        for p in generated:
            print(f"generated {p}")
        if not generated:
            print("(no .GL files found)")
        return 0
    if not src.is_file():
        print(f"glyph: not found: {src}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else src.with_suffix(".py")
    try:
        _gl_compile_file(src, out)
    except GLSyntaxError as e:
        print(f"glyph: .GL syntax error: {e}", file=sys.stderr)
        return 1
    print(f"generated {out}")
    return 0


def _cmd_bootstrap(args) -> int:
    root = Path(args.root) if args.root else None
    _bootstrap(root, verbose=True)
    return 0


def _cmd_install(args) -> int:
    try:
        result = install(args.path, force=args.force)
    except InstallError as e:
        print(f"glyph: install failed: {e}", file=sys.stderr)
        return 1
    print(f"Installed {result.name}=={result.version}")
    print(f"  -> {result.location}")
    print(f"  gate: {result.gate.reason}")
    return 0


def _cmd_uninstall(args) -> int:
    removed = uninstall(args.name, args.version)
    if not removed:
        print(f"glyph: not installed: {args.name}", file=sys.stderr)
        return 1
    for n, v in removed:
        print(f"Removed {n}=={v}")
    return 0


def _cmd_list(_args) -> int:
    items = list_installed()
    if not items:
        print("(no glyphs installed)")
        return 0
    width = max(len(n) for n, _ in items)
    for name, version in items:
        print(f"{name:<{width}}  {version}")
    return 0


def _cmd_freeze(_args) -> int:
    out = freeze()
    if out:
        print(out)
    return 0


def _cmd_show(args) -> int:
    idx = GlyphIndex()
    versions = idx.versions(args.name)
    if not versions:
        print(f"glyph: not installed: {args.name}", file=sys.stderr)
        return 1
    for v in versions:
        mpath = idx.location(args.name, v) / "manifest.json"
        if mpath.exists():
            m = Manifest.from_path(mpath)
            print(f"Name: {m.name}")
            print(f"Version: {m.version}")
            print(f"Type: {m.glyph_type}    Runtime: {m.runtime}    Environment: {m.environment}")
            print(f"Requires Glyph: {m.requires_glyph}")
            print(f"Risk: {m.risk_level}    Cost: {m.cost_estimate}")
            print(f"SHA256: {m.sha256}")
            print(f"Location: {mpath.parent}")
            if m.dependencies:
                print("Requires:")
                for d in m.dependencies:
                    print(f"  - {d.name} {d.spec}")
            print(f"Description: {m.description}")
            print("---")
    return 0


def _cmd_pack(args) -> int:
    src = Path(args.src).resolve()
    if not src.is_dir():
        print(f"glyph: pack source must be a directory: {src}", file=sys.stderr)
        return 1
    manifest_path = src / "manifest.json"
    code_dir = src / "code"
    if not manifest_path.is_file() or not code_dir.is_dir():
        print("glyph: pack source must contain manifest.json and code/ directory",
              file=sys.stderr)
        return 1
    try:
        manifest = Manifest.from_path(manifest_path)
    except (ManifestError, json.JSONDecodeError) as e:
        print(f"glyph: invalid manifest: {e}", file=sys.stderr)
        return 1

    # Auto-compile any .GL files under code/ and adapt manifest accordingly.
    try:
        generated = _gl_compile_tree(code_dir)
    except GLSyntaxError as e:
        print(f"glyph: .GL syntax error: {e}", file=sys.stderr)
        return 1
    if generated:
        # If a main.GL exists, prefer its compiled .py as the entrypoint
        main_gl = code_dir / "main.GL"
        if main_gl.is_file():
            manifest.entrypoint = "code/main.py"
            # v0.6: also lift any `emotion` block from main.GL into the manifest.
            try:
                doc = _gl_parse(main_gl.read_text(encoding="utf-8"))
                if doc.emotion:
                    merged = dict(manifest.emotion)
                    merged.update(doc.emotion)
                    manifest.emotion = merged
            except GLSyntaxError:
                pass
        # Tag runtime as octalang when .GL sources are present (declarative origin)
        manifest.runtime = "octalang"
        if manifest.glyph_type == "native":
            manifest.glyph_type = "native"  # leave as-is; runtime field expresses origin

    # v0.7: detect wasm entrypoint and validate the module structurally.
    ep_path = code_dir / Path(manifest.entrypoint).relative_to("code") \
        if manifest.entrypoint.startswith("code/") else None
    if ep_path is not None and ep_path.suffix == ".wasm" and ep_path.is_file():
        from . import wasm as _wasm
        try:
            info = _wasm.validate_wasm(ep_path)
        except _wasm.WasmError as e:
            print(f"glyph: invalid wasm module: {e}", file=sys.stderr)
            return 1
        manifest.runtime = "wasm"
        print(f"  wasm module: {info.size} bytes, "
              f"{len(info.exports)} exports, {len(info.imports)} imports")

    # recompute digest over code/ (now includes generated .py files)
    manifest.sha256 = IntegrityChecker.digest_directory(code_dir)
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest.to_json())
        for f in sorted(code_dir.rglob("*")):
            if f.is_file():
                zf.write(f, arcname=f"code/{f.relative_to(code_dir).as_posix()}")
        geom = src / "geometry"
        if geom.is_dir():
            for f in sorted(geom.rglob("*")):
                if f.is_file():
                    zf.write(f, arcname=f"geometry/{f.relative_to(geom).as_posix()}")
    print(f"Packed {manifest.name}=={manifest.version} -> {out}")
    print(f"  runtime: {manifest.runtime}    entrypoint: {manifest.entrypoint}")
    if generated:
        print(f"  .GL sources compiled: {len(generated)}")
    print(f"  sha256: {manifest.sha256}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="glyph",
        description="Glyph — Seraphina's package manager (parallel to pip).",
    )
    p.add_argument("--version", action="version", version=f"glyph {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    sb = sub.add_parser("bootstrap", help="initialize the Glyph environment (no pip required)")
    sb.add_argument("--root", default=None, help="override GLYPH_HOME root")
    sb.set_defaults(func=_cmd_bootstrap)

    si = sub.add_parser("install", help="install a .glyph archive")
    si.add_argument("path")
    si.add_argument("--force", action="store_true")
    si.set_defaults(func=_cmd_install)

    su = sub.add_parser("uninstall", help="uninstall a glyph")
    su.add_argument("name")
    su.add_argument("--version", default=None)
    su.set_defaults(func=_cmd_uninstall)

    sub.add_parser("list", help="list installed glyphs").set_defaults(func=_cmd_list)
    sub.add_parser("freeze", help="output installed glyphs in requirements format").set_defaults(func=_cmd_freeze)

    sh = sub.add_parser("show", help="show metadata for an installed glyph")
    sh.add_argument("name")
    sh.set_defaults(func=_cmd_show)

    sp = sub.add_parser("pack", help="pack a source directory into a .glyph archive")
    sp.add_argument("src")
    sp.add_argument("-o", "--output", required=True)
    sp.set_defaults(func=_cmd_pack)

    sg = sub.add_parser("generate", help="compile .GL source files into Python")
    sg.add_argument("src", help="path to a .GL file or a directory tree")
    sg.add_argument("-o", "--output", default=None,
                    help="output .py path (only when src is a single file)")
    sg.set_defaults(func=_cmd_generate)

    sf = sub.add_parser("fmt", help="format .GL source files in canonical form")
    sf.add_argument("src", help="path to a .GL file or a directory tree")
    sf.add_argument("--check", action="store_true",
                    help="exit 1 if any file is not already canonical; do not write")
    sf.set_defaults(func=_cmd_fmt)

    sd = sub.add_parser("doctor", help="verify the Glyph environment is healthy")
    sd.add_argument("--root", default=None, help="override GLYPH_HOME root")
    sd.set_defaults(func=_cmd_doctor)

    sh = sub.add_parser("history", help="show recent emotional-gate decisions from the ledger")
    sh.add_argument("name", nargs="?", default=None,
                    help="optional package name to filter by")
    sh.add_argument("--limit", type=int, default=20)
    sh.add_argument("--root", default=None, help="override GLYPH_HOME root")
    sh.set_defaults(func=_cmd_history)

    sr = sub.add_parser("run", help="run an installed glyph's entrypoint")
    sr.add_argument("name")
    sr.add_argument("--version", default=None)
    sr.add_argument("--export", default=None,
                    help="name of a wasm export to invoke (wasm runtime only)")
    sr.add_argument("--host", default=None,
                    help="override wasm host (wasmtime|wasmer|null)")
    sr.add_argument("--arg", action="append", default=[],
                    help="integer argument(s) to pass to the wasm export")
    sr.set_defaults(func=_cmd_run)

    sx = sub.add_parser("forge",
        help="Rule-24: build a binary-native wasm glyph from geometry params")
    sx.add_argument("name")
    sx.add_argument("--version", default="1.0.0")
    sx.add_argument("--sides", type=int, default=0)
    sx.add_argument("--points", type=int, default=0)
    sx.add_argument("--dots", type=int, default=0)
    sx.add_argument("--intersections", type=int, default=0)
    sx.add_argument("--spirals", type=int, default=0)
    sx.add_argument("-o", "--output", default=None,
                    help="output .glyph path (default: <name>.glyph)")
    sx.add_argument("--source", default=None,
                    help="also write package source tree to this directory")
    sx.set_defaults(func=_cmd_forge)

    sra = sub.add_parser("remote-add",
        help="register a remote host endpoint in $GLYPH_HOME/remotes.json")
    sra.add_argument("name")
    sra.add_argument("--base-url", required=True,
                     help="e.g. http://synergro.local:8080 (use null:// for echo-host)")
    sra.add_argument("--auth", choices=["none", "bearer", "header", "basic"], default="none")
    sra.add_argument("--token", default="")
    sra.add_argument("--header-name", default="")
    sra.add_argument("--path", default="/", dest="default_path")
    sra.add_argument("--method", default="POST")
    sra.add_argument("--timeout", type=float, default=30.0)
    sra.set_defaults(func=_cmd_remote_add)

    srl = sub.add_parser("remote-list", help="list registered remote endpoints")
    srl.set_defaults(func=_cmd_remote_list)

    srr = sub.add_parser("remote-remove", help="unregister a remote endpoint")
    srr.add_argument("name")
    srr.set_defaults(func=_cmd_remote_remove)

    src = sub.add_parser("remote-call",
        help="POST a JSON payload to a registered remote and print the response")
    src.add_argument("name")
    src.add_argument("--prompt", default=None,
                     help='shortcut: send {"prompt": "<text>"}')
    src.add_argument("--json", default=None, dest="json_payload",
                     help="raw JSON payload string (overrides --prompt)")
    src.add_argument("--path", default=None)
    src.add_argument("--method", default=None)
    src.set_defaults(func=_cmd_remote_call)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
