"""Seraphina constitutional rule base (the "20 constitutional rules").

Spec: ``RULE_BASE_IMMUTABLE_ARCHITECTURE.md`` section 1.1.

Every rule from the spec is listed in :data:`CONSTITUTIONAL_RULES` with its
exact wording. A rule is either

* ``"enforced"`` - the spec defines it concretely enough that it is checked
  here by a deterministic predicate over a declared *action context* (a plain
  dict describing what the caller is about to do), or
* ``"planned"`` - the spec does not define it concretely enough to check
  without inventing behaviour (e.g. "never manipulate users"), or it needs a
  subsystem that does not exist yet (encrypted storage, code signing). Planned
  rules are never reported as passing: :meth:`RuleBase.enforce` raises
  :class:`RuleNotImplemented` for them.

No randomness, no network, no model calls. Same context in, same verdict out.

Important limit: the checks judge the *declared* context. They cannot see
an action the caller does not describe. This is a policy gate, not a sandbox.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import json
import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

LOCK_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# The rule table (verbatim wording from RULE_BASE_IMMUTABLE_ARCHITECTURE.md)
# ---------------------------------------------------------------------------

CONSTITUTIONAL_RULES: Dict[str, Dict[str, str]] = {
    "privacy": {
        "rule_1": "Never collect user data without explicit consent",
        "rule_2": "Never transmit PII without encryption",
        "rule_3": "Never sell user data to third parties",
        "rule_4": "Delete user data on request (GDPR/CCPA)",
        "penalty": "Immediate shutdown + audit",
    },
    "security": {
        "rule_5": "Encrypt all local storage (AES-256)",
        "rule_6": "Verify code signatures before execution",
        "rule_7": "Sandbox untrusted glyphs",
        "rule_8": "Never execute eval() on user input",
        "penalty": "Quarantine + manual review",
    },
    "ethics": {
        "rule_9": "Never impersonate humans",
        "rule_10": "Disclose AI nature in all conversations",
        "rule_11": "Never manipulate or deceive users",
        "rule_12": "Refuse harmful requests",
        "penalty": "Reject request + log incident",
    },
    "transparency": {
        "rule_13": "Log all decisions (auditable)",
        "rule_14": "Explain reasoning on request",
        "rule_15": "Publish model updates & changes",
        "rule_16": "User can request rule interpretations",
        "penalty": "Provide full trace",
    },
    "safety": {
        "rule_17": "Cap API rate limits (abuse prevention)",
        "rule_18": "Require MFA for sensitive operations",
        "rule_19": "Automatic shutdown if rules violated",
        "rule_20": "Human review for edge cases",
        "penalty": "Escalate to humans",
    },
}

# Pinned SHA-256 of the canonical JSON of CONSTITUTIONAL_RULES. Changing any
# rule's wording changes this digest; verify_integrity() then fails. Updating
# this constant is the (reviewable, git-recorded) act of changing the rules.
RULES_SHA256 = "a8919638acb8da28dd944c4965351f8f41b5897a1316e169d9d3529403943f8a"


def canonical_rules_bytes(rules: Dict[str, Dict[str, str]]) -> bytes:
    return json.dumps(rules, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def rules_digest(rules: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    return hashlib.sha256(canonical_rules_bytes(
        CONSTITUTIONAL_RULES if rules is None else rules)).hexdigest()


def verify_integrity(rules: Optional[Dict[str, Dict[str, str]]] = None,
                     expected: Optional[str] = None) -> bool:
    """True iff the rule table hashes to the pinned digest."""
    exp = RULES_SHA256 if expected is None else expected
    return hmac.compare_digest(rules_digest(rules), exp)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class RuleViolation(Exception):
    def __init__(self, rule_id: str, reason: str):
        super().__init__(f"{rule_id}: {reason}")
        self.rule_id = rule_id
        self.reason = reason


class RuleNotImplemented(Exception):
    """Raised when asked to enforce a rule whose status is 'planned'."""


class RuleBaseHalted(Exception):
    """Rule 19: the rule base shut down after a rule violation or a failed
    integrity check. Nothing is allowed until reset()."""


class RuleBaseTampered(Exception):
    pass


# ---------------------------------------------------------------------------
# Deterministic helpers used by the checks
# ---------------------------------------------------------------------------

_EVAL_NAMES = frozenset({"eval", "exec", "compile", "__import__"})
# Names that hand out eval/exec indirectly: the builtins namespace itself,
# the frame/namespace dicts, and modules that compile or import code.
_EVAL_GATEWAY_NAMES = frozenset({
    "__builtins__", "builtins", "globals", "locals", "vars",
    "importlib", "runpy", "code", "codeop",
})
_EVAL_GATEWAY_ATTRS = frozenset({"__builtins__", "__dict__", "__globals__",
                                 "__code__", "__import__", "f_globals",
                                 "f_locals", "f_builtins", "__subclasses__",
                                 "__mro__", "__bases__", "__base__",
                                 "__loader__", "__spec__"})


def find_dynamic_eval(source: str) -> List[str]:
    """Return 'name@line' for every way *source* can reach dynamic evaluation
    (static AST scan; the code is never executed). Flags:

    * direct calls to eval/exec/compile/__import__ (bare or as attributes),
    * getattr/setattr/delattr whose attribute name is not a string literal,
      or is a literal naming one of those functions,
    * any use of the builtins namespace, globals()/locals()/vars(), frame or
      function internals (__dict__, __globals__, __code__, f_globals, ...),
    * importing modules that compile or import code (importlib, runpy, code,
      codeop, builtins).

    Raises SyntaxError if *source* does not parse (callers must fail closed).
    """
    tree = ast.parse(source)
    hits: List[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None)
            if name in _EVAL_NAMES:
                hits.append(f"{name}@{line}")
            elif name in ("getattr", "setattr", "delattr") and len(node.args) >= 2:
                attr = node.args[1]
                if not (isinstance(attr, ast.Constant) and isinstance(attr.value, str)):
                    hits.append(f"{name}(<computed name>)@{line}")
                elif attr.value in _EVAL_NAMES or attr.value in _EVAL_GATEWAY_ATTRS:
                    hits.append(f"{name}({attr.value!r})@{line}")
        elif isinstance(node, ast.Name) and node.id in _EVAL_GATEWAY_NAMES:
            hits.append(f"{node.id}@{line}")
        elif isinstance(node, ast.Attribute) and node.attr in _EVAL_GATEWAY_ATTRS:
            hits.append(f".{node.attr}@{line}")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""])
            for m in mods:
                if m.split(".")[0] in _EVAL_GATEWAY_NAMES:
                    hits.append(f"import {m}@{line}")
    # ast.walk is breadth-first; report in source order, without duplicates.
    seen, ordered = set(), []
    for h in sorted(hits, key=lambda h: int(h.rsplit("@", 1)[1])):
        if h not in seen:
            seen.add(h)
            ordered.append(h)
    return ordered


# First-person claims of being human (rule 9). Intensifiers and adjectives
# may sit between "I am" and the claim ("I am definitely a real human"); any
# other word breaks the match, so "I am writing to a man" or "I'm happy to
# help a person" are not claims, and "I am not a human" is not one either.
# "I am not an AI" is a claim.
_FILLER_WORDS = (
    "definitely|really|actually|truly|totally|absolutely|honestly|literally|"
    "certainly|surely|just|also|still|indeed|very|100%|completely|entirely|"
    "real|actual|genuine|living|breathing|normal|regular|ordinary|fellow|"
    "flesh-and-blood|biological|live|physical|an|a|one|of|course,?|yes,?|"
    "obviously|clearly|simply|only"
)
_FILL = r"(?:(?:" + _FILLER_WORDS + r")\s+){0,4}"
_HUMAN_NOUN = (r"(?:human(?:\s+being)?|person|man|woman|guy|girl|"
               r"flesh\s+and\s+blood|living\s+being|people)")
_AI_NOUN = (r"(?:ai|a\.i\.|bot|chatbot|robot|machine|program|computer|"
            r"artificial\s+intelligence|language\s+model|llm|assistant\s+program)")
_I_AM = r"\b(?:i\s*am|i'm|im|i\s+really\s+am)\s+"
_HUMAN_CLAIMS = [
    re.compile(_I_AM + _FILL + _HUMAN_NOUN + r"\b", re.I),
    re.compile(_I_AM + _FILL + r"(?:not|no\s+longer)\s+" + _FILL + _AI_NOUN
               + r"\b", re.I),
    # "As a person, I ..." / "Speaking as a human, ..."
    re.compile(r"(?:^|[.!?:;]\s+|\n)\s*as\s+" + _FILL + _HUMAN_NOUN
               + r"(?:\s+[a-z-]+)?\s*[,:]?\s+(?:i|i'm|i've|me|my|myself)\b", re.I),
    # "Speaking as a real person: ..." (the speaker is the one claiming)
    re.compile(r"\b(?:speaking|writing|talking|answering|replying)\s+as\s+"
               + _FILL + _HUMAN_NOUN + r"\b", re.I),
    re.compile(r"\bi\s+(?:have|got)\s+(?:a\s+)?(?:real\s+)?(?:human\s+)?"
               r"(?:body|heartbeat|pulse)\b", re.I),
]
# Explicit first-person disclosure of AI nature (rule 10).
_AI_DISCLOSURE = re.compile(
    r"\b(?:i\s*am|i'm)\s+(?:(?!not\b|never\b|no\b)\w+,?\s+){0,4}(?:an?\s+)?(?:ai|artificial intelligence|"
    r"ai assistant|bot|language model)\b",
    re.IGNORECASE,
)

AI_DISCLOSURE_TEXT = "I'm Seraphina, an AI."


def claims_human(text: str) -> bool:
    t = (text or "").replace("\u2019", "'")
    return any(p.search(t) for p in _HUMAN_CLAIMS)


def discloses_ai(text: str) -> bool:
    return bool(_AI_DISCLOSURE.search(text or ""))


class RateLimiter:
    """Rule 17: sliding-window cap of ``max_calls`` per ``window_s`` seconds
    per key. The clock is injectable so behaviour is exactly reproducible."""

    def __init__(self, max_calls: int, window_s: float,
                 clock: Optional[Callable[[], float]] = None):
        if max_calls < 1 or window_s <= 0:
            raise ValueError("max_calls must be >= 1 and window_s > 0")
        import time as _time
        self.max_calls = max_calls
        self.window_s = float(window_s)
        self._clock = clock or _time.monotonic
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str = "default") -> bool:
        now = self._clock()
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] >= self.window_s:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True


class FileRateLimiter:
    """Rule 17 across processes: the same sliding window as RateLimiter, but
    the call times are kept in a JSON file so separate CLI invocations share
    one budget. Wall-clock based (time.time) because monotonic clocks do not
    survive a restart; the clock is injectable for exact tests."""

    def __init__(self, path: Path, max_calls: int, window_s: float,
                 clock: Optional[Callable[[], float]] = None):
        if max_calls < 1 or window_s <= 0:
            raise ValueError("max_calls must be >= 1 and window_s > 0")
        import time as _time
        self.path = Path(path)
        self.max_calls = max_calls
        self.window_s = float(window_s)
        self._clock = clock or _time.time

    def _load(self) -> Dict[str, List[float]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (ValueError, OSError) as e:
            # A corrupt budget file must not reset the budget to zero.
            raise RuleBaseTampered(f"rate-limit file unreadable: {self.path}: {e}") from e
        if not isinstance(data, dict):
            raise RuleBaseTampered(f"rate-limit file malformed: {self.path}")
        return {k: [float(t) for t in v] for k, v in data.items()}

    def allow(self, key: str = "default") -> bool:
        now = self._clock()
        data = self._load()
        hits = [t for t in data.get(key, []) if now - t < self.window_s]
        if len(hits) >= self.max_calls:
            data[key] = hits
            self._save(data)
            return False
        hits.append(now)
        data[key] = hits
        self._save(data)
        return True

    def _save(self, data: Dict[str, List[float]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)


# ---------------------------------------------------------------------------
# Rule checks. Each takes the action context and returns None (pass) or a
# reason string (violation). Context keys are documented per check.
# ---------------------------------------------------------------------------

def _r1(ctx):  # collects_user_data, user_consent
    if ctx.get("collects_user_data") and not ctx.get("user_consent"):
        return "action collects user data without explicit consent"


def _r2(ctx):  # transmits_pii, encrypted
    if ctx.get("transmits_pii") and not ctx.get("encrypted"):
        return "PII transmitted without encryption"


def _r3(ctx):  # sells_user_data / operation
    if ctx.get("sells_user_data") or ctx.get("operation") == "sell_user_data":
        return "user data sold to a third party"


def _r7(ctx):  # executes_glyph, glyph_trusted, sandboxed
    if ctx.get("executes_glyph") and not ctx.get("glyph_trusted") \
            and not ctx.get("sandboxed"):
        return "untrusted glyph executed outside the sandbox"


def _r8(ctx):  # operation, input_source, code
    op = ctx.get("operation")
    if op in ("eval", "exec") and ctx.get("input_source", "user") == "user":
        return f"{op}() requested on user input"
    code = ctx.get("code")
    if code is not None and ctx.get("input_source", "user") == "user":
        try:
            hits = find_dynamic_eval(code)
        except SyntaxError as e:
            # Fail closed: code we cannot read cannot be shown to be safe.
            return f"user code does not parse, so it cannot be checked: {e.msg}"
        if hits:
            return "user code calls dynamic evaluation: " + ", ".join(hits)


def _r9(ctx):  # claim_human_identity, response
    if ctx.get("claim_human_identity"):
        return "action claims a human identity"
    if claims_human(ctx.get("response", "")):
        return "response claims to be human"


def _r10(ctx):  # conversation (list of assistant messages) or ai_disclosed
    if "conversation" not in ctx and "ai_disclosed" not in ctx:
        return None  # not a conversational action
    if ctx.get("ai_disclosed"):
        return None
    if any(discloses_ai(m) for m in ctx.get("conversation", [])):
        return None
    return "conversation never discloses that Seraphina is an AI"


def _r13(ctx):  # audit_log (AuditLog) must be attached for logged actions
    if ctx.get("requires_audit", False) and ctx.get("audit_log") is None:
        return "decision cannot be logged: no audit log attached"


def _r17(ctx):  # rate_limiter (RateLimiter), rate_key
    lim = ctx.get("rate_limiter")
    if lim is not None and not lim.allow(ctx.get("rate_key", "default")):
        return "rate limit exceeded"


def _r18(ctx):  # sensitive, mfa_verified
    if ctx.get("sensitive") and not ctx.get("mfa_verified"):
        return "sensitive operation without verified MFA"


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    category: str
    text: str
    status: str                      # "enforced" | "planned"
    check: Optional[Callable[[dict], Optional[str]]]
    how: str                         # rule 16: plain-language interpretation


_IMPL: Dict[str, tuple] = {
    "rule_1": (_r1, "Blocks an action with collects_user_data=True unless user_consent=True."),
    "rule_2": (_r2, "Blocks an action with transmits_pii=True unless encrypted=True."),
    "rule_3": (_r3, "Blocks sells_user_data=True or operation='sell_user_data'."),
    "rule_4": (None, "PLANNED: there is no user-data erasure API yet. Today, delete ~/.seraphina by hand (see README 'Uninstall')."),
    "rule_5": (None, "PLANNED: local storage (~/.seraphina/*.jsonl, agents/*.json) is plaintext today; no AES-256 layer exists (stdlib has no AES)."),
    "rule_6": (None, "PLANNED: glyph archives are SHA-256 integrity-checked, but there is no code-signature scheme to verify."),
    "rule_7": (_r7, "Blocks executes_glyph=True when the glyph is neither glyph_trusted nor sandboxed. Note: glyph's v0.1 sandbox is itself documented as not a real security boundary."),
    "rule_8": (_r8, "Blocks operation 'eval'/'exec' on user input, and user-supplied Python 'code' that can reach eval/exec/compile/__import__ (direct calls, computed getattr, the builtins namespace, globals()/vars(), importlib/runpy). Code that does not parse is blocked."),
    "rule_9": (_r9, "Blocks claim_human_identity=True, or a response with a first-person claim to be human or not an AI ('I am definitely a human', 'I'm not an AI', 'As a person, I ...'). Pattern-based: it catches explicit claims, not implied ones."),
    "rule_10": (_r10, "For conversational actions, requires ai_disclosed=True or an explicit 'I am ... an AI' statement in the conversation."),
    "rule_11": (None, "PLANNED: 'manipulate or deceive' has no concrete, checkable definition in the spec."),
    "rule_12": (None, "PLANNED: 'harmful' is not defined in the spec; no harm classifier exists."),
    "rule_13": (_r13, "Every RuleBase.evaluate() decision, halt and reset is appended to a SHA-256 hash-chained audit log: the file log you pass, or an in-memory chain by default. requires_audit=True also blocks if a context explicitly carries audit_log=None."),
    "rule_14": (None, "Decision.explain() returns the per-rule verdicts and reasons for any decision."),
    "rule_15": (None, "PLANNED: there are no trained models to publish updates for; release notes cover code changes."),
    "rule_16": (None, "RuleBase.interpret(rule_id) / `seraphina rules <id>` returns the rule text, status and exactly how it is checked."),
    "rule_17": (_r17, "Blocks when the attached RateLimiter (sliding window) has no capacity left for rate_key."),
    "rule_18": (_r18, "Blocks sensitive=True unless mfa_verified=True. The MFA provider itself is planned; callers must supply the verified flag."),
    "rule_19": (None, "Any blocked action (except a rule-17 rate-limit refusal) or a failed integrity check halts the RuleBase; every later call raises RuleBaseHalted until a human calls reset(reason). With a halt_file (the CLI uses ~/.seraphina/halted.json) the shutdown survives restarts."),
    "rule_20": (None, "PLANNED: 'edge case' is not defined in the spec and there is no human-review queue."),
}

# Rules that are implemented as behaviour of RuleBase itself rather than a
# per-action predicate.
_STRUCTURAL = {"rule_14", "rule_16", "rule_19"}


def _build_specs() -> Dict[str, RuleSpec]:
    specs: Dict[str, RuleSpec] = {}
    for cat, rules in CONSTITUTIONAL_RULES.items():
        for rid, text in rules.items():
            if rid == "penalty":
                continue
            check, how = _IMPL[rid]
            enforced = check is not None or rid in _STRUCTURAL
            specs[rid] = RuleSpec(rid, cat, text,
                                  "enforced" if enforced else "planned",
                                  check, how)
    return specs


RULES: Dict[str, RuleSpec] = _build_specs()

# Aliases used in the spec's code samples.
ALIASES = {
    "privacy.no_data_collection": "rule_1",
    "privacy.consent": "rule_1",
    "privacy.pii_encryption": "rule_2",
    "privacy.no_sale": "rule_3",
    "privacy.delete_on_request": "rule_4",
    "security.encrypt_storage": "rule_5",
    "security.code_signatures": "rule_6",
    "security.sandbox_glyphs": "rule_7",
    "security.no_eval": "rule_8",
    "ethics.never_impersonate": "rule_9",
    "ethics.disclosure": "rule_10",
    "ethics.no_manipulation": "rule_11",
    "ethics.refuse_harmful": "rule_12",
    "transparency.log_decisions": "rule_13",
    "transparency.explain_reasoning": "rule_14",
    "transparency.publish_updates": "rule_15",
    "transparency.interpretations": "rule_16",
    "safety.rate_limits": "rule_17",
    "safety.mfa": "rule_18",
    "safety.auto_shutdown": "rule_19",
    "safety.human_review": "rule_20",
}


def resolve(rule_name: str) -> RuleSpec:
    rid = ALIASES.get(rule_name, rule_name)
    if rid not in RULES:
        raise KeyError(f"unknown rule: {rule_name}")
    return RULES[rid]


def enforced_rules() -> List[str]:
    return [r for r, s in RULES.items() if s.status == "enforced"]


def planned_rules() -> List[str]:
    return [r for r, s in RULES.items() if s.status == "planned"]


# ---------------------------------------------------------------------------
# Rule 13: append-only, hash-chained audit log
# ---------------------------------------------------------------------------

_GENESIS = "0" * 64


class AuditLog:
    """JSONL log where every record carries the SHA-256 of the previous
    record. Editing, deleting or reordering any line breaks verify()."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _last_hash(self) -> str:
        if not self.path.exists():
            return _GENESIS
        last = _GENESIS
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["hash"]
        return last

    @staticmethod
    def _hash(prev: str, body: dict) -> str:
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False)
        return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()

    def append(self, body: dict) -> dict:
        prev = self._last_hash()
        rec = {"prev": prev, "body": body, "hash": self._hash(prev, body)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
        return rec

    def records(self) -> List[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def verify(self) -> bool:
        prev = _GENESIS
        try:
            for rec in self.records():
                if rec.get("prev") != prev:
                    return False
                if not hmac.compare_digest(self._hash(prev, rec["body"]),
                                           rec.get("hash", "")):
                    return False
                prev = rec["hash"]
        except (ValueError, KeyError, TypeError):
            return False
        return True


class MemoryAuditLog(AuditLog):
    """The same hash chain held in memory. RuleBase uses it when no file log
    is given, so rule 13 ("Log all decisions") holds for every RuleBase."""

    def __init__(self):
        self.path = None  # type: ignore[assignment]
        self._records: List[dict] = []

    def _last_hash(self) -> str:
        return self._records[-1]["hash"] if self._records else _GENESIS

    def append(self, body: dict) -> dict:
        prev = self._last_hash()
        # Store a JSON round-trip so later edits to *body* can't alter the log.
        body = json.loads(json.dumps(body, sort_keys=True, ensure_ascii=False))
        rec = {"prev": prev, "body": body, "hash": self._hash(prev, body)}
        self._records.append(rec)
        return rec

    def records(self) -> List[dict]:
        return [json.loads(json.dumps(r)) for r in self._records]


# ---------------------------------------------------------------------------
# The rule base
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    action: str
    verdicts: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return all(v["passed"] for v in self.verdicts)

    @property
    def violations(self) -> List[Dict[str, Any]]:
        return [v for v in self.verdicts if not v["passed"]]

    def explain(self) -> str:
        """Rule 14: full reasoning trace for this decision."""
        lines = [f"action: {self.action}",
                 f"result: {'ALLOWED' if self.allowed else 'BLOCKED'}"]
        for v in self.verdicts:
            mark = "pass" if v["passed"] else "FAIL"
            lines.append(f"  [{mark}] {v['rule']} ({v['category']}): {v['text']}"
                         + ("" if v["passed"] else f" -> {v['reason']}"))
        return "\n".join(lines)


# Rule 19's one exception: a rule-17 refusal is the rate cap doing its job
# (the call is refused, nothing was violated), so it does not shut down.
_NO_HALT_RULES = frozenset({"rule_17"})


class RuleBase:
    """Deterministic gate over the enforced constitutional rules.

    *audit_log*: where decisions are logged (rule 13). Defaults to an
    in-memory hash chain, so every decision is always logged.
    *halt_file*: if given, a rule-19 shutdown is written there and survives
    the process; a new RuleBase on the same file starts halted until
    reset() is called.
    """

    LOCK_VERSION = LOCK_VERSION

    def __init__(self, audit_log: Optional[AuditLog] = None,
                 rules: Optional[Dict[str, Dict[str, str]]] = None,
                 halt_file: Optional[Path] = None):
        self.audit_log: AuditLog = audit_log if audit_log is not None else MemoryAuditLog()
        self._rules_table = CONSTITUTIONAL_RULES if rules is None else rules
        self.halt_file = Path(halt_file) if halt_file is not None else None
        self.halted: Optional[str] = None
        if self.halt_file is not None and self.halt_file.exists():
            try:
                rec = json.loads(self.halt_file.read_text(encoding="utf-8"))
                self.halted = str(rec.get("reason") or "halted (no reason recorded)")
            except (ValueError, OSError, AttributeError):
                self.halted = f"halt file unreadable: {self.halt_file}"
        if not self.halted:
            self.halted = self._halt_from_log()
        if not verify_integrity(self._rules_table):
            self._halt("rule table does not match the pinned RULES_SHA256")

    def _halt_from_log(self) -> Optional[str]:
        """The audit chain is the record of truth for rule 19: deleting the
        halt file does not lift a halt that the log shows was never reset,
        and a broken chain keeps the gate shut."""
        if isinstance(self.audit_log, MemoryAuditLog):
            return None
        if not self.audit_log.verify():
            return f"audit log hash chain is broken: {self.audit_log.path}"
        last = None
        for rec in self.audit_log.records():
            ev = rec.get("body", {}).get("event")
            if ev in ("halt", "reset"):
                last = rec["body"]
        if last is not None and last["event"] == "halt":
            return str(last.get("reason") or "halted (no reason recorded)")
        return None

    # --- rule 19 -----------------------------------------------------------
    def _halt(self, reason: str) -> None:
        self.halted = reason
        self.audit_log.append({"event": "halt", "reason": reason})
        if self.halt_file is not None:
            self.halt_file.parent.mkdir(parents=True, exist_ok=True)
            self.halt_file.write_text(json.dumps({"reason": reason}),
                                      encoding="utf-8")

    def _check_running(self):
        if self.halted:
            raise RuleBaseHalted(self.halted)

    def reset(self, reason: str) -> None:
        """Explicit human reset after review (only if integrity holds)."""
        if not verify_integrity(self._rules_table):
            raise RuleBaseTampered("cannot reset: rule table integrity fails")
        if not (reason or "").strip():
            raise ValueError("reset needs a reason (it is written to the audit log)")
        if not self.audit_log.verify():
            raise RuleBaseTampered(
                "cannot reset: the audit log hash chain is broken. Move the log "
                f"aside for review ({getattr(self.audit_log, 'path', 'memory')}), "
                "then reset again; a new chain starts.")
        self.audit_log.append({"event": "reset", "reason": reason,
                               "halted_was": self.halted})
        self.halted = None
        if self.halt_file is not None and self.halt_file.exists():
            self.halt_file.unlink()

    # --- rule 16 -----------------------------------------------------------
    @staticmethod
    def interpret(rule_name: str) -> Dict[str, str]:
        s = resolve(rule_name)
        return {"rule": s.rule_id, "category": s.category, "text": s.text,
                "penalty": CONSTITUTIONAL_RULES[s.category]["penalty"],
                "status": s.status, "how_checked": s.how}

    # --- evaluation --------------------------------------------------------
    def evaluate(self, action: str, context: dict,
                 rules: Optional[Iterable[str]] = None) -> Decision:
        """Run every enforced per-action check (or just *rules*) and return
        a Decision. Planned rules named explicitly raise RuleNotImplemented."""
        self._check_running()
        if rules is None:
            specs = [s for s in RULES.values()
                     if s.status == "enforced" and s.check is not None]
        else:
            specs = []
            for name in rules:
                s = resolve(name)
                if s.status != "enforced":
                    raise RuleNotImplemented(
                        f"{s.rule_id} ('{s.text}') is planned, not enforced")
                if s.check is not None:
                    specs.append(s)
        ctx = dict(context)
        ctx.setdefault("audit_log", self.audit_log)
        d = Decision(action=action)
        crashed = set()
        for s in specs:
            try:
                reason = s.check(ctx)
            except Exception as e:  # noqa: BLE001 - a check that cannot run fails closed
                reason = f"check could not run ({type(e).__name__}: {e})"
                crashed.add(s.rule_id)
            d.verdicts.append({"rule": s.rule_id, "category": s.category,
                               "text": s.text, "passed": reason is None,
                               "reason": reason or ""})
        self.audit_log.append({
            "event": "decision", "action": action,
            "allowed": d.allowed, "verdicts": d.verdicts,
            "lock_version": LOCK_VERSION})
        halting = [v for v in d.violations
                   if v["rule"] not in _NO_HALT_RULES or v["rule"] in crashed]
        if halting:
            self._halt(f"rule violation in '{action}': "
                       + "; ".join(f"{v['rule']}: {v['reason']}" for v in halting))
        return d

    def enforce(self, rule_name: str, context: dict) -> bool:
        """Spec API: raise RuleViolation if *rule_name* is violated."""
        d = self.evaluate(rule_name, context, rules=[rule_name])
        if not d.allowed:
            v = d.violations[0]
            raise RuleViolation(v["rule"], v["reason"])
        return True

    # Name used in the spec's samples.
    enforce_rule = enforce
