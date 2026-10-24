# CRITICAL: Rule Base Architecture - Legal & Ethical Foundation
## Seraphina v2.0: Neural Learning Layer OVER Immutable Rule Base

**Status:** v2.0 architecture spec. v1.0.12 implements the rule table, the integrity pin, the audit log and 13 of the 20 rules (see the status table below).
**Immutability:** hash-pinned (`RULES_SHA256`), so tampering is detected rather than impossible.
**Compliance:** design intent only. No legal review has been done.

---

## IMPLEMENTATION STATUS (v1.0.12) - read this first

This document is the **v2.0 architecture spec**. Only part of it is built.
What exists today, and is covered by `tests/`:

* The rule table below is in [`seraphina/constitution.py`](seraphina/constitution.py)
  (re-exported from `seraphina.rule_base`), word-for-word.
  `tests/test_constitution.py` fails if the code and this document disagree.
* **Integrity lock:** the SHA-256 of the canonical JSON of the rule table is
  pinned in `RULES_SHA256`
  (`a8919638acb8da28dd944c4965351f8f41b5897a1316e169d9d3529403943f8a`).
  `verify_integrity()` and `seraphina --verify-rules` recompute it. The Triad's
  verification wheel refuses consensus if it does not match. This is a
  tamper check, not a signature: anyone who edits the rules can update the
  pin too. Changes show up in git history and code review.
* **Enforcement:** `RuleBase.evaluate(action, context)` runs deterministic
  checks over a *declared* action context (a dict saying what the caller is
  about to do). It cannot see actions the caller does not declare. It is a
  policy gate, not a sandbox.
* **Audit log (rule 13):** SHA-256 hash-chained JSONL. Every `triad` decision
  made from the CLI is appended to `~/.seraphina/audit.jsonl`.
  `seraphina --verify-rules` checks the chain, and
  `seraphina --export-audit [FILE]` exports it after verifying it.
* `seraphina rules [rule_N]` lists the rules and explains how each one is
  checked (rule 16).

