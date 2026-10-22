# Roman Wheel Node shadow mode for Seraphina

`seraphina/rwn_shadow.py` adds one integration point, `ShadowHook`. It runs the frozen
[Roman Wheel Node](https://github.com/SynerGro-AI/roman-wheel-node) policy on every claim your agent produces, and it
logs each decision (`ACCEPT`, `NOT_SURE` or `BLOCK`) without changing what the agent returns.

- **Shadow only.** The wrapped function returns the same object it always did. Its exceptions are raised as before.
  An error inside the hook is caught and logged and never reaches the agent.
- **No paid calls.** The hook can't enable the xAI judges, and it refuses `profile="panel"`, `judges=` and `enforce=`.
- **No required dependencies.** If `roman_wheel_node` isn't installed, every claim is still written to a hash-chained
  log with the outcome `NOT_SURE`. That fails closed: claims are logged but never trusted.

## The integration point (3 lines)

```python
from seraphina.rwn_shadow import ShadowHook
hook = ShadowHook()                          # judges OFF, free local sources, shadow mode
agent_respond = hook.wrap(agent_respond)     # same return value; claims get logged
```

If you have evidence for a claim, log it directly with `hook.observe("claim", evidence=["exact sentence", ...])`.
The exact-copy gate only passes evidence that is byte-identical to a sentence in your trusted corpus
(`SERAPHINA_RWN_CORPUS`). Without a corpus, a claim can't be verified, so it is logged as `BLOCK`. That's still useful
fresh data.

## Install on Windows (PowerShell)

```powershell
cd C:\path\to\Seraphina          # your Seraphina checkout (public or private)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
# the engine, from the roman-wheel-node phase4-shadow branch, with local NLI extras
pip install "roman-wheel-node[local-nli,local-nli2] @ git+https://github.com/SynerGro-AI/roman-wheel-node.git@phase4-shadow"
# GPU (NVIDIA): CUDA torch and onnxruntime-gpu
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip uninstall -y onnxruntime; pip install onnxruntime-gpu
```

## Configure and run

```powershell
$env:RWN_NLI2 = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"   # downloaded on first use (~0.7 GB)
$env:RWN_DEVICE = "cuda"                                           # or "cpu"
$env:SERAPHINA_RWN_CORPUS = "C:\data\trusted_corpus.jsonl"         # optional: {"doc_id": "...", "sentences": [...]}
# logs default to $env:LOCALAPPDATA\Seraphina\rwn_shadow ; override with $env:SERAPHINA_RWN_LOG_DIR
python -m seraphina.rwn_shadow "Vitamin D supplementation reduces respiratory infections."
```

Logs (they hold claim text, so keep them out of git):

| File | What |
|---|---|
| `audit.jsonl` | Hash-chained ClaimTrace audit. Every decision can be recomputed from it. |
| `fresh_claims.jsonl` | One row per claim: the claim, its evidence, raw source scores and the outcome. This is the input for labelling. |
| `errors.jsonl`, `hook_errors.jsonl` | Errors the hook caught. They never reach the agent. |

Labelling and certification use the roman-wheel-node tools:
`python -m roman_wheel_node.fresh prereg|label|certify --log-dir "$env:LOCALAPPDATA\Seraphina\rwn_shadow"`.
See `PHASE4_DESKTOP.md` in roman-wheel-node.

## What is and isn't certified

The free local profile isn't certified at any error level. The only certificate behind any profile is the Phase 3e one:
on SciFact-like claims, with the paid 6-judge panel, false accepts are at most 5% of accepts. Nothing is certified at
1% or 2%. Shadow mode exists to collect fresh claims, so that a later certificate can be earned on data the node was
never tuned on.
