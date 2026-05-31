"""Seraphina interactive wizard - cross-platform CLI.

Run with:
    seraphina            # if installed via pip
    python -m seraphina  # without install

Wraps the real ``glyph`` package manager (``python -m glyph ...``) so users
type natural intents instead of memorising flags.

No fake commands. Intents that don't have a real backend yet return a plan,
not pretend execution.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import __version__
from .core import RomanWheelTriad
from .rule_base import OctaRuleBase


# --- paths -------------------------------------------------------------------

WIZARD_DIR = Path(os.environ.get("SERAPHINA_HOME", Path.home() / ".seraphina")) / "wizard"
MEMORY_FILE = WIZARD_DIR / "memory.jsonl"
HISTORY_FILE = WIZARD_DIR / "history.jsonl"


def _ensure_dirs() -> None:
    WIZARD_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --- logging -----------------------------------------------------------------

def _append(path: Path, record: dict) -> None:
    _ensure_dirs()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def remember(text: str) -> None:
    _append(MEMORY_FILE, {"ts": _now(), "note": text})
    print("  remembered.")


def recall(query: str = "") -> None:
    if not MEMORY_FILE.exists():
        print("  (no memory yet)")
        return
    hits: List[dict] = []
    with MEMORY_FILE.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not query or query.lower() in rec.get("note", "").lower():
                hits.append(rec)
    if not hits:
        print("  (no matches)")
        return
    for rec in hits[-20:]:
        print(f"  {rec['ts']}  {rec['note']}")


# --- glyph CLI bridge --------------------------------------------------------

def glyph(*args: str, dry_run: bool = False) -> int:
    cmd = [sys.executable, "-m", "glyph", *args]
    display = "python -m glyph " + " ".join(shlex.quote(a) for a in args)
    print(f"  > {display}")
    _append(HISTORY_FILE, {"ts": _now(), "kind": "cmd", "cmd": display})
    if dry_run:
        print("  (dry-run, skipped)")
        return 0
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print("  error: python interpreter not found", file=sys.stderr)
        return 127


# --- Rule-24 helper ----------------------------------------------------------
# value = sides*10 + points + dots + intersections + spirals*8

def resolve_geometry_for_value(n: int) -> dict:
    if n < 0:
        raise ValueError("value must be >= 0")
    sides = 8 if n >= 80 else 0
    spirals = min(8, max(0, (n - sides * 10) // 8))
    rem = n - sides * 10 - spirals * 8
    points, dots, inter = rem, 0, 0
    if rem >= 35:
        dots, inter, points = 1, 1, rem - 2
    elif rem >= 2:
        dots, points = 1, rem - 1
    check = sides * 10 + points + dots + inter + spirals * 8
    return {
        "sides": sides, "points": points, "dots": dots,
        "intersections": inter, "spirals": spirals, "check": check,
    }


# --- triad ------------------------------------------------------------------

def triad(message: str) -> None:
    result = RomanWheelTriad().process(message)
    print(f"  consensus: {result['consensus']}")
    print(f"  response:  {result['response']}")
    print(f"  time:      {result['processing_time']}s")


# --- intent router ----------------------------------------------------------

HELP_TEXT = """
Intents (natural phrasing works for most):

  build glyph <N>            forge a binary-native wasm glyph whose Rule-24
                             value equals N        (e.g. "build glyph 179")
  forge <name> [k=v ...]     explicit forge: sides=8 points=33 dots=1 ...
  list                       list installed glyphs
  show <name>                manifest for an installed glyph
  run <name> [export=E n=K]  run an installed glyph
  install <path.glyph>       install a packed .glyph
  pack <dir>                 pack a source directory
  doctor                     environment health check
  history [N]                last N gate-ledger entries
  bootstrap                  re-init the glyph environment
  triad <message>            run a Roman Wheel Triad consensus pass
  remember <text>            append note to memory
  recall [query]             search memory (substring)
  plan <text>                honest build plan, no execution
  dry on | dry off           toggle dry-run mode
  version | help | exit
