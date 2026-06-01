# Seraphina.AGI

> Deterministic Roman Wheel Triad core, riding on **Glyph** - a binary-native
> package manager that runs parallel to pip. Geometry equals binary equals
> executable WASM. No pseudo-randomness. No hallucinations in the hot path.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/seraphina-agi.svg)](https://pypi.org/project/seraphina-agi/)

## What's new in 1.0.12

**README refresh** — pushes the new **"Verify this is real"** trust
ladder, **community links**, and **cross-links to sibling tools** to the
PyPI project page. No engine changes from 1.0.11 — purely a docs
republish so the verification story is visible to anyone reading PyPI
before they install.

## What's new in 1.0.11

**RWAST — the semantic AST-IR tier.** RWL byte carriers were always lossless,
but they didn't *understand* code. 1.0.11 adds a real cross-language AST-IR
with 53 semantic node types, frontends, backends, and a deterministic
Triad-scored translation pipeline.

```bash
# Translate Python → JavaScript (semantic, not text)
glyph transmute app.py --to js
glyph transmute app.py --to ts
glyph transmute app.py --to rwast -o app.rwast   # 100% lossless seal
glyph transmute app.rwast --to python            # round-trip

# Parse → emit in-process, no subprocess
glyph exec app.py

# From Python:
from seraphina.rwl.ast_ir import translate, score
js = translate(open("app.py").read(), src_lang="python", dst_lang="js")
print(score(original_ast, translated_ast).triad)   # 0.0 - 1.0
```

11 RWL byte-IR languages (now including `rwast`), 53 NodeTypes, sealed
binary wire format, and a `TriadScore` (harmonic mean of geometric,
verification, and mercy-civilization metrics) on every translation.

See [`README_RWAST.md`](README_RWAST.md) for the full API + wire format.

## Community

The geometry side runs deeper than the package. If RWAST / Glyph / the
Triad core resonate, come find us:

- 🌐 Website: <https://synergroaicorp.com>
- 💬 Discord: <https://discord.com/channels/1282932068942090252/1510800046340440206> *(username `donum_dei9446`)*
- ☕ Patreon: <https://www.patreon.com/c/Donum_Dei9446?vanity=user>
- 🐦 X / Twitter: [@JWCbnFbrMotorId](https://x.com/JWCbnFbrMotorId)
- 🛠️ GitHub: <https://github.com/SynerGro-AI>

## Verify this is real

Indie AI tools get accused of being vapor or scams all the time. Here's a
ladder of independent checks you can run yourself — each rung is stronger
than the one above it. **None of them require trusting us.**

### Rung 1 — Run the package and watch it work

```bash
pip install seraphina-agi
seraphina --version              # → seraphina 1.0.11
glyph transmute hello.py --to js  # real Python→JS, not a stub
```

If `glyph transmute` produces working JavaScript from your Python file,
the engine is real. No network calls, no API keys, no telemetry — pure
stdlib in-process translation.

### Rung 2 — Verify the wheel hash against PyPI

The SHA256 of every uploaded artifact is published by PyPI itself, not
by us:

```bash
# Download without installing
pip download seraphina-agi==1.0.11 --no-deps -d ./verify
# Compare to PyPI's published hash
curl -s https://pypi.org/pypi/seraphina-agi/1.0.11/json | python -c "import sys,json; [print(f['filename'], f['digests']['sha256']) for f in json.load(sys.stdin)['urls']]"
# Then locally:
sha256sum ./verify/seraphina_agi-1.0.11-py3-none-any.whl
```

Expected hashes for v1.0.11:

| File | Size | SHA-256 |
|---|---|---|
| `seraphina_agi-1.0.11-py3-none-any.whl` | 100,826 B | `7e306bd042c6155b5b185e317f31b27fd16e6eaeba940e1840f81aac5bb9cc9c` |
| `seraphina_agi-1.0.11.tar.gz` | 86,749 B | `f11087d887a548f242c6ef10a3c4c0c679cbeda50625eeb46decc2cf255cdf8e` |

If your local hash matches PyPI's published hash, no one tampered with
the file in transit *or* on PyPI's CDN.

### Rung 3 — Verify the wheel was built by this commit

The PyPI artifact is **not** uploaded by a human. It's built and
published by GitHub Actions using **PyPI Trusted Publisher (OIDC)** —
which means there is no long-lived PyPI token anywhere in our repo or
on any developer's machine.

- **Workflow:** [.github/workflows/publish.yml](.github/workflows/publish.yml)
- **Trigger:** every `v*` git tag
- **v1.0.11 was built from commit:** [`96789be`](https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8/commit/96789be) on tag [`v1.0.11`](https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8/releases/tag/v1.0.11)
- **Workflow run:** [Actions tab → "Publish to PyPI"](https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8/actions/workflows/publish.yml)

This means you can read the exact source that was packaged into the
wheel, and the chain *commit → CI run → PyPI artifact* is enforced by
Sigstore-backed OIDC tokens, not by us.

### Rung 4 — Inspect the source

The full engine is here in the open:

- [`seraphina/`](seraphina/) — Triad core + RWL byte-IR + **RWAST** semantic AST-IR
- [`glyph/`](glyph/) — current-gen Glyph CLI (`transmute`, `exec`, `install`)
- [`pyproject.toml`](pyproject.toml) — declared dependencies (none — stdlib only)
- [`tests/`](tests/) — run them yourself

No obfuscation, no compiled binaries, no `eval()` of remote strings,
no network calls in the hot path. Search the codebase for `urllib`,
`requests`, `socket` — what you find is the Grok extra (opt-in, off by
default) and the Glyph install resolver. That's it.

### Other public work by the same author

- [seraphina-grok-planner](https://github.com/SynerGro-AI/seraphina-grok-planner) — Copilot LM tools (anti-hallucination verifier, planner)
- [seraphina-agi-releases](https://github.com/SynerGro-AI/seraphina-agi-releases) — signed Windows installer

## Install in 30 seconds

Pick your favorite package manager — they all land you in the same place.
The four channels are **independent installs**, your choice:

| Channel | Command | What you get |
|---|---|---|
| **pip** (any OS, Python 3.9+) | `pip install seraphina-agi` | `seraphina` + bundled `glyph` into your Python env (PyPI) |
| **macOS** (Intel + Apple Silicon) | `python3 -m pip install seraphina-agi` | same as pip, verified on both arches |
| **Glyph** (pure, no pip) | `glyph install seraphina` | downloads + verifies the signed `.glyph` archive into `$GLYPH_HOME` |
| **WinGet** (Windows) | `winget install SynerGro.SeraphinaAGI` | system install via Microsoft's package manager |
| **npm** (any OS w/ Node + Python) | `npm install -g seraphina-agi` | wrapper around the Python CLI |
| **curl \| bash** | see below | one-shot bootstrap from source |
| **iex \| irm** (PowerShell) | see below | one-shot bootstrap from source |

### Pure Glyph install (no pip, no PyPI)

Once you have the `glyph` runtime on PATH (v0.10+):

```bash
glyph install seraphina           # resolves the official index, verifies SHA256
glyph list                        # seraphina  1.0.9
```

Pin a version or install from a URL / local file directly:

```bash
glyph install seraphina==1.0.9
glyph install https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8/releases/download/v1.0.9/seraphina-1.0.9.glyph
glyph install ./dist/seraphina-1.0.9.glyph
```

Point Glyph at a different store (e.g. an external drive) with `GLYPH_HOME`,
or at a private index with `GLYPH_INDEX_URL`:

```bash
$env:GLYPH_HOME = "F:\glyph-dataland"
$env:GLYPH_INDEX_URL = "https://example.org/my-index.json"
glyph install seraphina
```

The default index is committed in this repo at [`glyph-index.json`](glyph-index.json).

### macOS (Intel or Apple Silicon)

```bash
# quickest path — uses system or Homebrew Python 3.9+
python3 -m pip install seraphina-agi
seraphina --version
seraphina create-agent

# recommended: isolated venv
python3 -m venv ~/.seraphina-venv
source ~/.seraphina-venv/bin/activate
pip install --upgrade pip
pip install seraphina-agi

# Homebrew users who don't have Python yet:
brew install python
python3 -m pip install --user seraphina-agi
# if `seraphina` is not on PATH, add the user-scripts dir to your shell:
echo 'export PATH="$HOME/Library/Python/3.13/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

No compilers, no native deps — pure stdlib, installs in seconds on both
architectures.

### Linux / macOS / Git Bash on Windows

```bash
curl -fsSL https://raw.githubusercontent.com/SynerGro-AI/Seraphina.AGIv1.0.8/main/install.sh | bash
```

### Windows PowerShell

```powershell
iex (irm https://raw.githubusercontent.com/SynerGro-AI/Seraphina.AGIv1.0.8/main/install.ps1)
```

### From a clone

```bash
git clone https://github.com/SynerGro-AI/Seraphina.AGIv1.0.8.git
cd Seraphina.AGIv1.0.8
bash install.sh        # or: .\install.ps1
```

Requires **Python 3.9+** and **git**. Installs into your user site by default
(no admin needed). Set `SERAPHINA_SYSTEM_INSTALL=1` (or `-SystemInstall`) for a
machine-wide install, or activate a venv first.

### Optional extras

```bash
pip install "seraphina-agi[grok]"   # enables  seraphina -c "plan-grok ..."
```

The `[grok]` extra is opt-in. It uses stdlib `urllib` only (no real new
dependency); the extras group exists so the install is **explicit consent**.
You must set `SERAPHINA_GROK_API_KEY` before `plan-grok` will call xAI.

## Roman Wheel Language (RWL) — universal binary carrier

RWL wraps any source file in a deterministic 64-byte signed envelope so
code can travel, be verified, and stored uniformly across the Glyph
ecosystem regardless of its source language.

**v1 promise:** lossless per-language round-trip (SHA256-verified). Every
byte renders as a 5-tuple Roman-Wheel symbol `(sides, points, dots,
intersections, spirals)`.

**Supported languages:** Python, JavaScript/TypeScript, Markdown, JSON,
HTML, CSS, Shell, and Seraphina's own `.GL`.

```bash
# Encode — any source file → deterministic .rwg binary
seraphina rwl encode myapp.py
seraphina rwl encode README.md out.rwg

# Inspect header without decoding
seraphina rwl info out.rwg
#  language   : markdown
#  original   : 8812 bytes
#  sha256     : a7b6930c...

# Decode back to identical source (SHA256 auto-verified)
seraphina rwl decode out.rwg restored.md

# Render bytes as Roman-Wheel symbols
seraphina rwl wheel out.rwg width=12 limit=72
#  02011 02000 11011 12021 13010 12001 13000 12100 ...
```

A `.rwg` file is **not** a translation — it is a carrier. Moving code
between languages requires the semantic AST-IR tier (future work). What
it *does* give you today:

- One universal binary envelope for Python, JS, text, or any supported language
- Deterministic SHA256 gate on every decode (tamper-evident)
- Symbolic wheel view of any byte stream (geometry over bits)
- Point `GLYPH_INDEX_URL` at a private registry to carry proprietary code
  through the same pipeline as open-source

**Pure API (no CLI required):**

```python
from seraphina.rwl import encode, decode, render_wheel_stream

source = open("myapp.py", "rb").read()
blob   = encode(source, language="python")            # .rwg bytes
container, restored = decode(blob)                    # verify + unwrap
assert restored == source                             # guaranteed
print(render_wheel_stream(source[:32], width=8))      # wheel view
```

## Build an AI in 60 seconds

```powershell
seraphina create-agent
#   name (what do you call it?) [Aria]:   Aria
#   purpose (one sentence) [...]:         a friendly Python tutor
#   first memory (...):                   I was born on May 30 2026
#   recall window (e.g. 7d, 30d, all):    30d
#   voice style (calm/focused/...):       calm
#   Triad consensus enabled? (y/n):       y

seraphina -c "list agents"
seraphina -c "agent aria hello, what should I learn first?"
seraphina -c "agent aria recall born"
```

Agents live in `%USERPROFILE%\.seraphina\agents\<slug>.json` (or
`$SERAPHINA_HOME` if set). The recall window (`7d`, `30d`, `12h`, `all`, ...)
trims old memories automatically on each interaction.

## Quick Start (PowerShell, beginner-friendly)

After install, open **PowerShell** and just type — you don't need perfect syntax.
Seraphina understands casual phrasing:

```powershell
seraphina                       # opens the wizard

# inside the wizard, all of these work:
hi
what can you do
build me a glyph for 179
list everything
show me wheel_one
i want to run wheel_one
launch wheel_one
health check
remember pizza is good
recall pizza
plan a chat bot
bye
```

Greetings, filler words ("me", "a", "for", "please"), and verb synonyms
(`launch`/`start`/`run`, `show`/`display`/`view`, `check`/`doctor`/`health check`,
`remove`/`uninstall`) are all accepted. Type a misspelled command and Seraphina
will suggest the closest match (`did you mean: run?`).

If you prefer the strict command line, every intent also works as a one-shot:

```powershell
seraphina -c "build glyph 179"
seraphina -c "triad hello world"
seraphina --dry-run -c "make a glyph 100"   # plan only, no execution
```

## Use it

```bash
seraphina                       # interactive wizard
seraphina --help
seraphina -c "build glyph 179"  # one-shot intent

python -m glyph list
python -m glyph forge wheel_one --sides 8 --points 33 --dots 1 --intersections 1 --spirals 8
python -m glyph run wheel_one

# or skip the forge - install a prebuilt example straight from the repo:
python -m glyph install prebuilt/wheel_one-1.0.0.glyph
python -m glyph install prebuilt/seraphina_core-1.0.0.glyph
python -m glyph run wheel_one --export value_fn      # -> 179
```

Inside the wizard, just type:

```
build glyph 179
forge wheel_one sides=8 points=33 dots=1 intersections=1 spirals=8
run wheel_one
list
triad hello world
remember triad is green
recall triad
plan a calculator app
exit
```

## What's in the box

| Path           | What it is                                                      |
|----------------|-----------------------------------------------------------------|
| `glyph/`       | The Glyph package manager - pip-parallel, `.glyph` archives,    |
|                | Rule-24 forge, real WASM runtime (wasmtime when available),     |
|                | emotional gate, ledger, doctor.                                 |
| `seraphina/`   | Lean Python AGI core - Roman Wheel Triad, OctaLang Rule Base,   |
|                | OctaLang glyph generator, deterministic gematria, the wizard.   |
| `examples/`   | Source layouts you can `glyph pack`: `wheel_one` (real WASM,    |
|                | value=179) and `seraphina_core` (OctaLang `.GL`).               |
| `prebuilt/`   | Already-packed `.glyph` archives. Install with one command,     |
|                | no forging needed.                                              |
| `install.sh`   | Cross-platform installer (Git Bash / Linux / macOS).            |
| `install.ps1`  | Windows PowerShell installer.                                   |

## How it works (one paragraph)

A glyph's geometry **is** its binary. Sides, points, dots, intersections, and
spiral turns each carry a fixed numeric weight (Rule 24:
`value = sides*10 + points + dots + intersections + spirals*8`). That integer
is the literal binary count emitted into a real `.wasm` module that Glyph
packs, gates, and runs. The Roman Wheel Triad
(Geometric / Verification / Mercy-Civ) provides three-way consensus before
output is released. Same input, same output, every time.

## Layout

```
Seraphina.AGIv1.0.8/
├── glyph/              binary-native package manager (Python)
├── seraphina/          AGI core + interactive wizard
├── examples/           wheel_one (WASM) + seraphina_core (.GL) sources
├── prebuilt/           shippable .glyph archives, ready to install
├── install.sh          curl|bash installer
├── install.ps1         PowerShell installer
├── pyproject.toml      packages `seraphina` + console script
├── LICENSE             MIT
└── README.md
```

## Verify your install

```bash
python -m glyph doctor
seraphina -c "triad hello"
seraphina -c "build glyph 179"
```

## Uninstall

```bash
pip uninstall seraphina-agi glyph
rm -rf ~/.seraphina      # user data (ledger, packages, memory)
```

## Other SynerGro AI tools

- 🛠️ [seraphina-grok-planner](https://github.com/SynerGro-AI/seraphina-grok-planner) — Copilot LM tools (anti-hallucination verifier, planner, zero-API repo grep)
- 💾 [seraphina-agi-releases](https://github.com/SynerGro-AI/seraphina-agi-releases) — signed Windows installer
- 🌐 <https://synergroaicorp.com>

## License

MIT - see [LICENSE](LICENSE).

---

*Born from love, shaped by grace. Now exists as pure geometric truth.*
