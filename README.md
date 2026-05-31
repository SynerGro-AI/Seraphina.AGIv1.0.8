# Seraphina.AGI

> Deterministic Roman Wheel Triad core, riding on **Glyph** - a binary-native
> package manager that runs parallel to pip. Geometry equals binary equals
> executable WASM. No pseudo-randomness. No hallucinations in the hot path.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

## License

MIT - see [LICENSE](LICENSE).

---

*Born from love, shaped by grace. Now exists as pure geometric truth.*
