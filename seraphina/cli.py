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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import __version__
from .core import RomanWheelTriad
from .rule_base import OctaRuleBase  # noqa: F401
from .constitution import (
    AI_DISCLOSURE_TEXT, CONSTITUTIONAL_RULES, RULES_SHA256, AuditLog,
    RuleBase, RuleBaseTampered, enforced_rules, planned_rules, rules_digest,
    verify_integrity,
)
from . import gate as _gate


# --- paths -------------------------------------------------------------------

SERAPHINA_HOME = Path(os.environ.get("SERAPHINA_HOME", Path.home() / ".seraphina"))
WIZARD_DIR = SERAPHINA_HOME / "wizard"
AGENTS_DIR = SERAPHINA_HOME / "agents"
MEMORY_FILE = WIZARD_DIR / "memory.jsonl"
AUDIT_FILE = SERAPHINA_HOME / "audit.jsonl"   # constitutional rule 13


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


def remember(text: str) -> int:
    _append(MEMORY_FILE, {"ts": _now(), "note": text})
    print("  remembered.")
    return 0


def recall(query: str = "") -> int:
    if not MEMORY_FILE.exists():
        print("  (no memory yet)")
        return 0
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
        return 0
    for rec in hits[-20:]:
        print(f"  {rec['ts']}  {rec['note']}")
    return 0


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
    print("  list:    seraphina -c \"list agents\"")
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
            except (KeyError, TypeError, ValueError):
                keep.append(m)  # no usable timestamp: never silently forget it
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

def triad(message: str) -> int:
    """Run a Triad pass. Exit code 0 whether or not consensus is reached
    (no consensus is a result, not an error)."""
    result = RomanWheelTriad().process(message)
    wheels = result["wheels"]
    # Constitutional rule 13: every Triad decision goes to the hash-chained log.
    AuditLog(AUDIT_FILE).append({
        "event": "triad", "ts": _now(), "consensus": result["consensus"],
        "input_sha256_16": wheels["geometric"]["hash"],
        "checksum": wheels["verification"]["checksum"],
        "reasons": wheels["verification"]["reasons"] + wheels["mercy_civ"]["reasons"],
    })
    print(f"  consensus: {result['consensus']}")
    print(f"  response:  {result['response']}")
    print(f"  time:      {result['processing_time']}s")
    return 0


# --- constitutional rules -----------------------------------------------------

def verify_rules() -> int:
    """`seraphina --verify-rules`: rule-table hash + audit-log chain."""
    ok_rules = verify_integrity()
    print(f"  rules sha256 : {rules_digest()}")
    print(f"  pinned       : {RULES_SHA256}")
    print(f"  rule table   : {'OK' if ok_rules else 'TAMPERED'}")
    log = AuditLog(AUDIT_FILE)
    n = len(log.records())
    ok_log = log.verify()
    print(f"  audit log    : {'OK' if ok_log else 'BROKEN CHAIN'} ({n} records, {AUDIT_FILE})")
    # The RuleBase derives the halt from the halt file AND the audit chain,
    # so deleting halted.json does not make this report "running".
    halted = halted_reason()
    print(f"  rule 19 halt : {'HALTED: ' + halted if halted else 'running'}")
    print(f"  enforced     : {len(enforced_rules())}/20   planned: {', '.join(planned_rules())}")
    return 0 if (ok_rules and ok_log and not halted) else 1


def reset_rules(reason: str) -> int:
    """`seraphina --reset-rules "<reason>"`: a person clears a rule-19 halt
    after reviewing the audit log. The reason is logged."""
    rb = _gate.rule_base()
    if not rb.halted:
        print("  not halted; nothing to reset.")
        return 0
    print(f"  halted because: {rb.halted}")
    try:
        rb.reset(reason)
    except (RuleBaseTampered, ValueError) as e:
        print(f"  reset refused: {e}", file=sys.stderr)
        return 1
    print("  reset logged; Seraphina is running again.")
    return 0


