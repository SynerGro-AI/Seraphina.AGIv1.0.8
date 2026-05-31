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
import difflib
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

SERAPHINA_HOME = Path(os.environ.get("SERAPHINA_HOME", Path.home() / ".seraphina"))
WIZARD_DIR = SERAPHINA_HOME / "wizard"
AGENTS_DIR = SERAPHINA_HOME / "agents"
MEMORY_FILE = WIZARD_DIR / "memory.jsonl"
HISTORY_FILE = WIZARD_DIR / "history.jsonl"


def _ensure_dirs() -> None:
    WIZARD_DIR.mkdir(parents=True, exist_ok=True)
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)


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


# --- agent builder ----------------------------------------------------------

def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
    return s.lower() or "agent"


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"  {prompt}{suffix}: ").strip()
    except EOFError:
        ans = ""
    return ans or default


def _ask_int(prompt: str, default: int) -> int:
    raw = _ask(prompt, str(default))
    try:
        return int(raw)
    except ValueError:
        print(f"  (not a number, using {default})")
        return default


def create_agent(name: Optional[str] = None) -> int:
    """Interactive wizard: name, purpose, first memory, recall window, etc."""
    _ensure_dirs()
    print()
    print("  Let's build an AI. Press Enter to accept defaults.")
    print()
    name = name or _ask("name (what do you call it?)", "Aria")
    slug = _slug(name)
    purpose = _ask("purpose (one sentence)", "a helpful, deterministic assistant")
    first_memory = _ask("first memory (something it should always remember)", "")
    recall_window = _ask("recall window (e.g. 7d, 30d, all)", "30d")
    voice = _ask("voice style (calm / focused / playful / serious)", "calm")
    triad = _ask("Triad consensus enabled? (y/n)", "y").lower().startswith("y")

    agent_path = AGENTS_DIR / f"{slug}.json"
    if agent_path.exists():
        ow = _ask(f"agent '{slug}' already exists - overwrite? (y/n)", "n").lower()
        if not ow.startswith("y"):
            print("  cancelled.")
            return 1

    record = {
        "schema": 1,
        "name": name,
        "slug": slug,
        "purpose": purpose,
        "voice": voice,
        "triad_consensus": triad,
        "recall_window": recall_window,
        "created": _now(),
        "memories": [],
    }
    if first_memory:
        record["memories"].append({"ts": _now(), "note": first_memory})

    agent_path.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    print()
    print(f"  created agent: {name}  ({slug})")
    print(f"  -> {agent_path}")
    print(f"  use it:  seraphina -c \"agent {slug} hello\"")
    print(f"  list:    seraphina -c \"list agents\"")
    return 0


def list_agents() -> int:
    _ensure_dirs()
    files = sorted(AGENTS_DIR.glob("*.json"))
    if not files:
        print("  no agents yet. create one:  seraphina create-agent")
        return 0
    print(f"  {len(files)} agent(s) in {AGENTS_DIR}:")
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            print(f"    {data.get('slug', p.stem):<20}  "
                  f"{data.get('name', '?'):<20}  {data.get('purpose', '')[:50]}")
        except Exception as e:  # noqa: BLE001 - keep listing on bad file
            print(f"    {p.stem}  (unreadable: {e!r})")
    return 0


def _parse_recall_window(window: str) -> Optional[float]:
    """Return seconds, or None for 'all' / unparseable."""
    w = (window or "").strip().lower()
    if w in ("all", "forever", "", "*"):
        return None
    m = re.fullmatch(r"(\d+)\s*([smhdwy])", w)
    if not m:
        return None
    n = int(m.group(1))
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}
    return n * mult[m.group(2)]


