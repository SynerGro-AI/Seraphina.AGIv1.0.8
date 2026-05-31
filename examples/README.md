# Examples

Two ready-to-run glyphs. Pack them into `.glyph` archives, then install and run.

## wheel_one — binary-native WASM, Rule-24 value = 179

```
sides=8  points=33  dots=1  intersections=1  spirals=8
value = 8*10 + 33 + 1 + 1 + 8 = 179   binary = 10110011
```

`code/main.wasm` is a real 59-byte WebAssembly module exporting:

- `value`     (global i32) = `179`
- `value_fn`  (func -> i32) = `179`

Pack, install, and run:

```bash
python -m glyph pack    examples/wheel_one      -o prebuilt/wheel_one-1.0.0.glyph
python -m glyph install prebuilt/wheel_one-1.0.0.glyph
python -m glyph run     wheel_one
python -m glyph run     wheel_one --export value_fn   # -> 179
```

## seraphina_core — OctaLang `.GL` source

Triad-aware glyph that emits the Roman Wheel Triad, Fibonacci-binary, and Manifest-369 signals.
Source: [seraphina_core/code/main.GL](seraphina_core/code/main.GL).

```bash
python -m glyph pack    examples/seraphina_core -o prebuilt/seraphina_core-1.0.0.glyph
python -m glyph install prebuilt/seraphina_core-1.0.0.glyph
python -m glyph run     seraphina_core
```

## Prebuilt archives

Both glyphs are already packed under [prebuilt/](../prebuilt/) so users can skip
the `pack` step entirely:

```bash
python -m glyph install prebuilt/wheel_one-1.0.0.glyph
python -m glyph install prebuilt/seraphina_core-1.0.0.glyph
```