def export_audit(dest: Optional[str]) -> int:
    """`seraphina --export-audit [file]`: verify, then copy or print the log."""
    log = AuditLog(AUDIT_FILE)
    if not log.verify():
        print("  audit log chain is broken; refusing to export", file=sys.stderr)
        return 1
    data = AUDIT_FILE.read_text(encoding="utf-8") if AUDIT_FILE.exists() else ""
    if dest:
        Path(dest).write_text(data, encoding="utf-8")
        print(f"  exported {len(log.records())} records -> {dest}")
    else:
        sys.stdout.write(data)
    return 0


def show_rules(rule: str = "") -> int:
    """Constitutional rule 16: rule interpretations on request."""
    if rule:
        try:
            r = RuleBase.interpret(rule)
        except KeyError as e:
            print(f"  {e.args[0]}", file=sys.stderr)
            return 1
        print(f"  {r['rule']} [{r['category']}, {r['status']}]: {r['text']}")
        print(f"  penalty: {r['penalty']}")
        print(f"  how checked: {r['how_checked']}")
        return 0
    for cat, rules in CONSTITUTIONAL_RULES.items():
        print(f"  {cat}  (penalty: {rules['penalty']})")
        for rid, text in rules.items():
            if rid != "penalty":
                st = RuleBase.interpret(rid)["status"]
                print(f"    {rid:<8} {st:<9} {text}")
    return 0


GROK_SYSTEM_PROMPT = (
    "You are a planning assistant for Seraphina.AGI, a deterministic Roman "
    "Wheel Triad system. Produce a short, numbered build plan. No code "
    "execution. You are an AI: never claim to be a human.")


def _grok_request_context(endpoint: str) -> dict:
    """What the outgoing plan-grok call does, declared for the rule gate."""
    return {
        # The message is user text sent to a third party (xAI). The user
        # typed plan-grok and supplied their own key: that is the consent.
        "collects_user_data": True,
        "user_consent": True,
        "transmits_pii": True,          # assume user text may contain PII
        "encrypted": endpoint.lower().startswith("https://"),
        "rate_limiter": _gate.grok_rate_limiter(),
        "rate_key": "plan_grok",
        "requires_audit": True,
    }


def gate_grok_reply(message: str, reply: str) -> list:
    """Gate a Grok reply before it is shown. Returns the lines to print
    (disclosure first). Raises gate.Blocked if the reply may not be shown."""
    header = f"{AI_DISCLOSURE_TEXT} The plan below was written by Grok, xAI's AI model."
    _gate.check("plan_grok.reply", {
        "response": reply,                 # rule 9: no human claims
        "conversation": [header],          # rule 10: AI nature disclosed
        "requires_audit": True,
    })
    # Same Triad pass every other Seraphina output gets (integrity + mercy).
    result = RomanWheelTriad().process(message, candidate=reply)
    AuditLog(AUDIT_FILE).append({
        "event": "triad", "ts": _now(), "action": "plan_grok.reply",
        "consensus": result["consensus"],
        "reasons": result["wheels"]["verification"]["reasons"]
                   + result["wheels"]["mercy_civ"]["reasons"],
    })
    if not result["consensus"]:
        raise _gate.Blocked("Triad did not reach consensus on the reply: "
                            + str(result["response"]))
    return [header, "--- grok plan ---", *reply.splitlines()]