def agent_speak(slug: str, message: str) -> int:
    """Append a message to an agent's memory, return a Triad-consensus reply."""
    _ensure_dirs()
    agent_path = AGENTS_DIR / f"{_slug(slug)}.json"
    if not agent_path.exists():
        print(f"  no such agent: {slug}.  create one:  seraphina create-agent")
        return 1
    data = json.loads(agent_path.read_text(encoding="utf-8"))
    data.setdefault("memories", []).append({"ts": _now(), "note": message})

    # Trim memory by recall_window
    secs = _parse_recall_window(data.get("recall_window", "all"))
    if secs is not None:
        now_dt = datetime.now(timezone.utc)
        keep = []
        for m in data["memories"]:
            try:
                ts = datetime.fromisoformat(m["ts"])
                if (now_dt - ts).total_seconds() <= secs:
                    keep.append(m)
            except Exception:
                keep.append(m)
        data["memories"] = keep

    agent_path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    print(f"  {data.get('name', slug)}: noted ({len(data['memories'])} memories kept)")

    if data.get("triad_consensus", True):
        triad(message)
    return 0


def agent_recall(slug: str, query: str = "") -> int:
    agent_path = AGENTS_DIR / f"{_slug(slug)}.json"
    if not agent_path.exists():
        print(f"  no such agent: {slug}")
        return 1
    data = json.loads(agent_path.read_text(encoding="utf-8"))
    mems = data.get("memories", [])
    q = (query or "").lower()
    hits = [m for m in mems if not q or q in m.get("note", "").lower()]
    if not hits:
        print(f"  ({data.get('name', slug)} has no matching memories)")
        return 0
    print(f"  {data.get('name', slug)} remembers ({len(hits)}):")
    for m in hits[-20:]:
        print(f"    {m['ts']}  {m['note']}")
    return 0


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


def plan_grok(message: str) -> None:
    """Optional: ask xAI Grok for a planning pass. Requires SERAPHINA_GROK_API_KEY.

    Uses stdlib urllib so no extra dependency is installed; the [grok]
    extra in pyproject.toml exists only to signal explicit user opt-in.
    """
    import json as _json
    import urllib.request
    import urllib.error

    key = os.environ.get("SERAPHINA_GROK_API_KEY", "").strip()
    if not key:
        print("  plan-grok: SERAPHINA_GROK_API_KEY is not set.")
        print("  set it first:")
        print("    PowerShell: $env:SERAPHINA_GROK_API_KEY = 'xai-...'")
        print("    bash:       export SERAPHINA_GROK_API_KEY=xai-...")
        print("  then retry:   seraphina -c \"plan-grok <your message>\"")
        return

    endpoint = os.environ.get("SERAPHINA_GROK_ENDPOINT",
                              "https://api.x.ai/v1/chat/completions")
    model = os.environ.get("SERAPHINA_GROK_MODEL", "grok-beta")
    payload = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "You are a planning assistant for Seraphina.AGI, a "
                        "deterministic Roman Wheel Triad system. Produce a "
                        "short, numbered build plan. No code execution."},
            {"role": "user", "content": message},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        endpoint,
        data=_json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    print(f"  plan-grok -> {endpoint} (model={model})")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
        return
    except urllib.error.URLError as e:
        print(f"  network error: {e.reason}")
        return
    except Exception as e:
        print(f"  error: {e}")
        return

    try:
        text = data["choices"][0]["message"]["content"]
    except Exception:
        print(f"  unexpected response shape: {str(data)[:400]}")
        return
    print("  --- grok plan ---")
    for line in text.splitlines():
        print(f"  {line}")


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

  create-agent [name]        interactive: build a named AI (name, purpose,
                             first memory, recall window, voice)
  list agents                show created agents
  agent <slug> <message>     send message; updates that agent's memory
  agent <slug> recall [q]    search that agent's memories

  triad <message>            run a Roman Wheel Triad consensus pass
  plan-grok <message>        optional: ask xAI Grok for a build plan
                             (needs SERAPHINA_GROK_API_KEY)
  remember <text>            append note to wizard memory
  recall [query]             search wizard memory (substring)
  plan <text>                honest build plan, no execution
  dry on | dry off           toggle dry-run mode
  version | help | exit

