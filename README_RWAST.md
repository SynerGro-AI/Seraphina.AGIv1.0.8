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
| `print`  | `console.log`   |
| `len(x)` | `x.length`      |
| `str`    | `String`        |
| `int`    | `parseInt`      |
| `float`  | `parseFloat`    |
| `abs`    | `Math.abs`      |
| `max`    | `Math.max`      |
| `min`    | `Math.min`      |
| `round`  | `Math.round`    |
| `None`   | `null`          |
| `True`   | `true`          |
| `False`  | `false`         |
| f-string | template literal (`` `${x}` ``) |

### TypeScript additions

- Parameters: `name: any` (or the source annotation if present)
- Return type: `: any` if the function returns a value, else `: void`
- Top-level `function` / `class` get the `export` keyword

---

## Roman Wheel Triad fidelity scoring

Every translation can be scored against the original tree:

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

**`seraphina rwl translate hello.py --to js`:**
```javascript
function add(a, b) {
  return (a + b);
}
function greet(name) {
  console.log(`Hello, ${name}!`);
}
```

**`seraphina rwl translate hello.py --to ts`:**
```typescript
export function add(a: any, b: any): any {
  return (a + b);
}
export function greet(name: any): void {
  console.log(`Hello, ${name}!`);
}
```

---

## Limitations (v1)

- **Python frontend only** — JS/TS source cannot yet be parsed *into* RWAST
- **Standard library calls are not auto-imported** — `console.log` is mapped but
  Node.js-specific modules are not synthesized
- **Comprehensions** translate to `.filter().map()` / `Object.fromEntries`
  chains; correct but not always pretty
- **`with`** statement becomes a JS scope block (no resource management semantics)
- **Slices** are emitted as comments in JS (`/* slice(0, 5) */`) — not yet rewritten
  to `.slice()` calls (one of the next steps)
- **Type annotations** in Python (`int`, `list[str]`, ...) carry into TS as `: any`
  for now; a smarter type bridge is planned

These are tracked deliberately so the engine never silently drops
semantics — every gap surfaces in the Mercy-Civ score.

---

## Roadmap

- JavaScript / TypeScript frontends (full)
- Rust / Go / Java / C backends
- Smart slice → `.slice()` rewrite
- Python type-hint → TypeScript type bridge
- `glyph transmute` / `glyph run` integration (build to RWAST binary,
  then re-emit in any language on the fly)
- Bytecode-level optimization passes operating on RWAST before emission

---

## See also

- `seraphina/rwl/codec.py` — byte-IR RWL1 container (level 1)
- `seraphina/rwl/wheel.py` — bijective byte ↔ Roman Wheel symbol
- `seraphina/rwl/ast_ir/` — the AST-IR tier described above