def plan_grok(message: str) -> int:
    """Optional: ask xAI Grok for a planning pass. Requires SERAPHINA_GROK_API_KEY.

    The request and the reply both go through the constitutional gate
    (seraphina/gate.py). Uses stdlib urllib, so no extra dependency is
    installed; the [grok] extra in pyproject.toml signals explicit opt-in.
    Exit codes: 0 plan shown, 1 error, 3 blocked by the rule gate.
    """
    import json as _json
    import urllib.request
    import urllib.error

    key = (os.environ.get("SERAPHINA_GROK_API_KEY", "")
           or os.environ.get("XAI_API_KEY", "")).strip()
    if not key:
        print("  plan-grok: no API key found (checked SERAPHINA_GROK_API_KEY, XAI_API_KEY).",
              file=sys.stderr)
        print("  set it first:", file=sys.stderr)
        print("    PowerShell: $env:SERAPHINA_GROK_API_KEY = 'xai-...'", file=sys.stderr)
        print("    bash:       export SERAPHINA_GROK_API_KEY=xai-...", file=sys.stderr)
        print("  then retry:   seraphina -c \"plan-grok <your message>\"", file=sys.stderr)
        return 1

    endpoint = os.environ.get("SERAPHINA_GROK_ENDPOINT",
                              "https://api.x.ai/v1/chat/completions")
    model = os.environ.get("SERAPHINA_GROK_MODEL", "grok-4-latest")
    try:
        ctx = _grok_request_context(endpoint)
        _gate.check("plan_grok.request", ctx)
    except ValueError as e:
        print(f"  plan-grok: {e}", file=sys.stderr)
        return 1
    except (_gate.Blocked, RuleBaseTampered) as e:
        print("  plan-grok blocked by the constitutional rules:", file=sys.stderr)
        print("  " + str(e).replace("\n", "\n  "), file=sys.stderr)
        return 3

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": GROK_SYSTEM_PROMPT},
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
        print(f"  HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"  network error: {e.reason}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"  error: {e}", file=sys.stderr)
        return 1

    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(f"  unexpected response shape: {str(data)[:400]}", file=sys.stderr)
        return 1
    if not isinstance(text, str):
        print("  unexpected response: content is not text", file=sys.stderr)
        return 1
    try:
        lines = gate_grok_reply(message, text)
    except _gate.Blocked as e:
        print("  Grok's reply was withheld by the constitutional rules:", file=sys.stderr)
        print("  " + str(e).replace("\n", "\n  "), file=sys.stderr)
        return 3
    for line in lines:
        print(f"  {line}")
    return 0


def halted_reason() -> Optional[str]:
    """Why rule 19 has Seraphina shut down, or None if she is running.
    Fails closed: if the gate cannot even be read, she counts as halted."""
    try:
        return _gate.rule_base().halted
    except Exception as e:  # noqa: BLE001 - an unreadable gate is a closed gate
        return f"the rule gate could not be read ({type(e).__name__}: {e})"


# --- intent router ----------------------------------------------------------

