"""WASM runtime adapter for Glyph (v0.7).

Goals:
  * Validate `.wasm` modules using only the stdlib (magic + section walk).
  * Provide a pluggable `WasmRuntime` host with auto-detection of
    ``wasmtime``, then ``wasmer`` if present; otherwise a deterministic
    `null_host` mode that *only* loads/inspects without invoking.
  * Never raise import errors from missing wasm runtimes — Glyph remains
    stdlib-only by default; runtime dependencies are opt-in.

Module-level public surface::

    validate_wasm(path) -> WasmModuleInfo
    load_module(code_dir, entrypoint, *, host=None) -> WasmInstance
    available_hosts() -> list[str]
    set_host(name | callable) -> None
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


WASM_MAGIC = b"\x00asm"
WASM_VERSION_1 = b"\x01\x00\x00\x00"


class WasmError(Exception):
    pass


_SECTION_NAMES = {
    0: "custom", 1: "type", 2: "import", 3: "function", 4: "table",
    5: "memory", 6: "global", 7: "export", 8: "start", 9: "element",
    10: "code", 11: "data", 12: "datacount",
}


@dataclass
class WasmModuleInfo:
    path: Path
    size: int
    sections: list[tuple[str, int]] = field(default_factory=list)  # (name, byte_size)
    exports: list[str] = field(default_factory=list)               # by name
    imports: list[tuple[str, str]] = field(default_factory=list)   # (module, field)
    has_start: bool = False


def _read_uleb128(buf: bytes, pos: int) -> tuple[int, int]:
    """Decode an unsigned LEB128 integer; return (value, new_pos)."""
    result = 0
    shift = 0
    start = pos
    while True:
        if pos >= len(buf):
            raise WasmError(f"truncated LEB128 at offset {start}")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result, pos
        shift += 7
        if shift > 63:
            raise WasmError("LEB128 too long")


def _read_name(buf: bytes, pos: int) -> tuple[str, int]:
    n, pos = _read_uleb128(buf, pos)
    if pos + n > len(buf):
        raise WasmError("truncated name")
    raw = buf[pos:pos + n]
    try:
        return raw.decode("utf-8"), pos + n
    except UnicodeDecodeError as e:
        raise WasmError(f"invalid utf-8 in name: {e}") from None


def validate_wasm(path: str | Path) -> WasmModuleInfo:
    """Validate a `.wasm` file and return a structural summary.

    This is a *structural* validator: header + section walk + export/import
    name decoding. It does NOT type-check the code section. Useful as a
    pre-flight check before handing the module to a real runtime.
    """
    p = Path(path)
    if not p.is_file():
        raise WasmError(f"not a file: {p}")
    data = p.read_bytes()
    if len(data) < 8:
        raise WasmError("file too small to be wasm")
    if data[:4] != WASM_MAGIC:
        raise WasmError(f"bad magic: {data[:4]!r}, expected {WASM_MAGIC!r}")
    if data[4:8] != WASM_VERSION_1:
        raise WasmError(f"unsupported wasm version: {data[4:8]!r}")

    info = WasmModuleInfo(path=p, size=len(data))
    pos = 8
    while pos < len(data):
        sec_id = data[pos]
        pos += 1
        sec_size, pos = _read_uleb128(data, pos)
        if pos + sec_size > len(data):
            raise WasmError(f"section {sec_id} overflows file")
        sec_end = pos + sec_size
        name = _SECTION_NAMES.get(sec_id, f"unknown_{sec_id}")
        info.sections.append((name, sec_size))

        if sec_id == 8:
            info.has_start = True
        elif sec_id == 7:  # exports
            try:
                count, q = _read_uleb128(data, pos)
                for _ in range(count):
                    nm, q = _read_name(data, q)
                    if q + 1 > sec_end:
                        raise WasmError("truncated export entry")
                    q += 1                         # export kind
                    _, q = _read_uleb128(data, q)  # export index
                    info.exports.append(nm)
            except WasmError:
                raise
            except Exception as e:  # noqa: BLE001 — wrap for consistent error type
                raise WasmError(f"bad export section: {e!r}") from None
        elif sec_id == 2:  # imports
            try:
                count, q = _read_uleb128(data, pos)
                for _ in range(count):
                    mod, q = _read_name(data, q)
                    fld, q = _read_name(data, q)
                    if q + 1 > sec_end:
                        raise WasmError("truncated import entry")
                    kind = data[q]; q += 1
                    if kind == 0:                  # func: typeidx
                        _, q = _read_uleb128(data, q)
                    elif kind in (1, 2):           # table / memory: limits
                        flags = data[q]; q += 1
                        _, q = _read_uleb128(data, q)            # min
                        if flags & 1:
                            _, q = _read_uleb128(data, q)        # max
                    elif kind == 3:                # global: valtype + mut
                        q += 2
                    else:
                        raise WasmError(f"unknown import kind: {kind}")
                    info.imports.append((mod, fld))
            except WasmError:
                raise
            except Exception as e:  # noqa: BLE001
                raise WasmError(f"bad import section: {e!r}") from None

        pos = sec_end
    return info


# --------------------------------------------------------------------------
# Pluggable host
# --------------------------------------------------------------------------

@dataclass
class WasmInstance:
    """Result of loading a wasm module under a host."""
    info: WasmModuleInfo
    host: str
    runtime_object: Any = None             # opaque (wasmtime.Instance, etc.)
    invoke: Optional[Callable[..., Any]] = None  # invoke(name, *args) -> result


HostFn = Callable[[WasmModuleInfo], WasmInstance]
_active_host: Optional[HostFn] = None


def available_hosts() -> list[str]:
    """Return names of wasm runtimes detected at runtime (in priority order)."""
    found: list[str] = []
    try:
        import wasmtime  # noqa: F401
        found.append("wasmtime")
    except ImportError:
        pass
    try:
        import wasmer  # noqa: F401
        found.append("wasmer")
    except ImportError:
        pass
    found.append("null")  # always available (load-only, no invoke)
    return found


def _null_host(info: WasmModuleInfo) -> WasmInstance:
    """Pure-stdlib host: validates and returns an inert instance."""
    def _no_invoke(_name: str, *_a, **_k):
        raise WasmError(
            "wasm invocation requires a real runtime (wasmtime/wasmer); "
            "running under null host"
        )
    return WasmInstance(info=info, host="null", invoke=_no_invoke)


def _wasmtime_host(info: WasmModuleInfo) -> WasmInstance:
    import wasmtime
    engine = wasmtime.Engine()
    store = wasmtime.Store(engine)
    module = wasmtime.Module.from_file(engine, str(info.path))
    inst = wasmtime.Instance(store, module, [])

    def _invoke(name: str, *args):
        f = inst.exports(store).get(name)
        if f is None:
            raise WasmError(f"no such export: {name!r}")
        return f(store, *args)

    return WasmInstance(info=info, host="wasmtime",
                        runtime_object=inst, invoke=_invoke)


def _resolve_host(name: Optional[str] = None) -> HostFn:
    if _active_host is not None:
        return _active_host
    if name is None:
        # auto-detect in priority order
        avail = available_hosts()
        name = avail[0]
    if name == "null":
        return _null_host
    if name == "wasmtime":
        return _wasmtime_host
    if name == "wasmer":
        # Lazy: only try if user explicitly asked for it.
        try:
            import wasmer  # noqa: F401
        except ImportError as e:
            raise WasmError(f"wasmer host requested but not installed: {e}") from None
        # Minimal wasmer host (left as future enhancement).
        raise WasmError("wasmer host adapter not yet implemented")
    raise WasmError(f"unknown wasm host: {name!r}")


def set_host(host: "str | HostFn | None") -> None:
    """Override host selection. Pass a name, a callable, or None to reset."""
    global _active_host
    if host is None or callable(host):
        _active_host = host  # type: ignore[assignment]
    elif isinstance(host, str):
        _active_host = _resolve_host(host)
    else:
        raise TypeError(f"host must be str | callable | None, got {type(host).__name__}")


def load_module(code_dir: str | Path, entrypoint: str,
                *, host: Optional[str] = None) -> WasmInstance:
    """Validate and load a wasm entrypoint under the selected host."""
    p = (Path(code_dir) / entrypoint).resolve()
    try:
        p.relative_to(Path(code_dir).resolve())
    except ValueError:
        raise WasmError(f"entrypoint escapes package root: {entrypoint!r}")
    info = validate_wasm(p)
    fn = _resolve_host(host)
    return fn(info)
