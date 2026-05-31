# Glyph — Seraphina's Package Manager (v0.1)

A lightweight, auditable package manager that runs **parallel to pip**,
managing `.glyph` packages (code + JSON manifest) for the Seraphina AGI
ecosystem.

Reference architecture: **pip** (commands / operations / resolution / network split).
Reference artifacts: `../seraphina-glyph/` (assembler, VM, manifest.octa, wasm).

## Features (v0.1)

- `.glyph` package format = ZIP { `manifest.json`, `code/`, optional `geometry/` }
- SHA-256 integrity verification over the code tree
- Minimal version-pinned dependency resolver (`==`, `>=`, `<`, comma-AND)
- Local filesystem `GlyphIndex` (analogous to PyPI), under `$GLYPH_HOME`
  (default `~/.seraphina/glyph_home/`)
- **Emotional approval gate** — pluggable hook so Seraphina can accept/reject
  installs based on `cost_estimate` and `risk_level`
- Best-effort sandbox loader (filtered `__builtins__`, allowlist imports)
- pip-style CLI: `install / uninstall / list / freeze / show / pack`

## Install

```powershell
cd C:\Users\jmwil\.seraphina\glyph
pip install -e .
glyph --version
```

Or without installing: `python -m glyph --help`

## Usage

```powershell
# Build a .glyph from a source directory containing manifest.json + code/
glyph pack ./my_glyph_src -o ./dist/my.glyph

# Install / inspect / remove
glyph install ./dist/my.glyph
glyph list
glyph show my_glyph
glyph freeze
glyph uninstall my_glyph
```

## Manifest schema (v1)

```json
{
  "schema": 1,
  "name": "memory_core",
  "version": "0.1.0",
  "entrypoint": "code/main.py",
  "sha256": "",
  "dependencies": [ {"name": "emotional_engine", "spec": ">=0.1.0"} ],
  "cost_estimate": 1.5,
  "risk_level": "low",
  "description": "Seraphina memory core glyph"
}
```

## Emotional gate hook

```python
from glyph import set_gate
from glyph.gate import GateDecision

def seraphina_gate(manifest):
    if manifest.name.startswith("experimental_"):
        return GateDecision(False, "Seraphina declined: experimental")
    return GateDecision(True, "Seraphina approves")

set_gate(seraphina_gate)
```

## Sandbox limitations (READ THIS)

The v0.1 sandbox is **not** a real security boundary. It filters
`__builtins__` and gates imports by allowlist, which only stops accidental
misuse. Treat all `.glyph` code as semi-trusted; gate execution behind the
emotional approval hook. For real isolation use a subprocess + OS sandbox
(future work; see `../glyph-wasm.ts` for the WASM direction).

## Test

```powershell
cd C:\Users\jmwil\.seraphina\glyph
python -m unittest discover -s tests -v
```