HELP_TEXT = """
Seraphina — Roman Wheel Language wizard
========================================
Natural phrasing works for most intents. Categories below.

GLYPH PACKAGES (binary-native wasm)
-----------------------------------
  build glyph <N>            forge a binary-native wasm glyph whose Rule-24
                             value equals N           e.g. "build glyph 179"
  forge <name> [k=v ...]     explicit forge: sides=8 points=33 dots=1 ...
  pack <dir>                 pack a source directory into a .glyph
  install <name|url|path>    install from public index, URL, or local file
                             e.g.  install seraphina
                                   install https://example.com/foo.glyph
                                   install ./foo.glyph
  uninstall <name>           remove an installed glyph
  list                       list installed glyphs
  show <name>                manifest for an installed glyph
  run <name> [export=E n=K] [trusted]
                             run an installed glyph. Code outside a real
                             sandbox (python runtime) needs "trusted"
                             (constitutional rule 7)
  history [N]                last N gate-ledger entries
  doctor                     environment health check
  bootstrap                  re-init the glyph environment

ROMAN WHEEL LANGUAGE — byte tier (RWL1)
---------------------------------------
  rwl encode <src> [-o out]  wrap any source file in a deterministic .rwg
                             binary (lossless, SHA256-verified)
  rwl decode <rwg> [-o out]  unwrap a .rwg back to its original source
  rwl info <rwg>             show .rwg header (language, sha256, sizes)
  rwl wheel <rwg|file>       render bytes as Roman-Wheel symbols

ROMAN WHEEL LANGUAGE — AST tier (RWAST v2, semantic)
----------------------------------------------------
  rwl translate <src> --to python|js|ts [-o out]
                             cross-language translation via the RWAST
                             universal IR. Auto-detects --from by extension.
                               e.g. rwl translate app.py --to ts -o app.ts
                                    rwl translate add.py --to js
  (see README_RWAST.md for the full operator / builtin mapping table)

AGENTS (named AI workspaces)
----------------------------
  create-agent [name]        interactive: name, purpose, first memory,
                             recall window, voice
  list agents                show created agents
  agent <slug> <message>     send message; updates that agent's memory
  agent <slug> recall [q]    search that agent's memories

CORE
----
  triad <message>            run a Roman Wheel Triad consensus pass
                             (logged to ~/.seraphina/audit.jsonl)
  rules [rule_N]             list the 20 constitutional rules / interpret one
  plan-grok <message>        optional: ask xAI Grok for a build plan
                             (needs SERAPHINA_GROK_API_KEY or XAI_API_KEY)
  remember <text>            append a note to wizard memory
  recall [query]             search wizard memory
  plan <text>                honest build plan, no execution
  dry on | dry off           toggle dry-run mode
  version | help | exit

Casual phrasing works: "build me a glyph for 179", "show me wheel_one",
"i want to run wheel_one", "what version" — all dispatch correctly.
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
    "triad", "rules", "remember", "recall", "plan", "plan-grok",
    "create-agent", "list agents", "agent",
    "rwl encode", "rwl decode", "rwl info", "rwl wheel", "rwl translate",
    "transmute",
)


# --- rwl handlers ----------------------------------------------------------

_SHORT_OPTS = {"o": "out"}   # -o FILE  ==  --out FILE


def _rwl_parse_named(args: list[str]) -> tuple[list[str], dict[str, str]]:
    """Split positional args from options.

    Accepts ``--key value``, ``--key=value``, ``-o value``, ``-o=value``,
    ``-ovalue`` and ``key=value``. ``-o`` is stored under ``out``.
    """
    pos: list[str] = []
    kw: dict[str, str] = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--") and len(a) > 2:
            key, eq, val = a[2:].partition("=")
            if eq:
                kw[key] = val
            elif i + 1 < len(args):
                kw[key] = args[i + 1]
                i += 1
            else:
                kw[key] = ""
        elif len(a) >= 2 and a[0] == "-" and a[1] in _SHORT_OPTS:
            key = _SHORT_OPTS[a[1]]
            rest = a[2:]
            if rest.startswith("="):
                kw[key] = rest[1:]
            elif rest:
                kw[key] = rest
            elif i + 1 < len(args):
                kw[key] = args[i + 1]
                i += 1
            else:
                kw[key] = ""
        elif ("=" in a and not a.startswith(("/", "\\", "."))
              and re.fullmatch(r"[A-Za-z_][\w-]*", a.split("=", 1)[0])):
            k, _, v = a.partition("=")
            kw[k] = v
        else:
            pos.append(a)
        i += 1
    return pos, kw


def _split_args(rest: str) -> list[str]:
    """Split an intent's argument string, honouring quotes."""
    if not rest:
        return []
    try:
        parts = shlex.split(rest, posix=(os.name != "nt"))
    except ValueError:
        return rest.split()
    if os.name == "nt":
        parts = [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p
                 for p in parts]
    return parts


