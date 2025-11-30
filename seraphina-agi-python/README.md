# Seraphina AGI Companion (Python)

Pure Python AGI companion for Seraphina - no mining, no wallets.

## Install

```bash
pip install -e .
```

## Usage

### CLI

```bash
seraphina-agi process --input "Hello, world!"
```

### API

```bash
seraphina-agi serve --port 8080
```

Then POST to http://localhost:8080/process with JSON {"input": "text"}

## Features

- Language processing with encryption
- HTTP API
- Pure Python