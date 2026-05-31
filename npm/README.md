# seraphina-agi (npm wrapper)

This is a **thin Node wrapper** around the Python package
[`seraphina-agi`](https://pypi.org/project/seraphina-agi/). It exists so
JavaScript-first developers can do:

```bash
npm install -g seraphina-agi
seraphina
```

## Requirements

- Node.js >= 14
- Python >= 3.9 with `seraphina-agi` installed:
  ```bash
  pip install seraphina-agi
  ```

The wrapper looks for Python in this order:

1. `$SERAPHINA_PYTHON` (explicit override)
2. `py` on Windows, `python3` elsewhere
3. `python` fallback

## Publishing

Not yet published to the npm registry. To publish:

```bash
cd npm
npm publish --access public
```
