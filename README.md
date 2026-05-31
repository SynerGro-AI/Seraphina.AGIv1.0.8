# Seraphina.AGI

> Deterministic Roman Wheel Triad core, riding on **Glyph** - a binary-native
> package manager that runs parallel to pip. Geometry equals binary equals
> executable WASM. No pseudo-randomness. No hallucinations in the hot path.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Install in 30 seconds

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