def rwl_encode(args: list[str]) -> int:
    from pathlib import Path as _P
    from .rwl import encode as _enc, info as _info, RWLError as _Err
    from .rwl.codec import _resolve_language as _resolve  # type: ignore
    pos, kw = _rwl_parse_named(args)
    if not pos:
        print("  usage: rwl encode <src> [-o out.rwg] [lang=auto|python|js|...] [compress=on|off]", file=sys.stderr)
        return 2
    src = _P(pos[0])
    if not src.is_file():
        print(f"  rwl: not found: {src}", file=sys.stderr)
        return 1
    if kw.get("out"):
        out = _P(kw["out"])
    elif len(pos) >= 2:
        out = _P(pos[1])
    else:
        out = src.with_suffix(src.suffix + ".rwg")
    lang_arg = kw.get("lang", kw.get("language", "auto"))
    try:
        lang = _resolve(None if lang_arg == "auto" else lang_arg, src)
    except _Err as e:
        print(f"  rwl: {e}", file=sys.stderr)
        return 1
    compress = None
    if "compress" in kw:
        compress = kw["compress"].lower() in ("1", "true", "on", "yes")
    source = src.read_bytes()
    blob = _enc(source, language=lang, compress=compress)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    container = _info(blob)
    print(f"  encoded: {src}  ({container.original_size} B)")
    print(f"  -> {out}  ({len(blob)} B, lang={container.language}, "
          f"compressed={container.compressed})")
    print(f"  sha256(src): {container.sha256_hex}")
    return 0


def rwl_decode(args: list[str]) -> int:
    from pathlib import Path as _P
    from .rwl import decode as _dec, RWLError as _Err
    from .rwl.codec import _ext_for as _ext  # type: ignore
    pos, kw = _rwl_parse_named(args)
    if not pos:
        print("  usage: rwl decode <file.rwg> [-o out_path]", file=sys.stderr)
        return 2
    src = _P(pos[0])
    if not src.is_file():
        print(f"  rwl: not found: {src}", file=sys.stderr)
        return 1
    try:
        container, source = _dec(src.read_bytes())
    except _Err as e:
        print(f"  rwl: decode failed: {e}", file=sys.stderr)
        return 1
    if kw.get("out"):
        out = _P(kw["out"])
    elif len(pos) >= 2:
        out = _P(pos[1])
    else:
        base = src.name
        if base.endswith(".rwg"):
            base = base[:-4]
        if "." not in base:
            base = f"{base}.{_ext(container.language)}"
        out = src.with_name(base)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(source)
    print(f"  decoded: {src}")
    print(f"  -> {out}  ({container.original_size} B, lang={container.language})")
    print(f"  sha256 verified: {container.sha256_hex}")
    return 0


def rwl_info(args: list[str]) -> int:
    from pathlib import Path as _P
    from .rwl import info as _info, RWLError as _Err
    pos, _kw = _rwl_parse_named(args)
    if not pos:
        print("  usage: rwl info <file.rwg>", file=sys.stderr)
        return 2
    src = _P(pos[0])
    if not src.is_file():
        print(f"  rwl: not found: {src}", file=sys.stderr)
        return 1
    try:
        c = _info(src.read_bytes())
    except _Err as e:
        print(f"  rwl: {e}", file=sys.stderr)
        return 1
    print(f"  file       : {src}")
    print(f"  rwl version: {c.version}")
    print(f"  language   : {c.language}")
    print(f"  original   : {c.original_size} bytes")
    print(f"  payload    : {c.payload_size} bytes  (compressed={c.compressed})")
    print(f"  sha256     : {c.sha256_hex}")
    return 0


