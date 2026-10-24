# RWAST — Roman Wheel Abstract Syntax Tree

**Cross-language semantic translation via a language-neutral binary IR.**

RWAST is the second tier of the Roman Wheel Language stack. Where the
byte-IR tier (`seraphina rwl encode/decode`) carries *source bytes*
losslessly between languages, RWAST carries *meaning* — the actual
program structure — and re-emits it as idiomatic source in any
supported target language.

```
                 ┌────────────────────────────────────────────┐
   Python ──────►│  RWAST   (53-node universal IR, binary)    │──────► Python
   JavaScript ──►│                                            │──────► JavaScript
   TypeScript ──►│  • Geometric / Verification / Mercy-Civ    │──────► TypeScript
   (more soon)   │  • SHA256 tamper-evident RWL1 carrier      │        (more soon)
                 └────────────────────────────────────────────┘
```

---

## Quick start

### Python API

```python
from seraphina.rwl.ast_ir import translate, parse, emit, encode_ast, decode_ast

src = """
def add(a, b):
    return a + b

def greet(name):
    print(f'Hello, {name}!')
"""

# One-shot translate
js = translate(src, "python", "js")
ts = translate(src, "python", "ts")

# Or two-step (gives you the IR)
root = parse(src, "python")      # → RWAST Node tree
js   = emit(root, "js")
ts   = emit(root, "ts")

# Persist the IR as a sealed binary blob (RWL1 carrier, SHA256-verified)
blob = encode_ast(root)          # bytes
root2 = decode_ast(blob)         # round-trip
```

### CLI

```bash
seraphina rwl translate hello.py --to js
seraphina rwl translate hello.py --to ts -o hello.ts
seraphina rwl translate hello.py --from python --to python -o roundtrip.py
```

---

## Supported languages

| Direction      | Python | JavaScript | TypeScript |
|----------------|:------:|:----------:|:----------:|
| **Frontend** (parse) | ✅ full | ⏳ planned | ⏳ planned |
| **Backend**  (emit)  | ✅ full | ✅ full    | ✅ full    |

So today: **Python → JS / TS / Python** is supported.
JS / TS frontends (and Rust, Go, C, Java backends) are next.

---

## What gets translated

53 node types covering the full Python language surface:

- **Module / Block / Import / ImportFrom**
- **FunctionDef / AsyncFunc / Lambda / ClassDef / Decorator / Param**
- **Assign / AugAssign / AnnAssign / Walrus**
- **If / While / For / Break / Continue / Return / Pass**
- **Try / Except / Raise / With / Assert / Delete**
- **Global / Nonlocal / Yield / YieldFrom / Await**
- **Call / KWARG / Starred / BinOp / UnaryOp / Compare / BoolOp / Ternary**
- **Name / Const / Attr / Subscript / Slice**
- **List / Dict / Tuple / Set / TemplateStr (f-strings)**
- **Comprehension (list / set / dict / gen)**

### Operator mapping (Python → JS / TS)

| Python  | JS / TS                       |
|---------|-------------------------------|
| `and`   | `&&`                          |
| `or`    | `\|\|`                        |
| `not`   | `!`                           |
| `==`    | `===`                         |
| `!=`    | `!==`                         |
| `is`    | `===`                         |
| `is not`| `!==`                         |
| `in`    | `arr.includes(x)`             |
| `not in`| `!arr.includes(x)`            |
| `//`    | `Math.floor(a / b)`           |
| `**`    | `**` (preserved)              |

### Builtin mapping (Python → JS / TS)

