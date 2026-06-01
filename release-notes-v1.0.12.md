# Seraphina.AGI 1.0.12 — Trust ladder on PyPI

**No engine changes.** This release republishes the package solely so
the new README — including the **"Verify this is real"** trust ladder,
community links, and cross-links to sibling tools — reaches the PyPI
project page.

PyPI README content is immutable per-version, so visibility upgrades
require a version bump. That's the entire changelog.

## What's actually different

- README adds a 4-rung **Verify this is real** section (run the package
  → compare hash to PyPI's published hash → OIDC commit provenance →
  read the source)
- Community block: website, Discord, Patreon, X, GitHub org
- Cross-links to `seraphina-grok-planner` (Copilot tools) and
  `seraphina-agi-releases` (signed Windows installer)
- `SECURITY.md` + `CONTRIBUTING.md` shipped in repo

## What did NOT change

- Engine code (`seraphina/`, `glyph/`) is byte-identical to 1.0.11
- Wire formats, public API, CLI commands — all unchanged
- Dependencies — still stdlib-only

## Install

```bash
pip install --upgrade seraphina-agi
seraphina --version          # → seraphina 1.0.12
```

## Verification

Same OIDC pipeline as 1.0.11 — built by GitHub Actions, no human token,
provable chain from tag → commit → wheel.

| File | Built from |
|---|---|
| `seraphina_agi-1.0.12-*.whl` | tag `v1.0.12` |
| `seraphina_agi-1.0.12.tar.gz` | tag `v1.0.12` |

Run `pip download seraphina-agi==1.0.12 --no-deps` and compare the
SHA256 against `https://pypi.org/pypi/seraphina-agi/1.0.12/json`.

## Community

- 🌐 <https://synergroaicorp.com>
- 💬 Discord: <https://discord.com/channels/1282932068942090252/1510800046340440206>
- ☕ <https://www.patreon.com/c/Donum_Dei9446?vanity=user>
- 🐦 [@JWCbnFbrMotorId](https://x.com/JWCbnFbrMotorId)

🜂 *Same engine. Visible chain of custody.*
