"""Remote-bridge runtime for Glyph (v0.9).

Lets a glyph (or the CLI) talk to a remote AGi / model / agent over plain
HTTP, with no third-party dependencies. Endpoints live in
``$GLYPH_HOME/remotes.json`` so the URL/auth can be configured once and
then referenced by name.

Design goals:
  * stdlib only (`urllib.request`, `json`)
  * never invent endpoints \u2014 a remote must be explicitly registered
  * deterministic tests \u2014 a ``null`` host is always available and a
    pluggable ``set_transport()`` lets tests inject a fake HTTP layer
  * every call is mirrored to the ledger and the in-process signal bus
"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

from .index import _resolve_root


class RemoteError(Exception):
    pass


# --------------------------------------------------------------------------
# Config: $GLYPH_HOME/remotes.json
# --------------------------------------------------------------------------

@dataclass
class RemoteHost:
    name: str
    base_url: str                                  # e.g. "http://synergro.local:8080"
    auth: str = "none"                             # none | bearer | header | basic
    token: str = ""                                # bearer token or header value
    header_name: str = ""                          # used when auth == "header"
    default_path: str = "/"                        # path appended for query()
    method: str = "POST"
    timeout: float = 30.0
    headers: dict = field(default_factory=dict)    # extra static headers

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RemoteHost":
        if "name" not in d or "base_url" not in d:
            raise RemoteError("remote needs 'name' and 'base_url'")
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def _registry_path(root: Optional[Path] = None) -> Path:
    return (root or _resolve_root()) / "remotes.json"


def _load_registry(root: Optional[Path] = None) -> dict[str, RemoteHost]:
    p = _registry_path(root)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text("utf-8"))
    except json.JSONDecodeError as e:
        raise RemoteError(f"corrupt remotes.json: {e}") from None
    out: dict[str, RemoteHost] = {}
    for name, d in raw.items():
        d = dict(d); d.setdefault("name", name)
        out[name] = RemoteHost.from_dict(d)
    return out


def _save_registry(reg: dict[str, RemoteHost], root: Optional[Path] = None) -> Path:
    p = _registry_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({n: h.to_dict() for n, h in reg.items()}, indent=2),
        encoding="utf-8",
    )
    return p


def register(host: RemoteHost, *, root: Optional[Path] = None) -> Path:
    reg = _load_registry(root)
    reg[host.name] = host
    return _save_registry(reg, root)


def unregister(name: str, *, root: Optional[Path] = None) -> bool:
    reg = _load_registry(root)
    if name not in reg:
        return False
    del reg[name]
    _save_registry(reg, root)
    return True


def list_remotes(*, root: Optional[Path] = None) -> list[RemoteHost]:
    return sorted(_load_registry(root).values(), key=lambda h: h.name)


def get(name: str, *, root: Optional[Path] = None) -> RemoteHost:
    reg = _load_registry(root)
    if name not in reg:
        raise RemoteError(f"no such remote: {name!r}")
    return reg[name]


# --------------------------------------------------------------------------
# Transport (pluggable for tests)
# --------------------------------------------------------------------------

Transport = Callable[[str, str, dict, bytes, float], tuple[int, dict, bytes]]
"""(method, url, headers, body, timeout) -> (status, response_headers, body)"""

_transport: Optional[Transport] = None


def set_transport(t: Optional[Transport]) -> None:
    global _transport
    _transport = t


def _stdlib_transport(method: str, url: str, headers: dict,
                      body: bytes, timeout: float) -> tuple[int, dict, bytes]:
    # Only allow http/https schemes \u2014 stop file:// / data:// abuse.
    if not (url.startswith("http://") or url.startswith("https://")):
        raise RemoteError(f"unsupported url scheme: {url!r}")
    req = urllib.request.Request(url, data=body if body else None,
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 \u2014 scheme checked
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""
    except urllib.error.URLError as e:
        raise RemoteError(f"transport error: {e.reason}") from None


# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------

@dataclass
class RemoteResponse:
    status: int
    headers: dict
    body: bytes
    json: Any = None                # parsed JSON if Content-Type is JSON

    def ok(self) -> bool:
        return 200 <= self.status < 300


def _build_headers(host: RemoteHost) -> dict:
    h = {"User-Agent": f"glyph-remote/{_runtime_version()}",
         "Accept": "application/json"}
    h.update(host.headers)
    if host.auth == "bearer" and host.token:
        h["Authorization"] = f"Bearer {host.token}"
    elif host.auth == "header" and host.header_name and host.token:
        h[host.header_name] = host.token
    elif host.auth == "basic" and host.token:
        # token is expected to be already-encoded "user:pass" base64 OR raw "user:pass"
        import base64
        tok = host.token
        if ":" in tok and not tok.endswith("="):
            tok = base64.b64encode(tok.encode("utf-8")).decode("ascii")
        h["Authorization"] = f"Basic {tok}"
    return h


def _runtime_version() -> str:
    try:
        from . import __version__
        return __version__
    except ImportError:
        return "?"


def call(name: str, payload: Any, *,
         path: Optional[str] = None,
         method: Optional[str] = None,
         root: Optional[Path] = None,
         host: Optional[RemoteHost] = None) -> RemoteResponse:
    """Send `payload` as JSON to remote `name` and return the response.

    The null host (``base_url == "null://"``) short-circuits to an echo
    response \u2014 useful for tests and for verifying the bridge wiring before
    pointing it at a real endpoint.
    """
    h = host or get(name, root=root)
    full_path = path or h.default_path
    if not full_path.startswith("/"):
        full_path = "/" + full_path
    url = h.base_url.rstrip("/") + full_path
    use_method = (method or h.method).upper()

    # Mirror to ledger + signal bus (best effort).
    try:
        from . import ledger as _ledger, signals as _signals
        _ledger.append({"event": "remote_call", "name": h.name,
                        "url": url, "method": use_method,
                        "payload_keys": list(payload.keys()) if isinstance(payload, dict) else None},
                       root=root)
        _signals.publish("remote_call", {"name": h.name, "url": url})
    except Exception:  # noqa: BLE001 \u2014 telemetry must never block
        pass

    if h.base_url.startswith("null://"):
        body = json.dumps({"echo": payload, "from": h.name}).encode("utf-8")
        return RemoteResponse(status=200, headers={"Content-Type": "application/json"},
                              body=body, json={"echo": payload, "from": h.name})

    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    headers = _build_headers(h)
    if body:
        headers["Content-Type"] = "application/json"
    t = _transport or _stdlib_transport
    status, resp_headers, resp_body = t(use_method, url, headers, body, h.timeout)
    parsed = None
    ctype = (resp_headers.get("Content-Type") or resp_headers.get("content-type") or "").lower()
    if "json" in ctype and resp_body:
        try:
            parsed = json.loads(resp_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
    return RemoteResponse(status=status, headers=resp_headers,
                          body=resp_body, json=parsed)