| Python   | JS / TS         |
|----------|-----------------|
| `print(*xs[, sep=][, end=])` | `__py_print([...xs], sep, end)` (each value as Python's `str()`; `file=` is refused) |
| `len(x)` | `__py_len(x)` (code points for a str, `.size` for Set/Map, key count for a dict) |
| `str(x)` / `repr(x)` | `__py_str(x)` / `__py_repr(x)` (`True`, `None`, `0.5`, `1e-05`, `[1, 'a']`, `{'k': 1}`) |
| `int`    | `parseInt`      |
| `float`  | `parseFloat`    |
| `abs`    | `Math.abs`      |
| `max(a, b, ...)` | `Math.max(a, b, ...)` |
| `min(a, b, ...)` | `Math.min(a, b, ...)` |
| `max(xs)` / `min(xs)` (one iterable) | `Math.max(...xs)` / `Math.min(...xs)` |
| `range(stop)` / `range(start, stop[, step])` | `Array.from(...)` (inline helper; step 0 throws `RangeError`) |
| `sum(xs[, start])` | `[...xs].reduce((a, b) => a + b, start)` |
| `sorted(xs[, key=f][, reverse=True])` | copy + `.sort()` with a Python-order comparator (the input is not mutated) |
| `enumerate(xs[, start])` | `Array.from(xs, (v, i) => [i + start, v])` |
| `round`  | `Math.round`    |
| `None`   | `null`          |
| `True`   | `true`          |
| `False`  | `false`         |
| f-string | template literal, each field through `__py_str` (`` `${__py_str(x)}` ``) |

### str methods (Python → JS / TS)

JS has no static types, so `s.split()` cannot be rewritten at compile time.
Each str method call becomes a call to a small helper, `__py_<method>(s, ...)`,
emitted once at the top of the module and only if the program uses it. When
`s` is a JS string the helper applies CPython's rules; any other receiver gets
its own method called with the original arguments (`list.count`/`list.index`
are handled for arrays). Keyword arguments are placed by CPython's parameter
names; an unknown keyword is refused at translate time (`ValueError`).

| Python | Semantics carried over |
|--------|------------------------|
| `upper()`, `lower()` | Unicode case mapping |
| `strip/lstrip/rstrip([chars])` | Python's 29 whitespace characters (the table comes from CPython), or the given chars |
| `split([sep[, maxsplit]])` | no `sep`: runs of whitespace, ends dropped, `maxsplit` keeps the rest; `sep=""` raises `ValueError: empty separator` |
| `sep.join(xs)` | non-str item raises `TypeError: sequence item N: expected str instance, int found` |
| `replace(old, new[, count])` | all occurrences, `count` limits; empty `old` inserts between code points |
| `startswith/endswith(x \| tuple[, start[, end]])` | tuple (array) of prefixes, Python slice bounds |
| `find`, `index`, `count` (`sub[, start[, end]]`) | code-point indices; `index` raises `ValueError: substring not found` |
| `isdigit()`, `isdecimal()`, `isalpha()`, `isspace()` | `\p{Nd}` plus CPython's non-decimal digits (`²`), `\p{L}`, Python whitespace |
| `capitalize()`, `title()` | CPython's title-case table (`ß` → `Ss`, `ǆ` → `ǅ`), runs split at uncased characters (`they're` → `They'Re`) |
| `fmt.format(*a, **kw)` | `{}`, `{0}`, `{name}`, `{{`/`}}`; values through `__py_str`; a format spec or conversion (`{:>4}`, `{!r}`, `{0.x}`) throws `NotImplementedError` at run time instead of printing something else |

`tests/test_js_backend.py` runs the same programs under CPython and node and
asserts identical stdout, plus the error cases above.

### TypeScript additions

- Parameters: `name: any` (or the source annotation if present)
- Return type: `: any` if the function returns a value, else `: void`
- Top-level `function` / `class` get the `export` keyword

---

## Roman Wheel Triad fidelity scoring

Any two RWAST trees can be scored against each other with `score()`.
`translate()` does not score automatically. Only a Python frontend exists, so
the usual check is the Python round trip:

```python
from seraphina.rwl.ast_ir import parse, emit, score

original   = parse(src, "python")
round_trip = parse(emit(original, "python"), "python")
print(score(original, round_trip))
# Geometric=1.000  Verification=1.000  Mercy-Civ=1.000  Consensus=1.000
```

| Axis          | Meaning                                                  |
|---------------|----------------------------------------------------------|
| Geometric     | Structural shape (node count + depth) similarity         |
| Verification  | Jaccard overlap of node-kind sets                        |
| Mercy-Civ     | Reward for low fallback / unknown-node ratio             |
| Consensus     | Harmonic mean of the three (0.0 – 1.0)                   |

---

## Binary wire format

RWAST trees are packed using a self-delimiting big-endian format:

```
[u8  node_type    ]
[u16 n_children   ]
[u16 data_len     ]
[u8* data         ]   ← UTF-8 JSON of node.data
[... children     ]   ← recursive
```

`encode_ast(root)` wraps the packed bytes in the RWL1 carrier with
language id `rwast` (id=10), giving SHA256 tamper-evidence and optional
zlib compression. `decode_ast(blob)` verifies the hash before unpacking.

---

## Example output

**Input** (`hello.py`):
```python
def add(a, b):
    return a + b

def greet(name):
    print(f'Hello, {name}!')
```

**`seraphina rwl translate hello.py --to js`** (the `__py_print`, `__py_str`,
`__py_repr` and `__py_float_repr` helper definitions that open the file are
left out here):
```javascript
function add(a, b) {
  return (a + b);
}
function greet(name) {
  __py_print([`Hello, ${__py_str(name)}!`], null, null);
}
```

**`seraphina rwl translate hello.py --to ts`:**
```typescript
export function add(a: any, b: any): any {
  return (a + b);
}
export function greet(name: any): void {
  __py_print([`Hello, ${__py_str(name)}!`], null, null);
}
```

---

## Limitations (v1)

- **Python frontend only** — JS/TS source cannot yet be parsed *into* RWAST
- **Classes do not run yet** — methods are emitted as `function name(self)`
  inside the class body (not valid JS), `self` is not rewritten to `this`, and
  `Cls()` is not rewritten to `new Cls()`. Planned.
- **Numbers** — JS has one number type, so a float with an integral value
  prints like an int (`4 / 2` prints `2`, Python prints `2.0`). Other floats
  print with Python's `repr` rules (`0.1`, `1e-05`, `1.5e+16`).
- **Tuples** become arrays and print as `[1, 2]`; dict keys become strings, so
  a dict with int keys prints `{'1': 2}`.
- **f-string format specs and conversions** (`f"{x:.2f}"`, `f"{x!r}"`) are
  dropped by the Python frontend, which keeps only the value. Planned: carry
  them in the IR and translate or refuse them.
- **str methods not listed above** (`rsplit`, `splitlines`, `partition`,
  `zfill`, `center`, `ljust`, `rjust`, `isupper`, `islower`, `isalnum`,
  `casefold`, `swapcase`, `encode`, ...) pass through as a plain JS method
  call and throw `TypeError: ... is not a function` on a string. Bound method
  references (`f = s.upper`) are not translated.
- **`list.index` / `list.count`** compare with `===`, so nested lists and dicts
  are compared by identity, not by value as in Python.
- **Standard library calls are not auto-imported** — `console.log` is mapped but
  Node.js-specific modules are not synthesized
- **Comprehensions** translate to `.filter().map()` / `Object.fromEntries`
  chains; correct but not always pretty
- **`with`** statement becomes a JS scope block (no resource management semantics)
- **Slices** are emitted as comments in JS (`/* slice(0, 5) */`) — not yet rewritten
  to `.slice()` calls (one of the next steps)
- **Type annotations** in Python (`int`, `list[str]`, ...) carry into TS as `: any`
  for now; a smarter type bridge is planned

Python constructs the frontend cannot parse become `UNKNOWN` / raw nodes, and
those lower the Mercy-Civ score. Backend-side gaps, such as the slice comments
above, do **not** affect the score, which is why they are listed here.
`range()` is materialised as an array (JS has no lazy range), so printing a
bare `range` object gives a different result from Python's `range(0, n)`
repr.

---

## Roadmap

- JavaScript / TypeScript frontends (full)
- Rust / Go / Java / C backends
- Smart slice → `.slice()` rewrite
- Python type-hint → TypeScript type bridge
- `glyph run` of RWAST-packed packages (`glyph transmute` and `glyph exec`
  already ship)
- Bytecode-level optimization passes operating on RWAST before emission

---

## See also

- `seraphina/rwl/codec.py` — byte-IR RWL1 container (level 1)
- `seraphina/rwl/wheel.py` — bijective byte ↔ Roman Wheel symbol
- `seraphina/rwl/ast_ir/` — the AST-IR tier described above
