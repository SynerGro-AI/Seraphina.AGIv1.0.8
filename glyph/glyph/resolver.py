"""Remote resolver for `glyph install <url>` and `glyph install <name>`.

v0.10 introduces three install argument shapes (in addition to the
original local path):

* Local file path     -> install as before
* http(s)://... URL    -> download, verify SHA256 if known, install
* bare name           -> look up in the configured glyph-index.json,
                         resolve to URL + sha256, then download + install

The index is a JSON document of the shape::

    {
      "<name>": {
        "latest": "1.0.9",
        "versions": {
          "1.0.9": {
            "url":    "https://.../seraphina-1.0.9.glyph",
            "sha256": "<hex>"
          }
        }
      }
    }

Indexes are read-only and fetched over plain HTTPS with stdlib urllib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_INDEX_URL = (
    "https://raw.githubusercontent.com/SynerGro-AI/Seraphina.AGIv1.0.8/"
    "main/glyph-index.json"
)

USER_AGENT = "glyph-installer/0.10"


class ResolverError(Exception):
    """Raised when a glyph install argument cannot be resolved."""


@dataclass
class Resolved:
    name: Optional[str]
    version: Optional[str]
    url: str
    sha256: Optional[str]


# ---------------------------------------------------------------------------
# argument classification
# ---------------------------------------------------------------------------


def is_url(arg: str) -> bool:
    p = urllib.parse.urlparse(arg)
    return p.scheme in {"http", "https"} and bool(p.netloc)


def is_local_path(arg: str) -> bool:
    if is_url(arg):
        return False
    # Only treat as a local install target if the arg already looks like a
    # path (has a separator or .glyph suffix) AND points at a real file.
    # Bare names like "seraphina" must never be silently matched against a
    # same-named directory in the cwd.
    p = Path(arg)
    looks_like_path = (
        "/" in arg or "\\" in arg or arg.startswith(".") or arg.endswith(".glyph")
    )
    if not looks_like_path:
        return False
    return p.is_file()


def is_bare_name(arg: str) -> bool:
    if is_url(arg) or is_local_path(arg):
        return False
    # bare names are lowercase identifiers, optionally with ==<version>
    head = arg.split("==", 1)[0]
    if not head:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in head)


# ---------------------------------------------------------------------------
# index fetch + lookup
# ---------------------------------------------------------------------------


def _index_url() -> str:
    return os.environ.get("GLYPH_INDEX_URL", DEFAULT_INDEX_URL).strip() or DEFAULT_INDEX_URL


def _fetch_text(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (validated scheme)
        if resp.status != 200:
            raise ResolverError(f"index fetch failed ({url}): HTTP {resp.status}")
        return resp.read().decode("utf-8")


def fetch_index(url: Optional[str] = None) -> dict:
    use = url or _index_url()
    if use.startswith(("http://", "https://")):
        raw = _fetch_text(use)
    else:
        # allow file:// or plain local paths for offline / private indexes
        if use.startswith("file://"):
            parsed = urllib.parse.urlparse(use)
            # On Windows, urlparse('file:///C:/x') gives path='/C:/x'; strip leading '/'
            p = urllib.parse.unquote(parsed.path)
            if os.name == "nt" and len(p) >= 3 and p[0] == "/" and p[2] == ":":
                p = p[1:]
            path = p
        else:
            path = use
        raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ResolverError(f"glyph-index.json is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise ResolverError("glyph-index.json must be a JSON object")
    return data


def resolve_name(arg: str, *, index: Optional[dict] = None) -> Resolved:
    """Resolve `name` or `name==version` against the registered index."""
    name, _, want = arg.partition("==")
    name = name.strip()
    want = want.strip() or None

    idx = index if index is not None else fetch_index()
    entry = idx.get(name)
    if not entry:
        raise ResolverError(
            f"'{name}' not in glyph index ({_index_url()}). "
            f"Provide a URL or local .glyph path instead."
        )
    versions = entry.get("versions") or {}
    if want:
        v = want
        if v not in versions:
            raise ResolverError(f"{name}: version {v} not in index")
    else:
        v = entry.get("latest") or (sorted(versions, key=_semver_key)[-1] if versions else None)
        if not v:
            raise ResolverError(f"{name}: index has no versions")

    spec = versions.get(v) or {}
    url = spec.get("url")
    sha = spec.get("sha256") or None
    if not url:
        raise ResolverError(f"{name}=={v}: index entry missing 'url'")
    return Resolved(name=name, version=v, url=url, sha256=sha)


def resolve_url(arg: str) -> Resolved:
    return Resolved(name=None, version=None, url=arg, sha256=None)


def _semver_key(v: str) -> tuple:
    out = []
    for p in v.split(".")[:3]:
        try:
            out.append(int(p.split("-")[0].split("+")[0]))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


def download(url: str, *, dest_dir: Optional[Path] = None, timeout: float = 120.0,
             expected_sha256: Optional[str] = None) -> Path:
    """Download a .glyph archive and (optionally) verify its sha256.

    Supports http(s):// and file:// URLs (the latter for offline/private
    indexes and CI smoke tests).
    """
    if url.startswith("file://"):
        parsed = urllib.parse.urlparse(url)
        p = urllib.parse.unquote(parsed.path)
        if os.name == "nt" and len(p) >= 3 and p[0] == "/" and p[2] == ":":
            p = p[1:]
        src = Path(p)
        if not src.is_file():
            raise ResolverError(f"file url not found: {src}")
        data = src.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            raise ResolverError(
                f"sha256 mismatch for {url}\n  expected: {expected_sha256}\n  actual:   {actual}"
            )
        dest_dir = dest_dir or Path(tempfile.mkdtemp(prefix="glyph-dl-"))
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / src.name
        out.write_bytes(data)
        return out

    if not (url.startswith("http://") or url.startswith("https://")):
        raise ResolverError(f"refusing to download non-http(s) url: {url!r}")

    dest_dir = dest_dir or Path(tempfile.mkdtemp(prefix="glyph-dl-"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    # derive a safe filename from the URL path
    name = Path(urllib.parse.urlparse(url).path).name or "download.glyph"
    if not name.endswith(".glyph"):
        name += ".glyph"
    out = dest_dir / name

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=timeout) as resp, out.open("wb") as f:  # noqa: S310
        if resp.status != 200:
            raise ResolverError(f"download failed ({url}): HTTP {resp.status}")
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            h.update(chunk)
            f.write(chunk)

    actual = h.hexdigest()
    if expected_sha256 and actual.lower() != expected_sha256.lower():
        try:
            out.unlink()
        except OSError:
            pass
        raise ResolverError(
            f"sha256 mismatch for {url}\n  expected: {expected_sha256}\n  actual:   {actual}"
        )
    return out
