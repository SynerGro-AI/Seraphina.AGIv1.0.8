"""The constitutional gate as Seraphina's commands use it.

Every action the CLI takes on the user's behalf that the enforced rules
cover goes through :func:`check` first:

* ``plan-grok``: the outgoing request (rules 1, 2, 17) and the reply before
  it is shown (rules 9, 10, plus a Roman Wheel Triad pass on the reply).
* running code: ``glyph exec`` and the wizard's ``run`` intent (rules 7, 8).

Decisions go to the hash-chained audit log at ``$SERAPHINA_HOME/audit.jsonl``
(rule 13). A blocked action halts the gate (rule 19) and the halt is kept in
``$SERAPHINA_HOME/halted.json``, so later commands stay blocked until a person
runs ``seraphina --reset-rules "<reason>"``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from .constitution import (
    AuditLog, Decision, FileRateLimiter, RuleBase, RuleBaseHalted,
)


def home() -> Path:
    return Path(os.environ.get("SERAPHINA_HOME", Path.home() / ".seraphina"))


def audit_file() -> Path:
    return home() / "audit.jsonl"


def halt_file() -> Path:
    return home() / "halted.json"


def rule_base() -> RuleBase:
    return RuleBase(audit_log=AuditLog(audit_file()), halt_file=halt_file())


_RATE_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")


def grok_rate_limiter() -> FileRateLimiter:
    """Rule 17 cap for plan-grok: SERAPHINA_GROK_RATE="calls/seconds"
    (default 30 calls per 3600 s), shared by every CLI process."""
    raw = os.environ.get("SERAPHINA_GROK_RATE", "30/3600")
    m = _RATE_RE.match(raw)
    if not m or int(m.group(1)) < 1 or int(m.group(2)) < 1:
        raise ValueError(f"SERAPHINA_GROK_RATE must look like 30/3600, got {raw!r}")
    return FileRateLimiter(home() / "rate" / "plan_grok.json",
                           int(m.group(1)), int(m.group(2)))


def halt_message(reason: str) -> str:
    """What a halted Seraphina tells the person, with the way out."""
    return (f"Seraphina is shut down by rule 19 until a person reviews it: {reason}\n"
            f"  review {audit_file()}, then run: seraphina --reset-rules \"<reason>\"\n"
            f"  (still available: --version, help, rules, --verify-rules, --export-audit)")


class Blocked(Exception):
    """The gate refused the action. ``str()`` is the full rule-14 trace."""

    def __init__(self, text: str, decision: Optional[Decision] = None):
        super().__init__(text)
        self.decision = decision


def check(action: str, context: dict, rb: Optional[RuleBase] = None) -> Decision:
    """Evaluate *action* against every enforced rule. Returns the Decision
    if allowed; raises :class:`Blocked` (with the explanation) otherwise,
    including when the gate is already halted."""
    rb = rb or rule_base()
    try:
        d = rb.evaluate(action, context)
    except RuleBaseHalted as e:
        raise Blocked(halt_message(str(e))) from e
    if not d.allowed:
        raise Blocked(d.explain(), d)
    return d
