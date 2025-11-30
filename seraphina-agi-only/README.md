# Seraphina AGI Only

This folder contains only AGI-related components from the Seraphina project, with no mining or wallet code.

Quick start

From this folder:

```pwsh
node ./run-agi.js serve 8080
# Then POST JSON { "input": "Hello" } to http://localhost:8080/process
```

Train (optional):

```pwsh
node ./run-agi.js train
```

Optimize (safe mock cube):

```pwsh
node ./run-agi.js optimize
```

Files included:
- `run-agi.js`: CLI runner
- `advanced-language-engine.js`: Language processing
- `ai-learning-orchestrator.js`: Learning orchestration
- `agi-self-optimizer.js`: Self-optimization
- `ai-memory-log.js`: Memory logging
- `agent-response-schema.js`: Agent schemas
- `AGENTS.md`: Agent documentation
- `ai-learning-config.json`: Config
- `ai-learning-summary-ledger.jsonl`: Ledger
- `lib/`: Dependencies (roman-wheel.js, etc.)

License: follow repository licensing.
