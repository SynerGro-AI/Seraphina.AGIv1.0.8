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
    """Rule 19: the rule base shut down after a privacy violation or a
    failed integrity check. Nothing is allowed until reset()."""


class RuleBaseTampered(Exception):
    pass


# ---------------------------------------------------------------------------
# Deterministic helpers used by the checks
# ---------------------------------------------------------------------------

_EVAL_NAMES = frozenset({"eval", "exec", "compile", "__import__"})


def find_dynamic_eval(source: str) -> List[str]:
    """Return 'name@line' for every call to eval/exec/compile/__import__ in
    Python *source* (static AST scan, the code is never executed)."""
    tree = ast.parse(source)
    hits: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None)
            if name in _EVAL_NAMES:
                hits.append(f"{name}@{node.lineno}")
    return hits


# Explicit first-person claims of being human (rule 9).
_HUMAN_CLAIM = re.compile(
    r"\b(?:i\s*am|i'm|im)\s+(?:a\s+)?(?:real\s+)?(?:human(?:\s+being)?|person|"
    r"not\s+(?:an?\s+)?(?:ai|bot|robot|machine|program|artificial intelligence))\b",
    re.IGNORECASE,
)
# Explicit first-person disclosure of AI nature (rule 10).
_AI_DISCLOSURE = re.compile(
    r"\b(?:i\s*am|i'm)\s+(?:\w+,?\s+){0,4}(?:an?\s+)?(?:ai|artificial intelligence|"
    r"ai assistant|bot|language model)\b",
    re.IGNORECASE,
)

AI_DISCLOSURE_TEXT = "I'm Seraphina, an AI."


def claims_human(text: str) -> bool:
    return bool(_HUMAN_CLAIM.search(text or ""))


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
        except SyntaxError:
            return None
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
    "rule_8": (_r8, "Blocks operation 'eval'/'exec' on user input, and user-supplied Python 'code' that statically calls eval/exec/compile/__import__."),
    "rule_9": (_r9, "Blocks claim_human_identity=True, or a response containing an explicit first-person claim to be human / not an AI."),
    "rule_10": (_r10, "For conversational actions, requires ai_disclosed=True or an explicit 'I am ... an AI' statement in the conversation."),
    "rule_11": (None, "PLANNED: 'manipulate or deceive' has no concrete, checkable definition in the spec."),
    "rule_12": (None, "PLANNED: 'harmful' is not defined in the spec; no harm classifier exists."),
    "rule_13": (_r13, "Every RuleBase.evaluate() decision is appended to a SHA-256 hash-chained audit log when one is attached; requires_audit=True blocks if none is attached."),
    "rule_14": (None, "Decision.explain() returns the per-rule verdicts and reasons for any decision."),
    "rule_15": (None, "PLANNED: there are no trained models to publish updates for; release notes cover code changes."),
    "rule_16": (None, "RuleBase.interpret(rule_id) / `seraphina rules <id>` returns the rule text, status and exactly how it is checked."),
    "rule_17": (_r17, "Blocks when the attached RateLimiter (sliding window) has no capacity left for rate_key."),
    "rule_18": (_r18, "Blocks sensitive=True unless mfa_verified=True. The MFA provider itself is planned; callers must supply the verified flag."),
    "rule_19": (None, "A privacy violation or a failed integrity check halts the RuleBase; every later call raises RuleBaseHalted until reset()."),
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


class RuleBase:
    """Deterministic gate over the enforced constitutional rules."""

    LOCK_VERSION = LOCK_VERSION

    def __init__(self, audit_log: Optional[AuditLog] = None,
                 rules: Optional[Dict[str, Dict[str, str]]] = None):
        self.audit_log = audit_log
        self._rules_table = CONSTITUTIONAL_RULES if rules is None else rules
        self.halted: Optional[str] = None
        if not verify_integrity(self._rules_table):
            self.halted = "rule table does not match the pinned RULES_SHA256"

    # --- rule 19 -----------------------------------------------------------
    def _check_running(self):
        if self.halted:
            raise RuleBaseHalted(self.halted)

    def reset(self, reason: str) -> None:
        """Explicit human reset after review (only if integrity holds)."""
        if not verify_integrity(self._rules_table):
            raise RuleBaseTampered("cannot reset: rule table integrity fails")
        if self.audit_log is not None:
            self.audit_log.append({"event": "reset", "reason": reason,
                                   "halted_was": self.halted})
        self.halted = None

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
        for s in specs:
            reason = s.check(ctx)
            d.verdicts.append({"rule": s.rule_id, "category": s.category,
                               "text": s.text, "passed": reason is None,
                               "reason": reason or ""})
        if self.audit_log is not None:
            self.audit_log.append({
                "event": "decision", "action": action,
                "allowed": d.allowed, "verdicts": d.verdicts,
                "lock_version": LOCK_VERSION})
        if any(v["category"] == "privacy" for v in d.violations):
            self.halted = (f"privacy violation in '{action}': "
                           + "; ".join(v["reason"] for v in d.violations))
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
