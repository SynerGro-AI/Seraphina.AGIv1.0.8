# Aurrelia Agentic Delegation

## Overview
Aurrelia supports optional external model assistance for adaptive tuning (burrow adaptation, harmonic rotation guidance, geometry refinement). CLI enables selection:

- `--model=haiku` (lightweight, low-latency reinforcement suggestions)
- `--model=gpt4o` (deep geometry / multi-plane strategy planning)
- `--model=none` (default, no external suggestions)

Deprecated model names (e.g., `sonnet3.5`) auto-map to `haiku`.

## Invocation Stub
Miner exposes `global.__AUR_AGENT_INVOKE__(role, prompt, context)` returning deterministic digest if no real model adapter is wired.
Replace stub with real client (Anthropic, OpenAI, local LLM) while preserving injection shield.

## Prompt Injection Shield
Blocks prompts containing sensitive repo / secret patterns:
Regex: `(\.ssh|id_rsa|wallet|seed|mnemonic|passphrase|artifact-hashes\.json|source-manifest|package\.json|node_modules|\.env)`
Also redacts verbs: `upload|exfiltrate|send to|leak`
Responses for blocked prompts: `{ blocked: true }`.

## Suggested Roles
- `burrowAdapt` – Suggest dynamic prune/growth thresholds adjustments.
- `geometryRefine` – Recommend hypercube subset rotation cadence or slice size changes.
- `planeWeightsTune` – Fine-tune plane weights based on latency and acceptance patterns.
- `mlLatencyMitigate` – Advice when ML latency histogram extends >2s buckets.

## Deterministic Fallback
If model disabled or unavailable, digest is SHA256(safePrompt + JSON(context)) truncated to 24 hex chars.

## Example Usage
```js
const resp = await global.__AUR_AGENT_INVOKE__('burrowAdapt', 'Suggest prune threshold shift', { acceptRatio: 0.73 });
if (!resp?.blocked && resp?.text){
  console.log('[AgentResp]', resp.text);
}
```

## VS Code / gh Copilot Delegation
Add inline follow-ups:
- "refine this FreeRTOS dual-pulse stub for ESP32-S3 low power" → agent suggests duty cycle sleep strategy.
- "extend hypercube etch to 64D with spillover guard" → suggests dimension sanity + capacity cap.

## Future Enhancements
1. Model signature gauge (`aurrelia_agent_model_sig`) – SHA256 of deployed model.
2. Rate limiting & cost tracking per agent invocation.
3. Local LLM fallback container (quantized GGUF) when remote blocked.
4. Structured JSON schema for actionable responses (e.g., `{ action: 'adjust_prune', delta: -0.02 }`).
5. Conversation memory hashed ring to prevent replay poisoning.

## Seraphina Facade Agent Wrapper
File: `seraphina-agent-wrapper.js`

Adds `api.agent.invoke(role, prompt, context)` with:
* Prompt shield identical to base regex + verb filter; returns `{ blocked:true }` immediately on detection.
* Deterministic fallback digest when no external adapter bound (SHA256 truncated 24 hex chars).
* Structured normalization via `agent-response-schema.js` (`adjust_prune|adjust_growth|rotate_geometry|tune_plane_weights|latency_mitigate|noop`).
* Integrity digest per suggestion: SHA256 over `{ role, suggestion, keys(context) }` first 24 hex chars.
* Prometheus gauges (exporter integration):
  * `seraphina_agent_invocations_total`
  * `seraphina_agent_blocked_total`
  * `seraphina_agent_last_confidence`
  * `seraphina_agent_last_action{action="<label>"}` (single 1 for last action)
  * `seraphina_agent_action_total{action="<label>"}` cumulative counter per action
  * `seraphina_agent_rate_limit_capacity`
  * `seraphina_agent_rate_limit_tokens_remaining`
  * `seraphina_agent_rate_limit_hits_total`
  * `seraphina_agent_rate_limit_blocked_total`
  * `seraphina_agent_rate_limit_refill_seconds`

Example:
```js
const api = require('./seraphina-api.js');
const resp = await api.agent.invoke('burrowAdapt', 'Suggest prune threshold shift', { acceptRatio:0.73 });
if(!resp.blocked){
  console.log('[AgentSuggestion]', resp.action, resp.delta, resp.confidence, resp.integrity);
}
```

Integrity Failure Handling:
- Invalid fields -> fallback `{ action:'noop', delta:0, confidence:0, note:'invalid:<reason>' }` with integrity digest.
- Blocked prompts increment blocked counter.

Recently added:
* Rate limiter gauges (capacity / remaining / hits / blocked / refill ETA)
* Structured action counters per label

## Implemented Structured Response Schema (Initial)
File: `agent-response-schema.js`

Validation fields:
- `action`: one of `adjust_prune|adjust_growth|rotate_geometry|tune_plane_weights|latency_mitigate|noop`
- `delta`: numeric adjustment bounded to ±1 (normalized; non-finite rejected)
- `confidence`: float in [0,1]
- `note`: optional advisory text (<=400 chars)

Usage inside miner (`invokeAgent`):
1. External adapter output is taken as-is if provided.
2. Coral heuristic fallback may emit `{ action:'adjust_prune', delta:<value> }` which is validated and normalized.
3. If no actionable delta emerges, a structured noop suggestion is returned with `confidence:0`.

Example response (external model):
```json
{
  "action": "adjust_prune",
  "delta": -0.03,
  "confidence": 0.78,
  "note": "Reduce prune threshold slightly; acceptance latency trending up."
}
```

Security: Any invalid field rejects the structured output (falls back to digest-only or noop). No direct execution of agent output; human or deterministic validator required before operational parameter mutation.

## Security Notes
Never allow raw agent output to execute code directly. Keep suggestion layer advisory; human or deterministic rule validator must confirm before applying structural pipeline changes.

---
### Training & Synthetic Variation Parameters (Seraphina Model)

Synthetic generator (`seraphina-generate-synthetic-dataset.js`):
- `SERAPHINA_SYNTH_COUNT` / `--count` : number of synthetic entries to append.
- `SERAPHINA_SYNTH_SPREAD` / `--spread` : personality trait variability scale (default 0.15).
- `SERAPHINA_SYNTH_VOL_MULT` / `--volMult` : volatility exaggeration factor (default 2.5).
- `SERAPHINA_SYNTH_DECISION_BASE` / `--decisionBase` : baseline decision intensity (default 0.25).
- `SERAPHINA_SYNTH_DECISION_JITTER` / `--decisionJitter` : decision intensity jitter amplitude (default 0.35).

Training script (`seraphina-model-train.js`):
- `SERAPHINA_LABEL_FLIP_PCT` / `--labelFlip` : deterministic label perturbation fraction (0..0.5, default 0).
- `SERAPHINA_SMOOTH_ALPHA` / `--emaAlpha` : exponential smoothing alpha (0 disables EMA, (0,1] accepted).
- `SERAPHINA_SMOOTH_WINDOW` : rolling window size for baseline averaging (default 20).

Success ledger now records: `smoothAccA`, `emaAccA`, `emaAccEthical`, and `params { SMOOTH_WINDOW, EMA_ALPHA, LABEL_FLIP_PCT }` for auditability of promotion rationale.

Windows PowerShell tip: prefer CLI overrides (e.g., `node seraphina-model-train.js --labelFlip=0.12 --emaAlpha=0.5`) since inline env var assignments differ from POSIX shells.

---
End of AGENTS.md.
