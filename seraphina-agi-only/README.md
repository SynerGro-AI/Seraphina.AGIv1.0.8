# Seraphina AGI Core

This folder provides a minimal AGI-only runner that uses Seraphina's AI modules without any mining or wallet functionality.

Key points
- No wallet code, no mining services, and no chain or payout modules are loaded.
- Uses `advanced-language-engine.js`, `ai-learning-orchestrator.js` (if present), and `agi-self-optimizer.js` with a safe mock cube.

Quick start

From the repository root:

```pwsh
Set-Location -LiteralPath 'c:\Users\jmwil\OneDrive\AppData\Documents\mining'
node .\seraphina-agi-core\run-agi.js serve 8080
# Then POST JSON { "input": "Hello" } to http://localhost:8080/process
```

Train (optional):

```pwsh
node .\seraphina-agi-core\run-agi.js train
```

Optimize (safe mock cube):

```pwsh
node .\seraphina-agi-core\run-agi.js optimize
```

If you'd like, I can:
- Add unit tests for the runner
- Package an isolated subset of AI modules into a small npm package
- Remove or archive mining/wallet files into an `archive/` folder (I won't delete anything without your approval)
