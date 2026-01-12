# Seraphina AGI Companion (Python)

Pure Python AGI companion for Seraphina - no mining, no wallets.

## Install

### From GitHub (Recommended)

```bash
pip install git+https://github.com/SynerGro-AI/Seraphina-agi-python.git
```

Replace `yourusername` with your GitHub username.

### Local Install

```bash
cd seraphina-agi-python
pip install -e .
```

Note: The script installs to `%APPDATA%\Python\Python313\Scripts\seraphina-agi.exe` (user install). Add this to PATH or run directly.

## Usage

### CLI

```bash
seraphina-agi process --input "Hello, world!"
# With voice: seraphina-agi process --voice
# With sharing: seraphina-agi process --input "Hello" --share

# Quantum core simulation
seraphina-agi quantum

# Crystal frequency tuning
seraphina-agi tune

# Mesh AI communications
seraphina-agi mesh
```

### Voice Chat

```bash
seraphina-agi voice
# Say "exit" to quit
```

### API

```bash
seraphina-agi serve --port 8080
```

Then POST to http://localhost:8080/process with JSON {"input": "text"}

## Features

- Language processing with encryption
- Deterministic quantum core simulation
- Crystal frequency tuning and harmonics
- Mesh AI-to-AI communications
- Pico-second data flow animation
- Unified system deployment
- Math/art stress testing
- 4-Tier Seraphina.AI processor
- HTTP API
- Pure Python
- Voice input/output (--voice)
- Collective learning (--share)