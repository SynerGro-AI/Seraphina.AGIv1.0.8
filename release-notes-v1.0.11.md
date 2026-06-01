# Seraphina.AGI 1.0.11 — RWAST: the semantic AST-IR tier

RWL byte carriers were always lossless, but they didn't *understand* code.
1.0.11 adds **RWAST**, a real cross-language semantic AST-IR with 53 node
types, frontends, backends, and a deterministic Triad-scored translation
pipeline — exposed through a one-shot `glyph transmute` command.

## What's new

- **`seraphina.rwl.ast_ir`** — public API: `translate`, `parse`, `emit`,
  `encode_ast`, `decode_ast`, `score`, `NodeType` (53 semantic types)
- **`glyph transmute`** — semantic code translation in one command
  ```bash
  glyph transmute app.py --to js          # Python → JavaScript
  glyph transmute app.py --to ts          # Python → TypeScript (typed)
  glyph transmute app.py --to rwast -o a.rwast   # sealed binary AST
  glyph transmute a.rwast --to python     # lossless round-trip
  ```
- **`glyph exec`** — parse → AST → emit → execute, no subprocess
- **11 RWL byte-IR languages** (added `rwast` as language id 10)
- **TriadScore** — harmonic mean of geometric / verification / mercy-civ
  metrics on every translation, so you can *measure* what came across
- **Sealed binary wire format** — `>BHH` per node, recursive children,
  wrapped in an RWL1 carrier with SHA256 gate
- **Stdlib-only** — no new dependencies; Python 3.9+

## Install

```bash
pip install --upgrade seraphina-agi
seraphina --version          # → seraphina 1.0.11
glyph --version              # → glyph 0.10.0
glyph transmute demo.py --to js
```

> The pure-`glyph install seraphina` channel is intentionally still pinned
> at 1.0.9 in `glyph-index.json` for now. Use `pip` for 1.0.11.

## Verification

| File | Size | SHA-256 |
|---|---|---|
| `seraphina_agi-1.0.11-py3-none-any.whl` | 100,826 B | `7e306bd042c6155b5b185e317f31b27fd16e6eaeba940e1840f81aac5bb9cc9c` |
| `seraphina_agi-1.0.11.tar.gz` | 86,749 B | `f11087d887a548f242c6ef10a3c4c0c679cbeda50625eeb46decc2cf255cdf8e` |

Published via PyPI Trusted Publisher (OIDC) — no token in repo. Built and
signed from commit `96789be` by `.github/workflows/publish.yml`.

## Docs

- [`README_RWAST.md`](README_RWAST.md) — full RWAST API, wire format,
  operator/builtin maps, Triad scoring, limitations, roadmap
- [`README.md`](README.md) — install channels + Build-an-AI wizard

## Community

The geometry side runs deeper than the package. Come find us:

- 🌐 Website: https://synergroaicorp.com
- 💬 Discord: https://discord.com/channels/1282932068942090252/1510800046340440206 *(username `donum_dei9446`)*
- ☕ Patreon: https://www.patreon.com/c/Donum_Dei9446?vanity=user
- 🐦 X / Twitter: [@JWCbnFbrMotorId](https://x.com/JWCbnFbrMotorId)
- 🛠️ GitHub: https://github.com/SynerGro-AI

🜂 "Binary that understands itself."
