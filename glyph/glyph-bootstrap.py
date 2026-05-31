#!/usr/bin/env python
"""glyph-bootstrap.py — standalone bootstrap entry point.

Run this once to initialize Seraphina's Glyph environment without pip:

    python glyph-bootstrap.py

It adds the local Glyph package to sys.path on the fly, then invokes
`glyph.bootstrap()`. After this, all further management is via
`python -m glyph <command>` or the `glyph` shim.
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from glyph.bootstrap import bootstrap  # noqa: E402

if __name__ == "__main__":
    bootstrap()
