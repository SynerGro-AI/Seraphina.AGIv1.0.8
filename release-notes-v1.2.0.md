# Seraphina.AGI 1.2.0 (draft release notes; not tagged or published)

Audit release: every claim in the README and `.md` files now matches the
code, and anything not built is labelled **planned**.

### Added
- **Constitution in code.** 20 rules in `seraphina/constitution.py`,
  hash-pinned (`RULES_SHA256`); 13 enforced as deterministic checks, 7
  labelled planned. `seraphina --verify-rules`, `--export-audit [FILE]`,
  `rules [rule_N]`. Decisions go to a SHA-256 hash-chained
  `~/.seraphina/audit.jsonl`.
- **Rule 19 halt.** Any blocked action (except a rule-17 rate-limit refusal)
  or a failed integrity check halts Seraphina. Every acting command then
  exits 3 until a person runs `seraphina --reset-rules "<reason>"`.
  Read-only diagnostics still work. The halt is re-derived from the audit
  chain, so deleting `halted.json` does not lift it.
- **Exit codes** for `seraphina` and `glyph`: 0 ok, 1 error, 2 usage,
  3 blocked by the rules.
- **`glyph exec` / `glyph run` need `--trusted`** for code that runs outside
  a real sandbox (rule 7). Without it: exit 3, logged as `refused`.
- **Py→JS/TS str methods** with CPython semantics: upper, lower, strip,
  lstrip, rstrip, split, join, replace, startswith, endswith, find, index,
  count, isdigit, isdecimal, isalpha, isspace, capitalize, title, format
  (positional/named fields), plus `str()`, `repr()`, `len()`,
  `print(sep=, end=)` and f-string fields. Tests run each program under node
  and CPython and compare the output byte for byte.
- **Glyph geometry from the seed.** `OctaLangGlyphGenerator.generate()`
  derives spiral turns, triangles, dots, facets and intersections from
  SHA-256 of the description (`geometry()`, `GEOMETRY_RANGES`). Same text,
  same glyph; different text, different glyph.
- **Glyph IDs** are 16 hex chars of SHA-256 (the old gematria-mod-999 IDs
  collided); legacy numeric IDs can still be read.
- `glyph remote-add` rejects non-`http(s)://` URLs.
- `tests/_util.require_tool`: a test that needs a missing tool skips with the
  reason, and fails under `SERAPHINA_REQUIRE_ALL_TESTS=1`.
- `[tool.ruff]` config in `pyproject.toml`; `ruff check .` is clean.

### Changed
- `rwl encode/decode/translate -o out` writes `out` (it created a file
  named `-o`). `python -m seraphina.cli` runs the CLI.
- Errors go to stderr with a non-zero exit code (`rules rule_99`,
  `plan-grok` without a key, ...).
- `glyph exec` runs the program in a child `python` process instead of
  `exec()` inside the CLI.
- Telemetry/ledger write failures in glyph now raise a `RuntimeWarning`
  instead of being swallowed.

### Deleted
- `seraphina/triad.py`: unused; returned hard-coded, simulated output and
  used `eval` and an unused PRNG.
- `seraphina/language_bridge.py`: unused; called a JS file that does not
  exist (`advanced-language-engine.js`) and returned error dicts instead of
  failing.
- The `~/.seraphina/wizard/history.jsonl` writer (`HISTORY_FILE`): it logged every
  command line without consent, against rule 1. Existing files are left in
  place; delete them by hand if you want.
- `HALT_FILE` in `seraphina/cli.py` (the halt lives in `seraphina/gate.py`
  and the audit chain).
- The in-process `exec()` in `glyph exec`.
- The `null://` echo host in `glyph/glyph/remote.py`, and the
  `set_transport()` / `_transport` fake-HTTP seam. Tests use a real local
  HTTP server.
- The fixed glyph template (intrinsic value 178 for every description) and
  the private `OctaLangGlyphGenerator._intrinsic_value` (now the module
  function `intrinsic_value`).
- JS backend: `len(x)` → `x.length` and `print` → `console.log` mappings
  (wrong for dicts, sep/end, and Python's printing of True/None/lists);
  replaced by runtime helpers.
- Silent `except: pass` in glyph identity/operations/remote telemetry and in
  the Python frontend's annotation reader.
- Unused imports and a dead local variable flagged by ruff.
- Tests removed because their expectation was wrong or they tested deleted
  code: `test_non_privacy_violation_does_not_halt` (rule 19 halts on any
  violation), `test_null_host_echoes` and `test_transport_called_with_auth`
  (replaced by real-server tests).

### Known limits (planned)
- Deleting the whole audit log (and halt file) starts a new chain; external
  anchoring of the chain head is planned.
- Translated Python classes are not runnable JS yet.
- f-string format specs and conversions are dropped by the Python frontend.
- Rules 4, 5, 6, 11, 12, 15, 20 are planned.

## Install (after publication)

```bash
pip install --upgrade seraphina-agi
seraphina --version          # -> seraphina 1.2.0
seraphina --verify-rules     # exit 0 = rule table and audit chain OK
```