You can talk casually: "build me a glyph for 179", "show me wheel_one",
"i want to run wheel_one", "what version" - all work.
""".strip()


# Words we strip from the front/middle of casual phrasings so the regex
# matchers below can ignore filler. "please run wheel_one" -> "run wheel_one".
_FILLERS = (
    "please", "pls", "can you", "could you", "would you",
    "i want to", "i'd like to", "i would like to",
    "lets", "let's", "go ahead and", "now",
    "me", "for me", "my", "the", "a", "an", "to",
    "everything", "all of them", "all",
)
# Verb synonyms -> canonical command keyword
_VERB_ALIASES = {
    r"\b(?:launch|start|execute|exec|invoke|use)\b": "run",
    r"\b(?:display|view|inspect|info|details?(?:\s+for)?|describe)\b": "show",
    r"\b(?:check|verify|test|diagnose|health\s*check)\b": "doctor",
    r"\b(?:setup|init|initialize|reinit|reinitialize)\b": "bootstrap",
    r"\b(?:remove|delete|drop|purge)\b": "uninstall",
    r"\b(?:add|deploy)\b": "install",
    r"\b(?:catalog|inventory|installed|whats?\s+installed)\b": "list",
}
_GREETINGS = re.compile(
    r"^(?:hi|hey|hello|howdy|yo|hola|greetings|sup|good\s+(?:morning|afternoon|evening))\b",
    re.IGNORECASE,
)
_HELP_PHRASES = re.compile(
    r"^(?:\?+|help|what\s+can\s+you\s+do|what\s+do\s+you\s+do|"
    r"how\s+do\s+i\s+(?:use|start)|commands?|menu)\b",
    re.IGNORECASE,
)
_VERSION_PHRASES = re.compile(
    r"^(?:version|whats?\s+(?:my|the)?\s*version|which\s+version|--?v)\b",
    re.IGNORECASE,
)

# Canonical commands used for "did you mean?" suggestions on unknown input.
_KNOWN_COMMANDS = (
    "help", "version", "exit", "dry on", "dry off",
    "build glyph", "forge", "list", "show", "run", "install",
    "uninstall", "pack", "doctor", "history", "bootstrap",
    "triad", "remember", "recall", "plan", "plan-grok",
    "create-agent", "list agents", "agent",
)


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, drop common filler words, expand verbs."""
    s = text.lower().strip()
    # Expand verb synonyms first (before filler removal so multi-word phrases match)
    for pat, repl in _VERB_ALIASES.items():
        s = re.sub(pat, repl, s)
    # Drop filler words (longest first to avoid partial matches)
    for word in sorted(_FILLERS, key=len, reverse=True):
        s = re.sub(rf"\b{re.escape(word)}\b", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s



def route(line: str, dry_run: bool) -> tuple[bool, bool]:
    """Returns (stop, new_dry_run)."""
    raw = line.strip()
    if not raw:
        return False, dry_run
    _append(HISTORY_FILE, {"ts": _now(), "kind": "user", "text": raw})

    # --- greetings / chit-chat ---
    if _GREETINGS.match(raw):
        print("  Hi! I'm Seraphina. Type 'help' to see what I can do,")
        print("  or try: build glyph 179   |   list   |   triad hello world")
        return False, dry_run

    if _HELP_PHRASES.match(raw):
        print(HELP_TEXT)
        return False, dry_run

    if _VERSION_PHRASES.match(raw):
        print(f"  seraphina {__version__}")
        return False, dry_run

    # Lowercase, drop filler, expand verb synonyms.
    t = _normalize(raw)

    if t in ("exit", "quit", "bye", "goodbye", "later", "done"):
        return True, dry_run
    if t == "help":
        print(HELP_TEXT)
        return False, dry_run

    m = re.fullmatch(r"dry\s+(on|off|true|false|yes|no)", t)
    if m:
        nd = m.group(1) in ("on", "true", "yes")
        print(f"  dry-run: {nd}")
        return False, nd

    # --- content-bearing commands: extract payload from RAW to preserve case ---

    m = re.match(r"(?i)^\s*remember\s+(.+)$", raw)
    if m:
        remember(m.group(1).strip())
        return False, dry_run

    m = re.match(r"(?i)^\s*recall(?:\s+(.*))?$", raw)
    if m:
        recall((m.group(1) or "").strip())
        return False, dry_run

    m = re.match(r"(?i)^\s*triad\s+(.+)$", raw)
    if m:
        triad(m.group(1).strip())
        return False, dry_run

    # --- optional Grok planner ---
    m = re.match(r"(?i)^\s*(?:plan-grok|grok-plan|grok)\s+(.+)$", raw)
    if m:
        plan_grok(m.group(1).strip())
        return False, dry_run

    # --- agent builder ---
    m = re.match(r"(?i)^\s*(?:create|new|build|make)[\s-]?agent(?:\s+(.+))?$", raw)
    if m:
        create_agent(m.group(1).strip() if m.group(1) else None)
        return False, dry_run

    if re.fullmatch(r"(?i)\s*(?:list|show)\s+agents?\s*", raw):
        list_agents()
        return False, dry_run

    m = re.match(r"(?i)^\s*agent\s+(\S+)\s+recall(?:\s+(.+))?$", raw)
    if m:
        agent_recall(m.group(1), (m.group(2) or "").strip())
        return False, dry_run

    m = re.match(r"(?i)^\s*agent\s+(\S+)\s+(.+)$", raw)
    if m:
        agent_speak(m.group(1), m.group(2).strip())
        return False, dry_run

    # --- build glyph <N>  (tolerant: "build me a glyph for 179", "make glyph 100") ---
    m = re.fullmatch(r"(?:build|make|create|forge)\s+(?:glyph\s+)?(?:for\s+)?(\d+)", t)
    if m:
        n = int(m.group(1))
        g = resolve_geometry_for_value(n)
        name = f"glyph_{n}"
        print(f"  Rule-24 plan for value {n} -> {g['check']}:")
        print(f"    sides={g['sides']} points={g['points']} dots={g['dots']} "
              f"intersections={g['intersections']} spirals={g['spirals']}")
        if g["check"] != n:
            print(f"  warn: closest reachable is {g['check']}, not {n}")
        try:
            ok = input(f"  forge as '{name}'? [Y/n] ").strip().lower()
        except EOFError:
            ok = "y"
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

    # install/pack: take payload from RAW to preserve path case
    m = re.match(r"(?i)^\s*(?:please\s+)?install\s+(.+)$", raw)
    if m: glyph("install", m.group(1).strip(), dry_run=dry_run); return False, dry_run

    m = re.match(r"(?i)^\s*(?:please\s+)?pack\s+(.+)$", raw)
    if m: glyph("pack", m.group(1).strip(), dry_run=dry_run); return False, dry_run

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

    # plan: preserve raw text after the verb
    m = re.match(r"(?i)^\s*plan\s+(.+)$", raw)
    if m:
        text = m.group(1).strip()
        print(f"  plan for: {text}")
        print("    1. break the request into binary-native glyphs (Rule-24 values)")
        print("    2. forge each glyph:  build glyph <N>")
        print("    3. install the packed .glyph files")
        print("    4. compose them with `run` and verify under Triad consensus")
        print("  (no execution - real implementation requires concrete numeric targets.)")
        return False, dry_run

    # --- final fallback: suggest the closest known command ---
    first = t.split(" ", 1)[0] if t else ""
    candidates = [c.split(" ", 1)[0] for c in _KNOWN_COMMANDS]
    suggestion = difflib.get_close_matches(first, candidates, n=1, cutoff=0.6)
    if suggestion:
        print(f"  hmm, not sure what '{raw}' means. did you mean: {suggestion[0]}?")
    else:
        print("  unrecognized. type 'help' to see what I can do.")
    return False, dry_run


# --- entry point ------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="seraphina", description="Seraphina interactive wizard")
    p.add_argument("--dry-run", action="store_true", help="plan only, do not invoke glyph")
    p.add_argument("-c", "--command", help="run a single intent and exit")
    p.add_argument("--version", action="store_true")
    p.add_argument("rest", nargs=argparse.REMAINDER,
                   help="optional positional intent, e.g. 'seraphina create-agent'")
    args = p.parse_args(argv)

    if args.version:
        print(f"seraphina {__version__}")
        return 0

    _ensure_dirs()

    if args.command:
        route(args.command, args.dry_run)
        return 0

    # Direct subcommands: `seraphina create-agent`, `seraphina list-agents`, etc.
    if args.rest:
        intent = " ".join(args.rest).strip()
        if intent:
            route(intent, args.dry_run)
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