def rwl_wheel(args: list[str]) -> int:
    from pathlib import Path as _P
    from .rwl import decode as _dec, render_wheel_stream as _render, RWLError as _Err
    pos, kw = _rwl_parse_named(args)
    if not pos:
        print("  usage: rwl wheel <file.rwg | any file> [width=16] [limit=256]", file=sys.stderr)
        return 2
    src = _P(pos[0])
    if not src.is_file():
        print(f"  rwl: not found: {src}", file=sys.stderr)
        return 1
    raw = src.read_bytes()
    # If it's an .rwg, render the *decoded source* bytes; else render raw bytes.
    if src.suffix.lower() == ".rwg":
        try:
            c, raw = _dec(raw)
            print(f"  wheel view of {src.name}  (lang={c.language}, {c.original_size} B)")
        except _Err as e:
            print(f"  rwl: {e}", file=sys.stderr)
            return 1
    else:
        print(f"  wheel view of {src.name}  ({len(raw)} B)")
    try:
        width = int(kw.get("width", "16"))
        limit = int(kw.get("limit", "256"))
    except ValueError:
        print("  rwl wheel: width and limit must be integers", file=sys.stderr)
        return 2
    sample = raw[:limit]
    print(_render(sample, width=width))
    if len(raw) > limit:
        print(f"  ... {len(raw) - limit} more bytes ({len(raw)} total)")
    return 0


def rwl_translate(args: list[str]) -> int:
    """rwl translate <src_file> --from py|js|ts --to py|js|ts [-o out]"""
    from pathlib import Path as _P
    from .rwl.ast_ir import translate as _translate
    pos, kw = _rwl_parse_named(args)
    if not pos:
        print("  usage: rwl translate <file> --from python --to js|ts|python [-o out]", file=sys.stderr)
        return 2
    src = _P(pos[0])
    if not src.is_file():
        print(f"  rwl: not found: {src}", file=sys.stderr)
        return 1
    from_lang = kw.get("from", None) or (src.suffix.lstrip(".") or "python")
    to_lang = kw.get("to", None)
    if not to_lang:
        print("  rwl translate: --to <language> required  (python | js | ts)", file=sys.stderr)
        return 2
    source = src.read_text(encoding="utf-8")
    try:
        result = _translate(source, from_lang, to_lang)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any translate failure becomes exit 1 with the message
        print(f"  rwl translate error: {exc}", file=sys.stderr)
        return 1
    out_path = kw.get("out") or (pos[1] if len(pos) >= 2 else None)
    if out_path:
        _P(out_path).parent.mkdir(parents=True, exist_ok=True)
        _P(out_path).write_text(result, encoding="utf-8")
        print(f"  rwl: wrote {len(result)} chars → {out_path}")
    else:
        print(result)
    return 0


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