""".strip()


def route(line: str, dry_run: bool) -> tuple[bool, bool]:
    """Returns (stop, new_dry_run)."""
    t = line.strip()
    if not t:
        return False, dry_run
    _append(HISTORY_FILE, {"ts": _now(), "kind": "user", "text": t})

    if t in ("exit", "quit", "bye"):
        return True, dry_run
    if t == "help":
        print(HELP_TEXT)
        return False, dry_run
    if t == "version":
        print(f"  seraphina {__version__}")
        return False, dry_run

    m = re.fullmatch(r"dry\s+(on|off)", t)
    if m:
        nd = (m.group(1) == "on")
        print(f"  dry-run: {nd}")
        return False, nd

    m = re.fullmatch(r"remember\s+(.+)", t)
    if m:
        remember(m.group(1))
        return False, dry_run

    m = re.fullmatch(r"recall(?:\s+(.*))?", t)
    if m:
        recall((m.group(1) or "").strip())
        return False, dry_run

    m = re.fullmatch(r"triad\s+(.+)", t)
    if m:
        triad(m.group(1))
        return False, dry_run

    m = re.fullmatch(r"(?:build|make|create)\s+(?:a\s+)?glyph\s+(?:for\s+)?(\d+)", t)
    if m:
        n = int(m.group(1))
        g = resolve_geometry_for_value(n)
        name = f"glyph_{n}"
        print(f"  Rule-24 plan for value {n} -> {g['check']}:")
        print(f"    sides={g['sides']} points={g['points']} dots={g['dots']} "
              f"intersections={g['intersections']} spirals={g['spirals']}")
        if g["check"] != n:
            print(f"  warn: closest reachable is {g['check']}, not {n}")
        ok = input(f"  forge as '{name}'? [Y/n] ").strip().lower()
        if ok and not ok.startswith("y"):
            print("  cancelled.")
            return False, dry_run
        glyph("forge", name,
              "--sides", str(g["sides"]), "--points", str(g["points"]),
              "--dots", str(g["dots"]), "--intersections", str(g["intersections"]),
              "--spirals", str(g["spirals"]), dry_run=dry_run)
        return False, dry_run

    m = re.fullmatch(r"forge\s+(\S+)(.*)", t)
    if m:
        name = m.group(1)
        rest = m.group(2)
        kw = {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", rest)}
        cli = ["forge", name]
        for k in ("sides", "points", "dots", "intersections", "spirals"):
            if k in kw:
                cli += [f"--{k}", str(kw[k])]
        glyph(*cli, dry_run=dry_run)
        return False, dry_run

    if t in ("list", "freeze", "doctor", "bootstrap"):
        glyph(t, dry_run=dry_run)
        return False, dry_run

    m = re.fullmatch(r"show\s+(\S+)", t)
    if m: glyph("show", m.group(1), dry_run=dry_run); return False, dry_run

    m = re.fullmatch(r"install\s+(.+)", t)
    if m: glyph("install", m.group(1), dry_run=dry_run); return False, dry_run

    m = re.fullmatch(r"pack\s+(.+)", t)
    if m: glyph("pack", m.group(1), dry_run=dry_run); return False, dry_run

    m = re.fullmatch(r"uninstall\s+(\S+)", t)
    if m: glyph("uninstall", m.group(1), dry_run=dry_run); return False, dry_run

    m = re.fullmatch(r"history(?:\s+(\d+))?", t)
    if m:
        extra = ["--limit", m.group(1)] if m.group(1) else []
        glyph("history", *extra, dry_run=dry_run); return False, dry_run

    m = re.fullmatch(r"run\s+(\S+)(.*)", t)
    if m:
        name, rest = m.group(1), m.group(2)
        cli = ["run", name]
        em = re.search(r"export\s*=\s*(\S+)", rest)
        if em: cli += ["--export", em.group(1)]
        for am in re.finditer(r"(?:arg|n)\s*=\s*(-?\d+)", rest):
            cli += ["--arg", am.group(1)]
        glyph(*cli, dry_run=dry_run); return False, dry_run

    m = re.fullmatch(r"plan\s+(.+)", t)
    if not m and re.fullmatch(r"(?:build|create|make)\s+(?!glyph\b).+", t):
        m_text = t
    else:
        m_text = m.group(1) if m else None
    if m_text:
        print(f"  plan for: {m_text}")
        print("    1. break the request into binary-native glyphs (Rule-24 values)")
        print("    2. forge each glyph:  build glyph <N>")
        print("    3. install the packed .glyph files")
        print("    4. compose them with `run` and verify under Triad consensus")
        print("  (no execution - real implementation requires concrete numeric targets.)")
        return False, dry_run

    print("  unrecognized. type 'help' to see intents.")
    return False, dry_run


# --- entry point ------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="seraphina", description="Seraphina interactive wizard")
    p.add_argument("--dry-run", action="store_true", help="plan only, do not invoke glyph")
    p.add_argument("-c", "--command", help="run a single intent and exit")
    p.add_argument("--version", action="store_true")
    args = p.parse_args(argv)

    if args.version:
        print(f"seraphina {__version__}")
        return 0

    _ensure_dirs()

    if args.command:
        stop, _ = route(args.command, args.dry_run)
        return 0

    print("")
    print("  Seraphina wizard - interactive Glyph shell")
    print(f"  version: {__version__}")
    if args.dry_run:
        print("  DRY-RUN MODE: plans only, no execution")
    print('  type "help" for intents, "exit" to quit')
    print("")

    dry = args.dry_run
    while True:
        try:
            line = input("Seraphina> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        try:
            stop, dry = route(line, dry)
            if stop:
                break
        except Exception as e:  # noqa: BLE001
            print(f"  error: {e}")
            _append(HISTORY_FILE, {"ts": _now(), "kind": "error", "text": str(e)})
    print("  goodbye.")
    return 0