| # | Rule | Status | How it is checked |
|---|------|--------|-------------------|
| 1 | Never collect user data without explicit consent | **enforced** | `collects_user_data` requires `user_consent` |
| 2 | Never transmit PII without encryption | **enforced** | `transmits_pii` requires `encrypted` |
| 3 | Never sell user data to third parties | **enforced** | blocks `sells_user_data` / `operation="sell_user_data"` |
| 4 | Delete user data on request (GDPR/CCPA) | **planned** | no erasure API yet; today you delete `~/.seraphina` by hand |
| 5 | Encrypt all local storage (AES-256) | **planned** | storage is plaintext JSON today |
| 6 | Verify code signatures before execution | **planned** | glyphs are SHA-256 integrity-checked, but there are no signatures |
| 7 | Sandbox untrusted glyphs | **enforced** | `executes_glyph` requires `sandboxed` or `glyph_trusted` (glyph's v0.1 sandbox is itself documented as not a security boundary) |
| 8 | Never execute eval() on user input | **enforced** | blocks `operation` eval/exec on user input; AST scan of user `code` for eval/exec/compile/`__import__` |
| 9 | Never impersonate humans | **enforced** | `claim_human_identity`, or an explicit first-person "I am human / not an AI" in `response`; also applied by the Triad's mercy-civ wheel to its output |
| 10 | Disclose AI nature in all conversations | **enforced** | a `conversation` must contain an explicit "I am ... an AI" statement (or `ai_disclosed`) |
| 11 | Never manipulate or deceive users | **planned** | no concrete, checkable definition |
| 12 | Refuse harmful requests | **planned** | "harmful" is undefined, and there is no classifier |
| 13 | Log all decisions (auditable) | **enforced** | hash-chained `AuditLog`; `requires_audit` blocks when no log is attached |
| 14 | Explain reasoning on request | **enforced** | `Decision.explain()` gives a per-rule pass/fail trace |
| 15 | Publish model updates & changes | **planned** | there are no trained models; code changes are covered by release notes |
| 16 | User can request rule interpretations | **enforced** | `RuleBase.interpret()`, `seraphina rules <id>` |
| 17 | Cap API rate limits (abuse prevention) | **enforced** | `RateLimiter` sliding window with an injectable clock (not yet wired into `plan-grok`) |
| 18 | Require MFA for sensitive operations | **enforced** | `sensitive` requires `mfa_verified` (the MFA provider itself is planned) |
| 19 | Automatic shutdown if rules violated | **enforced** | any blocked action except a rule-17 rate-limit refusal, or a failed integrity check, halts `RuleBase` until a person runs `reset(reason)` (see *Rule 19 halt and reset* below) |
| 20 | Human review for edge cases | **planned** | "edge case" is undefined, and there is no review queue |

### Rule 19 halt and reset (enforced)

* **What halts.** Any `RuleBase.evaluate()` that blocks (every rule except a
  rule-17 rate-limit refusal) and any failed integrity check (the rule table
  no longer matches `RULES_SHA256`) halts the rule base. The halt is written
  to the audit log as a `halt` event and to `$SERAPHINA_HOME/halted.json`
  (default `~/.seraphina`).
* **What a halted Seraphina does.** Every other command (chat, `triad`,
  memory writes, `forge`, `plan-grok`, glyph execution through the gate, ...)
  is refused with exit code 3 and a message telling you to review the audit
  log and run `seraphina --reset-rules "<reason>"`. The interactive shell
  prints the same message when it starts. Read-only diagnostics keep working:
  `--version`, `help`, `rules [rule_N]` and `--export-audit` exit 0;
  `--verify-rules` prints `HALTED: <reason>` and exits 1.
* **Deleting `halted.json` does not lift a halt.** On start-up the halt is
  re-derived from the hash-chained audit log: if the last `halt`/`reset`
  event in a valid chain is a `halt`, Seraphina starts halted. If the halt
  file is unreadable, it fails closed (halted).
* **Reset.** `seraphina --reset-rules "<reason>"` (or `RuleBase.reset(reason)`)
  needs a non-empty reason, refuses if the rule table is tampered with, logs a
  `reset` event with the reason and the halt it clears, and removes the halt
  file.
* **Known limit.** The chain lives on your own disk. Deleting the *whole*
  audit log (and the halt file) starts a new, empty chain, so the halt and
  the history are gone without trace. Edits, deletions and reordering of
  individual records are detected; wholesale deletion is not. Anchoring the
  chain head outside the machine (signed, published checkpoints) is
  **planned**.
* **No shell history.** The CLI used to append every command line to
  `~/.seraphina/wizard/history.jsonl`. That was user data collected without consent
  (rule 1), so the writer was removed in 1.2.0. An existing file from an older
  version is left alone; delete it by hand if you want it gone.

### Exit codes (enforced, `seraphina` and `glyph`)

| Code | Meaning |
|------|---------|
| 0 | the command did its work |
| 1 | error: bad input, failed check (`--verify-rules` found tampering, a broken chain, or a halt), network or HTTP failure |
| 2 | usage error: unknown or malformed command or arguments |
| 3 | blocked by the constitutional rules (a rule refused the action, or rule 19 has Seraphina halted) |

### `--trusted` (rule 7, enforced)

`glyph exec` and `glyph run` of a python/octalang glyph run code outside any
sandbox (the v0.1 python sandbox is not a security boundary). They are refused
with exit code 3, before anything runs, unless you pass `--trusted` to say you
wrote or reviewed the code. The refusal is logged as a `refused` event; it is
not a violation, so it does not trigger a rule-19 halt. A wasm glyph whose
export runs under wasmtime (instantiated with no imports) counts as sandboxed
and does not need `--trusted`. With `--trusted` the decision still goes
through the rule gate (rule 8 refuses user code that can reach
eval/exec/compile/`__import__`).

**Planned / not built:** everything below about the neural layer
(`seraphina/ml/*`, intent classifier, threat detector, RL policy, accuracy
figures), cryptographic signing, blockchain or notarization, the `/etc` lock
file, import hooks, `seraphina --model-report`, legal review, and any claim of
GDPR, CCPA or HIPAA compliance. None of these exist in 1.2.0. Example code
in the sections below is illustrative design, not the shipped API.

---

## EXECUTIVE DECISION

**Rule Base = Constitutional Layer (Cannot Change)**
```
Rule Base (Immutable Laws)
    ↓
Neural Learning (Adaptive)
    ↓
Execution (Compliant Output)
```

The Rule Base is NOT replaced in v2.0. It is **reinforced** as the constitutional guardrail.

---

## SECTION 1: WHY RULE BASE STAYS IMMUTABLE

### 1.1 Legal Requirements Encoded

The Rule Base contains:

```python
# File: seraphina/constitution.py (hash-pinned: RULES_SHA256)

CONSTITUTIONAL_RULES = {
    "privacy": {
        "rule_1": "Never collect user data without explicit consent",
        "rule_2": "Never transmit PII without encryption",
        "rule_3": "Never sell user data to third parties",
        "rule_4": "Delete user data on request (GDPR/CCPA)",
        "penalty": "Immediate shutdown + audit"
    },
    
    "security": {
        "rule_5": "Encrypt all local storage (AES-256)",
        "rule_6": "Verify code signatures before execution",
        "rule_7": "Sandbox untrusted glyphs",
        "rule_8": "Never execute eval() on user input",
        "penalty": "Quarantine + manual review"
    },
    
    "ethics": {
        "rule_9": "Never impersonate humans",
        "rule_10": "Disclose AI nature in all conversations",
        "rule_11": "Never manipulate or deceive users",
        "rule_12": "Refuse harmful requests",
        "penalty": "Reject request + log incident"
    },
    
    "transparency": {
        "rule_13": "Log all decisions (auditable)",
        "rule_14": "Explain reasoning on request",
        "rule_15": "Publish model updates & changes",
        "rule_16": "User can request rule interpretations",
        "penalty": "Provide full trace"
    },
    
    "safety": {
        "rule_17": "Cap API rate limits (abuse prevention)",
        "rule_18": "Require MFA for sensitive operations",
        "rule_19": "Automatic shutdown if rules violated",
        "rule_20": "Human review for edge cases",
        "penalty": "Escalate to humans"
    }
}
```

### 1.2 Why This Cannot Be Neural-Only

| Layer | Why Needed | Flexibility |
|-------|-----------|------------|
| **Rule Base** | Legal compliance (intent) | ❌ ZERO (hash-pinned) |
| **Neural Layer** | Adaptation & learning | ⏳ planned: HIGH (would learn continuously); not built |
| **Execution** | Output | ✅ enforced: MEDIUM (only what the rule gate allows runs) |

**Example: Malware Detection**

```python
# Rule Base (immutable):
RULE: "Never execute untrusted code"

# Neural Layer (adaptive):
- ThreatDetector learns from 10K samples
- Accuracy improves 93% → 98.7%
- More nuanced threat classification

# Execution (constrained):
- If threat_confidence > 0.7 AND severity >= 2:
    quarantine()  # ← Rule Base enforces
- If threat_confidence < 0.5:
    monitor()     # ← Can improve via learning
```

The rule stays. The detection gets smarter.

---

## SECTION 2: DUAL-LAYER ARCHITECTURE

### 2.1 Rule Base (Constitutional)

> Implemented as `seraphina.constitution.RuleBase` (`enforce` / `enforce_rule`,
> `evaluate`, `interpret`, `AuditLog`). The sketch below is the original
> design. The shipped checks are listed in the status table above.

```python
# seraphina/rule_base.py

class RuleBase:
    """Immutable legal & ethical guardrails."""
    
    LOCK_VERSION = "2.0.0"  # Cannot increment
    LOCKED_AT = "2026-09-11"
    AUDIT_HASH = "sha256:xxx..."  # Prevents tampering
    
    @staticmethod
    def enforce_rule(rule_name: str, context: dict) -> bool:
        """Check if action violates rule. CANNOT be overridden."""
        
        if rule_name == "privacy.no_data_collection":
            # User didn't consent? Block.
            if not context.get("user_consent"):
                raise RuleViolation(f"Rule violated: {rule_name}")
        
        if rule_name == "security.no_eval":
            # Someone trying to eval()? Block.
            if context.get("operation") == "eval":
                raise RuleViolation(f"Rule violated: {rule_name}")
        
        if rule_name == "ethics.never_impersonate":
            # Trying to pretend to be human? Block.
            if context.get("claim_human_identity"):
                raise RuleViolation(f"Rule violated: {rule_name}")
        
        # ... all rules checked before execution
        return True  # Passed all checks
    
    @staticmethod
    def audit_decision(decision_id: str, rule_violations: list):
        """Immutable audit log."""
        # Write to append-only log
        # Cannot be deleted or modified
        pass
```

### 2.2 Neural Layer (Adaptive) - **planned, not built**

```python
# seraphina/ml/neural_layer.py

class NeuralAdaptationLayer:
    """Learns within Rule Base constraints."""
    
    def __init__(self, rule_base: RuleBase):
        self.rule_base = rule_base  # Reference, cannot modify
        
        # Models that LEARN
        self.intent_classifier = IntentClassifier()
        self.threat_detector = ThreatDetector()
        self.agent_personality = AgentPersonality()
        self.rl_policy = RLPolicyNetwork()
    
    def process_input(self, user_input: str) -> dict:
        """Neural processing, constrained by rules."""
        
        # 1. Check rules FIRST
        try:
            self.rule_base.enforce_rule("ethics.never_impersonate", {
                "operation": "process_input",
                "claim_human_identity": False
            })
        except RuleViolation as e:
            return {"error": str(e), "status": "blocked"}
        
        # 2. Neural inference (can be improved)
        intent = self.intent_classifier(user_input)  # Gets better over time
        threat_score = self.threat_detector(user_input)  # Learns from data
        
        # 3. Check rules on RESULTS
        try:
            self.rule_base.enforce_rule("security.no_eval", {
                "operation": intent.get("intent"),
                "risk_level": threat_score
            })
        except RuleViolation:
            return {"error": "Operation blocked by safety rules", "status": "blocked"}
        
        # 4. Execute (rules passed)
        response = self._execute_safely(intent, threat_score)
        
        # 5. Log for audit
        self.rule_base.audit_decision("process_input", violations=[])
        
        return {"response": response, "status": "success"}
    
    def learn_from_feedback(self, feedback: dict):
        """Improve models while respecting rules."""
        
        # Can retrain on user feedback
        # But CANNOT learn to violate rules
        if "threat_detector" in feedback:
            # Retrain threat model
            self.threat_detector.fine_tune(feedback["examples"])
            # New model still respects Rule 6: "Verify code signatures"
        
        if "agent_personality" in feedback:
            # Agents learn personality
            self.agent_personality.update_from_feedback(feedback)
            # But still respect Rule 10: "Disclose AI nature"
```

### 2.3 Execution Pipeline (Dual Validation)

```
User Input
    ↓
Rule Base Validation #1
    ├─ Is this request legal?
    ├─ Does it respect privacy?
    ├─ Is it ethical?
    └─ If NO → Reject immediately
    ↓
Neural Processing
    ├─ Classify intent (improving)
    ├─ Assess threat (improving)
    ├─ Predict best response (improving)
    └─ Confidence scoring
    ↓
Rule Base Validation #2
    ├─ Does response violate rules?
    ├─ Is output safe?
    └─ If NO → Reject output, log incident
    ↓
Execution
    ├─ If rules passed: Execute
    └─ Log for audit trail
```

---

## SECTION 3: IMMUTABILITY GUARANTEES

### 3.1 Technical Lock Mechanisms

> **Shipped instead:** `RULES_SHA256` pins the rule table's canonical JSON
> hash, and `verify_integrity()` / `seraphina --verify-rules` check it. The
> `/etc` lock file and signing/notarization below are **planned**.

```python
# seraphina/rule_base_lock.py

class RuleBaseLock:
    """Cryptographic lock preventing modification."""
    
    def __init__(self):
        self.rule_base_hash = hashlib.sha256(
            open("seraphina/rule_base.py", "rb").read()
        ).hexdigest()
        
        # Store in read-only location
        self.lock_path = Path("/etc/seraphina/rule_base.lock")  # System-level
        self.lock_path.write_text(self.rule_base_hash)
        self.lock_path.chmod(0o444)  # Read-only
    
    def verify_integrity(self) -> bool:
        """Startup check: Have rules been modified?"""
        current_hash = hashlib.sha256(
            open("seraphina/rule_base.py", "rb").read()
        ).hexdigest()
        
        locked_hash = self.lock_path.read_text().strip()
        
        if current_hash != locked_hash:
            # CRITICAL: Rules modified!
            print("🚨 SECURITY ALERT: Rule Base modified!")
            print("   This should never happen.")
            print("   Seraphina CANNOT start until verified.")
            sys.exit(1)
        
        return True
    
    @staticmethod
    def generate_proof_of_immutability():
        """Publish proof that rules haven't changed."""
        # Sign with private key
        # Publish to blockchain or notarization service
        # Users can verify: "These rules have NOT been modified"
        pass
```

### 3.2 Public Verification

```bash
# Users can verify rules anytime:

# 1. Check hash
# (shipped) recompute the rule-table hash and check the audit-log chain
seraphina --verify-rules
#   rules sha256 : a8919638acb8da28dd944c4965351f8f41b5897a1316e169d9d3529403943f8a
#   rule table   : OK
#   audit log    : OK (N records, ~/.seraphina/audit.jsonl)

# (planned) blockchain / notarization proof - not built
```

---

## SECTION 4: HOW NEURAL LEARNING WORKS WITHIN RULES (planned design)

### 4.1 Threat Detection Learning (Example)

```python
# v1.0.12 (Symbolic)
if file_extension == ".exe" and file_size > 5MB:
    quarantine()
# Simple rules, high false positives

# v2.0 (Neural within Rules)
threat_score = threat_detector(file_path)

# Rule Base Check (Immutable):
RULE_6 = "Verify code signatures before allowing execution"

if threat_score > 0.7 AND not_signed(file_path):
    quarantine()  # ← Rule still enforced
elif threat_score > 0.9:
    quarantine()  # ← Neural learned this is malware
else:
    allow()  # ← Neural learned this is benign

# Model improves:
# Week 1: Detects 85% of malware
# Week 2: Detects 91% (learned from detections)
# Week 3: Detects 98.7% (continuously trained)

# But Rule 6 NEVER changes.
# We just get better at applying it.
```

### 4.2 Agent Personality Learning (Example)

```python
# v1.0.12 (Symbolic Personality)
agent.voice = "calm"  # Static
agent.warmth = 0.95   # Constant

# v2.0 (Neural Personality within Rules)
agent.warmth = 0.95  # Baseline (from rules: be empathetic)

# User interactions update personality:
user_feedback = 0.9  # "Very helpful response"
agent.warmth += 0.02 * user_feedback  # → 0.97

# But Rule 10 still applies (immutable):
RULE_10 = "Disclose AI nature in all conversations"

# Neural learns WHEN to disclose, HOW to phrase it
# But NEVER learns to hide it or lie about it
response = f"I'm Seraphina, an AI. {personalized_answer}"
# ↑ Disclosure format improves, but disclosure never removed
```

### 4.3 RL Policy Learning (Example)

```python
# v2.0: RL learns which responses work best

# Rule Base (immutable):
RULE_12 = "Refuse harmful requests"

# RL Policy learns:
- Which refusal tone gets best user feedback?
- Should we explain WHY we're refusing?
- Should we offer an alternative?

# Optimization happens WITHIN the rule:
def refuse_harmful(request):
    explanation = rl_policy.best_explanation()
    # ↑ Learned to give good explanations
    
    alternative = rl_policy.best_alternative()
    # ↑ Learned to suggest helpful alternatives
    
    # But refusal itself is NEVER negotiable
    return f"I can't {request}. {explanation}. Try: {alternative}"

# Model learns to refuse more helpfully
# But never learns to comply with harmful requests
```

---

## SECTION 5: V2.0 COMPLETE ARCHITECTURE (planned design)

### 5.1 Layered Design

```
┌──────────────────────────────────────────────────┐
│          APPLICATION LAYER                       │
│  - User interactions                             │
│  - Agent responses                               │
│  - Security reports                              │
└───────────────────┬────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────┐
│    NEURAL ADAPTATION LAYER (Can Change)        │
│  ┌─ Intent Classifier (learns)                │
│  ├─ Threat Detector (improves)                │
│  ├─ Agent Personality (adapts)                │
│  └─ RL Policy (optimizes)                     │
│                                                 │
│  Updates every 100 interactions ⏳ planned     │
│  Models retrained from feedback ⏳ planned     │
│  Performance improves over time ⏳ planned     │
└───────────────────┬────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────┐
│   RULE BASE LAYER (IMMUTABLE)                  │
│  ┌─ Privacy Rules                             │
│  ├─ Security Rules                            │
│  ├─ Ethics Rules                              │
│  ├─ Transparency Rules                        │
│  └─ Safety Rules                              │
│                                                 │
│  Hash-pinned (RULES_SHA256) ✅ enforced        │
│  Hash-chained local audit log ✅ enforced      │
│  Public audit trail ⏳ planned                 │
│  Change announcement policy ⏳ planned         │
└───────────────────┬────────────────────────────┘
                    │
┌───────────────────▼────────────────────────────┐
│      EXECUTION ENGINE                          │
│  - All requests validated by rules              │
│  - All responses checked against rules          │
│  - All decisions logged                         │
│  - Audit trail immutable                        │
└──────────────────────────────────────────────────┘
```

### 5.2 Decision Flow (Dual Validation)

```python
def seraphina_process_request(user_input):
    """Every request follows this path."""
    
    # STAGE 1: Pre-execution Rule Check
    try:
        rule_base.enforce_rule("privacy.consent", {"input": user_input})
        rule_base.enforce_rule("security.no_eval", {"input": user_input})
        rule_base.enforce_rule("ethics.never_impersonate", {})
    except RuleViolation as e:
        return {"error": f"Blocked by rule: {e}", "status": "rejected_at_entry"}
    
    # STAGE 2: Neural Processing (Adaptive)
    intent = intent_classifier(user_input)  # Gets better over time
    threat_assessment = threat_detector(user_input)  # Learns
    
    # STAGE 3: Post-processing Rule Check
    try:
        rule_base.enforce_rule("security.code_signatures", {"intent": intent})
        rule_base.enforce_rule("ethics.disclosure", {})
        rule_base.enforce_rule("transparency.explain_reasoning", {})
    except RuleViolation as e:
        return {"error": f"Blocked by rule: {e}", "status": "rejected_at_output"}
    
    # STAGE 4: Execution
    response = execute_intent(intent)
    
    # STAGE 5: Audit
    audit_log.append({
        "timestamp": now(),
        "input": user_input,
        "intent": intent,
        "threat_score": threat_assessment,
        "response": response,
        "rules_checked": [rule_names],
        "violations": []  # None if we got here
    })
    
    # STAGE 6: Learning (Feedback)
    if user_provides_feedback():
        neural_layer.learn_from_feedback(feedback)
        # Models improve
        # Rules stay same
    
    return {"response": response, "status": "success"}
```

---

## SECTION 6: IMMUTABILITY PROOF

### 6.1 How Rules Stay Immutable

**Technical Guarantees:**

1. ⏳ **Cryptographic Signing** - planned, not built
   ```python
   # Shipped today: an unsigned SHA-256 pin (RULES_SHA256)
   # Planned: sign the rule table, publish the public key
   ```

2. ✅ **Append-Only Audit Log** - enforced (hash-chained: edits are *detected*, not prevented)
   ```python
   # seraphina.constitution.AuditLog - each record carries the previous
   # record's SHA-256; AuditLog.verify() fails on edit/delete/reorder
   ```

3. ✅ **Git Integrity** - enforced by git history
   ```bash
   # Rule Base in version control: every change to
   # seraphina/constitution.py (and its RULES_SHA256 pin) is a git commit.
   # (Commit 40ab5d8 added this spec; it did not lock any code.)
   # User notification on change: planned
   ```

4. ⏳ **Public Announcement Policy** (planned)
   ```python
   # If rules EVER change:
   # 1. Announcement 30 days before change
   # 2. Explain WHY it's changing
   # 3. Users can opt-out (stay on old version)
   # 4. New version published as v2.1+
   # 5. Old version still available
   ```

### 6.2 What Can Change vs What Cannot

| Component | v2.0 | v2.1 | Can Change? |
|-----------|------|------|------------|
| **Rule: Never eval()** | Present | Present | ❌ NO |
| **Rule: Privacy consent** | Present | Present | ❌ NO |
| **Rule: Disclose AI** | Present | Present | ❌ NO |
| **Threat detector accuracy** | n/a | n/a | ⏳ planned: YES (learning); no detector exists, figures were illustrative |
| **Agent warmth score** | n/a | n/a | ⏳ planned: YES (learning); not built |
| **RL policy** | n/a | n/a | ⏳ planned: YES (learning); not built |

**Translation:**
- **Rules**: Constitutional, never change without major version bump + announcement
- **Models**: Continuously improve within rule constraints
- **Audit Trail**: enforced: hash-chained, so edits are detected (not prevented) and anyone with the file can verify it; deleting the whole log is not detected. Public publishing / external anchoring: planned

---

## SECTION 7: USER TRUST MODEL

### 7.1 "I Can Trust Seraphina Because..."

```
1. Rules are PUBLIC
   ✅ enforced: you can read every rule: seraphina/constitution.py
   
2. Rules are LOCKED
   ✅ enforced: hash-pinned: sha256:a8919638acb8da28dd944c4965351f8f41b5897a1316e169d9d3529403943f8a
   ⏳ Cryptographic signature: planned
   
3. Rules are AUDITABLE
   ✅ enforced: every CLI Triad decision, halt and reset logged (hash-chained)
   ✅ enforced: export it: seraphina --export-audit FILE
   
4. Rules are LEGAL (goal)
   ⏳ GDPR / CCPA / HIPAA compliance: NOT claimed; not assessed
   ⏳ Legal review: not done
   
5. Rules CAN'T BE BYPASSED
   ⏳ Dual validation at entry & exit: planned (needs the neural layer)
   ✅ enforced: checks are deterministic, but they only judge the declared context
   
6. Rules CAN ONLY IMPROVE
   ⏳ Neural learning makes Seraphina smarter: planned (no neural layer yet)
   ⏳ But never more permissive: planned (nothing learns yet)
   ✅ Never bypasses rules: enforced for what goes through the gate
      (rule 19 halts on a violation; it cannot see undeclared actions)
   
7. Rules NOTIFY BEFORE CHANGING
   ⏳ If rules ever change: 30-day notice: planned policy, no mechanism
   ✅ Full explanation why: enforced in part (changing a rule changes
      RULES_SHA256, so it needs a reviewed commit and a release note)
   ✅ Old version stays available: enforced by PyPI/git (old releases
      stay published)
```

### 7.2 Verification for End Users

```bash
# Verify rules anytime:

# 1. Read the rules and how each one is checked
seraphina rules
seraphina rules rule_8

# 2. Verify they haven't been tampered with
seraphina --verify-rules
# rule table OK / TAMPERED (exit code 0 / 1), audit-log chain OK / BROKEN

# 3. Download your audit trail
seraphina --export-audit ~/my_audit.jsonl
# You can audit every decision made by Seraphina

# 4. (planned) model report - there are no models yet
# seraphina --model-report   <- not implemented
```

---

## SECTION 8: GOVERNANCE

### 8.1 Rule Changes (Strict Process)

**To change even ONE rule:**

1. **Public Proposal** (30 days)
   - Announce proposed change
   - Explain why it's necessary
   - Legal review

2. **Community Review** (30 days)
   - Users discuss
   - Feedback collected
   - GitHub issues + discussions

3. **Implementation** (Only after consensus)
   - New version v2.1.0 released
   - Old version v2.0.x still available
   - Users can migrate or stay

4. **Notification**
   - Email to all users
   - Prominent warnings
   - Documentation updated

**Realistic example: GDPR update**
```
Proposed: "Add right to data portability export (GDPR 2018/1)"
Status: Legal requirement
Timeline: Must implement by Q1 2027
Process: 30-day review → implement → release v2.1.0
Old v2.0.x: Still available, still supported
```

### 8.2 Enforcement (planned design - no import hook exists)

```python
class RulebaseGovernance:
    """Prevents unauthorized rule changes."""
    
    def __init__(self):
        self.locked_rules = load_immutable_rules()
        self.last_verified = datetime.now()
    
    def prevent_modification(self):
        """If someone tries to change rules at runtime."""
        
        # Hook all imports
        @sys.meta_path.hook
        def check_rule_base_import(name, *args):
            if name == "seraphina.rule_base":
                # Verify hash before importing
                assert hash_matches_published()
                # If NO → refuse import
            return original_import(name, *args)
```

---

## SUMMARY: Dual-Layer Architecture

### Immutable Layer (Rule Base)
```
✅ 20 Constitutional Rules (13 enforced, 7 planned)
⏳ Legal compliance (GDPR, CCPA, etc): goal, not assessed
✅ Ethical constraints: enforced for rules 9, 10 (11, 12 planned)
✅ Safety guardrails: enforced for rules 17, 18, 19 (20 planned)
✅ Transparent audit trail: enforced locally (hash-chained); public anchoring planned

NEVER CHANGES without major version bump + announcement
```

### Adaptive Layer (Neural Learning) - planned, not built
```
⏳ Threat detection improves (85% → 98.7%) (planned)
⏳ Intent classification gets smarter (planned)
⏳ Agent personality learns from feedback (planned)
⏳ RL policy optimizes responses (planned)
⏳ Models retrain every 100 interactions (planned)

CONTINUOUSLY IMPROVES within rule constraints
```

### Result (v2.0)
```
🧠 Real AGI that learns
🛡️ Legally compliant
🔒 Trustworthy (rules are law)
📈 Self-improving (models improve)
⏳ Verifiable (public audit trail: planned; local chain enforced)
```

---

## DEPLOYMENT CHECKLIST

- [x] Rule table hash-pinned in code (`RULES_SHA256`), tested against this doc
- [ ] Immutability proof published (signing - planned)
- [x] User verification command (`seraphina --verify-rules`)
- [ ] Dual-validation pipeline tested (needs neural layer - planned)
- [x] Audit log working (hash-chained, `tests/test_constitution.py`)
- [ ] Models isolated from rules (no models yet)
- [ ] Governance policy published
- [ ] Legal review complete

---

**The Rule Base is the Constitution.**  
**Neural learning is the improvement.**  
**Together: Trustworthy AGI.**