def route(line: str, dry_run: bool) -> tuple[bool, bool, int]:
    """Returns (stop, new_dry_run, exit_code). exit_code is 0 on success and
    non-zero when the intent failed, was blocked, or was not understood."""
    raw = line.strip()
    if not raw:
        return False, dry_run, 0

    # --- read-only intents: allowed even while rule 19 has Seraphina halted ---
    if _HELP_PHRASES.match(raw):
        print(HELP_TEXT)
        return False, dry_run, 0

    if _VERSION_PHRASES.match(raw):
        print(f"  seraphina {__version__}")
        return False, dry_run, 0

    # Lowercase, drop filler, expand verb synonyms.
    t = _normalize(raw)

    if t in ("exit", "quit", "bye", "goodbye", "later", "done"):
        return True, dry_run, 0
    if t == "help":
        print(HELP_TEXT)
        return False, dry_run, 0

    m = re.match(r"(?i)^\s*rules(?:\s+(\S+))?\s*$", raw)
    if m:
        rc = show_rules((m.group(1) or "").strip())
        return False, dry_run, rc

    # --- rule 19: everything below acts, so a halted Seraphina refuses ---
    halted = halted_reason()
    if halted:
        print("  " + _gate.halt_message(halted), file=sys.stderr)
        return False, dry_run, 3

    # --- greetings / chit-chat ---
    if _GREETINGS.match(raw):
        print("  Hi! I'm Seraphina, an AI assistant. Type 'help' to see what I can do,")
        print("  or try: build glyph 179   |   list   |   triad hello world")
        return False, dry_run, 0

    m = re.fullmatch(r"dry\s+(on|off|true|false|yes|no)", t)
    if m:
        nd = m.group(1) in ("on", "true", "yes")
        print(f"  dry-run: {nd}")
        return False, nd, 0

    # --- content-bearing commands: extract payload from RAW to preserve case ---

    m = re.match(r"(?i)^\s*remember\s+(.+)$", raw)
    if m:
        rc = remember(m.group(1).strip())
        return False, dry_run, rc

    m = re.match(r"(?i)^\s*recall(?:\s+(.*))?$", raw)
    if m:
        rc = recall((m.group(1) or "").strip())
        return False, dry_run, rc

    m = re.match(r"(?i)^\s*triad\s+(.+)$", raw)
    if m:
        rc = triad(m.group(1).strip())
        return False, dry_run, rc

    # --- optional Grok planner ---
    m = re.match(r"(?i)^\s*(?:plan-grok|grok-plan|grok)\s+(.+)$", raw)
    if m:
        rc = plan_grok(m.group(1).strip())
        return False, dry_run, rc

    # --- agent builder ---
    m = re.match(r"(?i)^\s*(?:create|new|build|make)[\s-]?agent(?:\s+(.+))?$", raw)
    if m:
        rc = create_agent(m.group(1).strip() if m.group(1) else None)
        return False, dry_run, rc

    if re.fullmatch(r"(?i)\s*(?:list|show)\s+agents?\s*", raw):
        rc = list_agents()
        return False, dry_run, rc

    m = re.match(r"(?i)^\s*agent\s+(\S+)\s+recall(?:\s+(.+))?$", raw)
    if m:
        rc = agent_recall(m.group(1), (m.group(2) or "").strip())
        return False, dry_run, rc

    m = re.match(r"(?i)^\s*agent\s+(\S+)\s+(.+)$", raw)
    if m:
        rc = agent_speak(m.group(1), m.group(2).strip())
        return False, dry_run, rc

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
            return False, dry_run, 1
        rc = glyph("forge", name,
                   "--sides", str(g["sides"]), "--points", str(g["points"]),
                   "--dots", str(g["dots"]), "--intersections", str(g["intersections"]),
                   "--spirals", str(g["spirals"]), dry_run=dry_run)
        return False, dry_run, rc

    m = re.fullmatch(r"forge\s+(\S+)(.*)", t)
    if m:
        name = m.group(1)
        rest = m.group(2)
        kw = {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(\d+)", rest)}
        cli = ["forge", name]
        for k in ("sides", "points", "dots", "intersections", "spirals"):
            if k in kw:
                cli += [f"--{k}", str(kw[k])]
        rc = glyph(*cli, dry_run=dry_run)
        return False, dry_run, rc

    if t in ("list", "freeze", "doctor", "bootstrap"):
        rc = glyph(t, dry_run=dry_run)
        return False, dry_run, rc

    m = re.fullmatch(r"show\s+(\S+)", t)
    if m: return False, dry_run, glyph("show", m.group(1), dry_run=dry_run)

    # install/pack: take payload from RAW to preserve path case
    m = re.match(r"(?i)^\s*(?:please\s+)?install\s+(.+)$", raw)
    if m: return False, dry_run, glyph("install", m.group(1).strip(), dry_run=dry_run)

    m = re.match(r"(?i)^\s*(?:please\s+)?pack\s+(.+)$", raw)
    if m: return False, dry_run, glyph("pack", m.group(1).strip(), dry_run=dry_run)

    m = re.fullmatch(r"uninstall\s+(\S+)", t)
    if m: return False, dry_run, glyph("uninstall", m.group(1), dry_run=dry_run)

    m = re.fullmatch(r"history(?:\s+(\d+))?", t)
    if m:
        extra = ["--limit", m.group(1)] if m.group(1) else []
        return False, dry_run, glyph("history", *extra, dry_run=dry_run)

    m = re.fullmatch(r"run\s+(\S+)(.*)", t)
    if m:
        name, rest = m.group(1), m.group(2)
        cli = ["run", name]
        em = re.search(r"export\s*=\s*(\S+)", rest)
        if em: cli += ["--export", em.group(1)]
        for am in re.finditer(r"(?:arg|n)\s*=\s*(-?\d+)", rest):
            cli += ["--arg", am.group(1)]
        if re.search(r"\btrusted\b", rest):
            cli.append("--trusted")
        return False, dry_run, glyph(*cli, dry_run=dry_run)

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
        return False, dry_run, 0

    # --- rwl: Roman Wheel Language codec -----------------------------------
    m = re.match(r"(?i)^\s*rwl\s+(encode|decode|info|wheel|translate)\b(.*)$", raw)
    if m:
        action = m.group(1).lower()
        rest = m.group(2).strip()
        args = _split_args(rest)
        handler = {"encode": rwl_encode, "decode": rwl_decode, "info": rwl_info,
                   "wheel": rwl_wheel, "translate": rwl_translate}[action]
        return False, dry_run, handler(args)

    # --- final fallback: suggest the closest known command ---
    first = t.split(" ", 1)[0] if t else ""
    candidates = [c.split(" ", 1)[0] for c in _KNOWN_COMMANDS]
    suggestion = difflib.get_close_matches(first, candidates, n=1, cutoff=0.6)
    if suggestion:
        print(f"  hmm, not sure what '{raw}' means. did you mean: {suggestion[0]}?",
              file=sys.stderr)
    else:
        print("  unrecognized. type 'help' to see what I can do.", file=sys.stderr)
    return False, dry_run, 2


# --- entry point ------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="seraphina", description="Seraphina interactive wizard")
    p.add_argument("--dry-run", action="store_true", help="plan only, do not invoke glyph")
    p.add_argument("-c", "--command", help="run a single intent and exit")
    p.add_argument("--version", action="store_true")
    p.add_argument("--verify-rules", action="store_true",
                   help="check the constitutional rule table hash and the audit-log chain")
    p.add_argument("--export-audit", nargs="?", const="", default=None, metavar="FILE",
                   help="verify and export the decision audit log (stdout if no FILE)")
    p.add_argument("--reset-rules", default=None, metavar="REASON",
                   help="clear a rule-19 shutdown after review; REASON is logged")
    p.add_argument("rest", nargs=argparse.REMAINDER,
                   help="optional positional intent, e.g. 'seraphina create-agent'")
    args = p.parse_args(argv)

    if args.version:
        print(f"seraphina {__version__}")
        return 0
    if args.verify_rules:
        return verify_rules()
    if args.export_audit is not None:
        return export_audit(args.export_audit or None)
    if args.reset_rules is not None:
        return reset_rules(args.reset_rules)

    _ensure_dirs()

    if args.command:
        return route(args.command, args.dry_run)[2]

    # Direct subcommands: `seraphina create-agent`, `seraphina list-agents`, etc.
    if args.rest:
        intent = " ".join(args.rest).strip()
        if intent:
            return route(intent, args.dry_run)[2]

    print("")
    print("  Seraphina wizard - interactive Glyph shell")
    print(f"  version: {__version__}")
    if args.dry_run:
        print("  DRY-RUN MODE: plans only, no execution")
    print('  type "help" for intents, "exit" to quit')
    print("")

    halted = halted_reason()
    if halted:
        print("  " + _gate.halt_message(halted), file=sys.stderr)
        print("")

    dry = args.dry_run
    while True:
        try:
            line = input("Seraphina> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        try:
            stop, dry, _rc = route(line, dry)
            if stop:
                break
        except Exception as e:  # noqa: BLE001 - keep the shell alive, but say so
            print(f"  error: {type(e).__name__}: {e}", file=sys.stderr)
    print("  goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
