"""SHA-256 integrity verification for .glyph packages."""
from __future__ import annotations
import hashlib
import zipfile
from pathlib import Path
from typing import Iterable


class IntegrityError(Exception):
    pass


class IntegrityChecker:
    """Computes/verifies a deterministic SHA-256 digest over a code tree.

    Digest is computed over (sorted) `relative_posix_path\\0<file_bytes>\\0` chunks.
    Identical input trees always produce identical digests across platforms.
    """

    @staticmethod
    def _iter_files(root: Path) -> Iterable[Path]:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                yield p

    @classmethod
    def digest_directory(cls, code_dir: str | Path) -> str:
        root = Path(code_dir)
        if not root.is_dir():
            raise IntegrityError(f"not a directory: {root}")
        h = hashlib.sha256()
        for f in cls._iter_files(root):
            rel = f.relative_to(root).as_posix().encode("utf-8")
            h.update(rel)
            h.update(b"\0")
            h.update(f.read_bytes())
            h.update(b"\0")
        return h.hexdigest()

    @classmethod
    def digest_zip_subtree(cls, glyph_path: str | Path, subdir: str = "code/") -> str:
        """Compute digest over entries inside a .glyph zip under `subdir/`."""
        if not subdir.endswith("/"):
            subdir += "/"
        h = hashlib.sha256()
        with zipfile.ZipFile(glyph_path, "r") as zf:
            names = sorted(n for n in zf.namelist()
                           if n.startswith(subdir) and not n.endswith("/"))
            for n in names:
                rel = n[len(subdir):].encode("utf-8")
                h.update(rel)
                h.update(b"\0")
                h.update(zf.read(n))
                h.update(b"\0")
        return h.hexdigest()

    @classmethod
    def verify(cls, expected: str, actual: str) -> None:
        if not expected:
            raise IntegrityError("expected sha256 is empty")
        if expected.lower() != actual.lower():
            raise IntegrityError(
                f"sha256 mismatch: expected={expected[:12]}… actual={actual[:12]}…"
            )
