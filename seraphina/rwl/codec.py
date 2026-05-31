"""RWL container format (.rwg files).

A .rwg file is a deterministic binary envelope around any source language:

    +-----------------------------+
    | magic   "RWL1"  (4 bytes)   |
    | version u16     (2 bytes)   |
    | lang_id u8      (1 byte)    |   index into SUPPORTED_LANGUAGES
    | flags   u8      (1 byte)    |   bit0 = payload is zlib-compressed
    | orig_sz u32     (4 bytes)   |   length of original source bytes
    | payld_sz u32    (4 bytes)   |   length of payload that follows
    | sha256          (32 bytes)  |   SHA256 of the ORIGINAL source bytes
    | reserved        (16 bytes)  |   zeros in v1
    +-----------------------------+   <- 64-byte header
    | payload (orig bytes or zlib(orig bytes))                            |
    +-----------------------------+

Decoding verifies the SHA256 of the recovered source matches the header,
giving a hard guarantee of lossless round-trip. The container is the
*carrier*; the wheel.py module gives the symbolic view of the same bytes.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

MAGIC = b"RWL1"
HEADER_FMT = "<4sHBBII32s16s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 64
VERSION = 1
FLAG_ZLIB = 0b00000001

# language id -> (name, default_extension, default_compress)
# Order is the lang_id; never reorder, only append.
SUPPORTED_LANGUAGES: list[Tuple[str, str, bool]] = [
    ("text",       "txt", True),    # 0
    ("python",     "py",  True),    # 1
    ("javascript", "js",  True),    # 2
    ("typescript", "ts",  True),    # 3
    ("markdown",   "md",  True),    # 4
    ("json",       "json", True),   # 5
    ("html",       "html", True),   # 6
    ("css",        "css",  True),   # 7
    ("shell",      "sh",   True),   # 8
    ("gl",         "gl",   True),   # 9  - Seraphina's native .GL
    ("rwast",      "rwast", True),  # 10 - Roman Wheel AST binary IR
]

_LANG_TO_ID = {name: i for i, (name, _, _) in enumerate(SUPPORTED_LANGUAGES)}
_EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".sh": "shell",
    ".bash": "shell",
    ".gl": "gl",
    ".txt": "text",
}


class RWLError(Exception):
    pass


@dataclass
class RWLContainer:
    version: int
    language: str
    flags: int
    original_size: int
    payload_size: int
    sha256_hex: str

    @property
    def compressed(self) -> bool:
        return bool(self.flags & FLAG_ZLIB)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _detect_language(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _EXT_TO_LANG:
        return _EXT_TO_LANG[ext]
    return "text"


def _resolve_language(lang: Optional[str], src: Optional[Path]) -> str:
    if lang and lang != "auto":
        if lang not in _LANG_TO_ID:
            raise RWLError(f"unsupported language: {lang!r} "
                           f"(known: {sorted(_LANG_TO_ID)})")
        return lang
    if src is not None:
        return _detect_language(src)
    return "text"


def _ext_for(lang: str) -> str:
    return SUPPORTED_LANGUAGES[_LANG_TO_ID[lang]][1]


# --------------------------------------------------------------------------
# encode / decode
# --------------------------------------------------------------------------

def encode(source: bytes,
           *,
           language: str = "text",
           compress: Optional[bool] = None) -> bytes:
    """Wrap raw source bytes into a deterministic .rwg envelope."""
    if language not in _LANG_TO_ID:
        raise RWLError(f"unsupported language: {language!r}")

    if compress is None:
        compress = SUPPORTED_LANGUAGES[_LANG_TO_ID[language]][2]

    payload = zlib.compress(source, 9) if compress else source
    flags = FLAG_ZLIB if compress else 0
    digest = hashlib.sha256(source).digest()
    header = struct.pack(
        HEADER_FMT,
        MAGIC,
        VERSION,
        _LANG_TO_ID[language],
        flags,
        len(source),
        len(payload),
        digest,
        b"\x00" * 16,
    )
    return header + payload


def decode(blob: bytes) -> tuple[RWLContainer, bytes]:
    """Verify and unwrap a .rwg envelope. Returns (container, original source bytes)."""
    if len(blob) < HEADER_SIZE:
        raise RWLError(f"too short to be RWL ({len(blob)} bytes)")
    (
        magic, version, lang_id, flags, orig_sz, payld_sz, digest, _reserved
    ) = struct.unpack(HEADER_FMT, blob[:HEADER_SIZE])

    if magic != MAGIC:
        raise RWLError(f"bad magic: {magic!r}")
    if version != VERSION:
        raise RWLError(f"unsupported RWL version: {version}")
    if lang_id >= len(SUPPORTED_LANGUAGES):
        raise RWLError(f"unknown language id: {lang_id}")

    payload = blob[HEADER_SIZE:HEADER_SIZE + payld_sz]
    if len(payload) != payld_sz:
        raise RWLError(f"truncated payload: got {len(payload)}, expected {payld_sz}")

    if flags & FLAG_ZLIB:
        try:
            source = zlib.decompress(payload)
        except zlib.error as e:
            raise RWLError(f"zlib decompression failed: {e}")
    else:
        source = payload

    if len(source) != orig_sz:
        raise RWLError(
            f"size mismatch after decode: got {len(source)}, header said {orig_sz}"
        )
    actual = hashlib.sha256(source).digest()
    if actual != digest:
        raise RWLError("SHA256 mismatch: payload does not round-trip cleanly")

    container = RWLContainer(
        version=version,
        language=SUPPORTED_LANGUAGES[lang_id][0],
        flags=flags,
        original_size=orig_sz,
        payload_size=payld_sz,
        sha256_hex=digest.hex(),
    )
    return container, source


def info(blob: bytes) -> RWLContainer:
    """Inspect header without unpacking payload (cheap)."""
    if len(blob) < HEADER_SIZE:
        raise RWLError(f"too short to be RWL ({len(blob)} bytes)")
    (
        magic, version, lang_id, flags, orig_sz, payld_sz, digest, _reserved
    ) = struct.unpack(HEADER_FMT, blob[:HEADER_SIZE])
    if magic != MAGIC:
        raise RWLError(f"bad magic: {magic!r}")
    if lang_id >= len(SUPPORTED_LANGUAGES):
        raise RWLError(f"unknown language id: {lang_id}")
    return RWLContainer(
        version=version,
        language=SUPPORTED_LANGUAGES[lang_id][0],
        flags=flags,
        original_size=orig_sz,
        payload_size=payld_sz,
        sha256_hex=digest.hex(),
    )


# --------------------------------------------------------------------------
# convenience: file-level encode/decode
# --------------------------------------------------------------------------

def encode_file(src_path: Path,
                out_path: Path,
                *,
                language: Optional[str] = None,
                compress: Optional[bool] = None) -> RWLContainer:
    lang = _resolve_language(language, src_path)
    source = src_path.read_bytes()
    blob = encode(source, language=lang, compress=compress)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    return info(blob)


def decode_file(rwg_path: Path, out_path: Optional[Path] = None) -> tuple[RWLContainer, Path]:
    blob = rwg_path.read_bytes()
    container, source = decode(blob)
    if out_path is None:
        ext = _ext_for(container.language)
        out_path = rwg_path.with_suffix("." + ext)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(source)
    return container, out_path
