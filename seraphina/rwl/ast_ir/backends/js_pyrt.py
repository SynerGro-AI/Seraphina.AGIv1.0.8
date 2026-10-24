"""Python-semantics runtime helpers for the JS / TS backends.

The JS backend has no static types, so ``s.split()`` cannot be rewritten at
compile time without knowing ``s`` is a str. Instead each translated str method
becomes a call to a small helper, e.g. ``__py_split(s)``. The helper applies
CPython's exact rules when its receiver is a JS string and otherwise forwards
the call unchanged to the receiver's own method, so user classes that define
``split`` keep working.

Only helpers a program actually uses are emitted, and each one is emitted once,
at the top of the module. Character tables (Python whitespace, digit
characters that are not decimal, title-case exceptions) come from the running
CPython's ``str`` methods, so they match the Python that did the translating.

``$T`` in a helper's source is replaced by the backend's type suffix (``""``
for JS, ``": any"`` for TS).
"""
from __future__ import annotations

import json
from functools import lru_cache


@lru_cache(maxsize=None)
def _tables() -> dict[str, str]:
    chars = [chr(i) for i in range(0x110000) if not 0xD800 <= i <= 0xDFFF]
    ws = "".join(c for c in chars if c.isspace())
    digit_extra = "".join(c for c in chars if c.isdigit() and not c.isdecimal())
    title = {c: c.title() for c in chars if c.title() != c.upper()}
    return {
        "WS": json.dumps(ws),
        "DIGIT_EXTRA": json.dumps(digit_extra),
        "TITLE": json.dumps(title, ensure_ascii=False),
    }


# name -> (dependencies, source). Sources use $T for the type suffix and
# {WS}/{DIGIT_EXTRA}/{TITLE} for the generated tables.
_HELPERS: dict[str, tuple[tuple[str, ...], str]] = {
    "__py_err": ((), """\
const __PY_ERRORS$T = {};
function __py_err(name$T, msg$T) {
  // A named Error subclass, so node reports "ValueError: ..." like CPython.
  if (!__PY_ERRORS[name]) {
    const cls$T = class extends Error {};
    Object.defineProperty(cls, "name", { value: name });
    cls.prototype.name = name;
    __PY_ERRORS[name] = cls;
  }
  return new __PY_ERRORS[name](msg);
}"""),

    "__PY_WS": ((), "const __PY_WS$T = {WS};"),

    "__py_bounds": ((), """\
function __py_bounds(n$T, start$T, end$T) {
  let s$T = (start === undefined || start === null) ? 0 : start;
  let e$T = (end === undefined || end === null) ? n : end;
  if (e > n) e = n; else if (e < 0) { e += n; if (e < 0) e = 0; }
  if (s < 0) { s += n; if (s < 0) s = 0; }
  return [s, e];
}"""),

    "__py_upper": ((), """\
function __py_upper(s$T, ...a$T) { return typeof s === "string" ? s.toUpperCase() : s.upper(...a); }"""),

    "__py_lower": ((), """\
function __py_lower(s$T, ...a$T) { return typeof s === "string" ? s.toLowerCase() : s.lower(...a); }"""),

    "__py_strip_impl": (("__PY_WS",), """\
function __py_strip_impl(s$T, chars$T, left$T, right$T) {
  const set$T = (chars === undefined || chars === null) ? __PY_WS : chars;
  const cps$T = Array.from(s);
  let i$T = 0, j$T = cps.length;
  if (left) while (i < j && set.includes(cps[i])) i++;
  if (right) while (j > i && set.includes(cps[j - 1])) j--;
  return cps.slice(i, j).join("");
}"""),

    "__py_strip": (("__py_strip_impl",), """\
function __py_strip(s$T, ...a$T) { return typeof s === "string" ? __py_strip_impl(s, a[0], true, true) : s.strip(...a); }"""),

    "__py_lstrip": (("__py_strip_impl",), """\
function __py_lstrip(s$T, ...a$T) { return typeof s === "string" ? __py_strip_impl(s, a[0], true, false) : s.lstrip(...a); }"""),

    "__py_rstrip": (("__py_strip_impl",), """\
function __py_rstrip(s$T, ...a$T) { return typeof s === "string" ? __py_strip_impl(s, a[0], false, true) : s.rstrip(...a); }"""),

    "__py_split": (("__PY_WS", "__py_err"), """\
function __py_split(s$T, ...a$T) {
  if (typeof s !== "string") return s.split(...a);
  const sep$T = (a[0] === undefined) ? null : a[0];
  const maxsplit$T = (a[1] === undefined || a[1] === null) ? -1 : a[1];
  if (sep === null) {
    const out$T = [];
    const n$T = s.length;
    let i$T = 0;
    for (;;) {
      while (i < n && __PY_WS.includes(s[i])) i++;
      if (i >= n) break;
      if (maxsplit >= 0 && out.length === maxsplit) { out.push(s.slice(i)); break; }
      let j$T = i;
      while (j < n && !__PY_WS.includes(s[j])) j++;
      out.push(s.slice(i, j));
      i = j;
    }
    return out;
  }
  if (typeof sep !== "string") throw __py_err("TypeError", "must be str or None");
  if (sep === "") throw __py_err("ValueError", "empty separator");
  const parts$T = s.split(sep);
  if (maxsplit >= 0 && parts.length > maxsplit + 1) {
    return parts.slice(0, maxsplit).concat([parts.slice(maxsplit).join(sep)]);
  }
  return parts;
}"""),

    "__py_typename": ((), """\
function __py_typename(v$T) {
  if (v === null || v === undefined) return "NoneType";
  if (typeof v === "boolean") return "bool";
  if (typeof v === "number") return Number.isInteger(v) ? "int" : "float";
  if (typeof v === "string") return "str";
  if (Array.isArray(v)) return "list";
  return (v.constructor && v.constructor.name) || typeof v;
}"""),

    "__py_join": (("__py_err", "__py_typename"), """\
function __py_join(sep$T, ...a$T) {
  if (typeof sep !== "string") return sep.join(...a);
  const xs$T = Array.from(a[0]);
  xs.forEach((x$T, i$T) => {
    if (typeof x !== "string") {
      throw __py_err("TypeError", "sequence item " + i + ": expected str instance, " + __py_typename(x) + " found");
    }
  });
  return xs.join(sep);
}"""),

    "__py_replace": ((), """\
function __py_replace(s$T, ...a$T) {
  if (typeof s !== "string") return s.replace(...a);
  const old$T = a[0], nw$T = a[1];
  let count$T = (a[2] === undefined || a[2] === null || a[2] < 0) ? Infinity : a[2];
  let out$T = "", k$T = 0;
  if (old === "") {
    for (const c of Array.from(s)) { if (k < count) { out += nw; k++; } out += c; }
    if (k < count) out += nw;
    return out;
  }
  let i$T = 0;
  while (k < count) {
    const j$T = s.indexOf(old, i);
    if (j < 0) break;
    out += s.slice(i, j) + nw;
    i = j + old.length;
    k++;
  }
  return out + s.slice(i);
}"""),

    "__py_tailmatch": (("__py_bounds",), """\
function __py_tailmatch(s$T, affix$T, start$T, end$T, atEnd$T) {
  const cps$T = Array.from(s);
  const [st, en] = __py_bounds(cps.length, start, end);
  const affixes$T = Array.isArray(affix) ? affix : [affix];
  for (const p of affixes) {
    if (en - st < Array.from(p).length) continue;
    const hay$T = cps.slice(st, en).join("");
    if (atEnd ? hay.endsWith(p) : hay.startsWith(p)) return true;
  }
  return false;
}"""),

    "__py_startswith": (("__py_tailmatch",), """\
function __py_startswith(s$T, ...a$T) { return typeof s === "string" ? __py_tailmatch(s, a[0], a[1], a[2], false) : s.startswith(...a); }"""),

    "__py_endswith": (("__py_tailmatch",), """\
function __py_endswith(s$T, ...a$T) { return typeof s === "string" ? __py_tailmatch(s, a[0], a[1], a[2], true) : s.endswith(...a); }"""),

    "__py_find_impl": (("__py_bounds",), """\
function __py_find_impl(s$T, sub$T, start$T, end$T) {
  const cps$T = Array.from(s);
  const [st, en] = __py_bounds(cps.length, start, end);
  if (en - st < Array.from(sub).length) return -1;
  const hay$T = cps.slice(st, en).join("");
  const i$T = hay.indexOf(sub);
  return i < 0 ? -1 : st + Array.from(hay.slice(0, i)).length;
}"""),

    "__py_find": (("__py_find_impl",), """\
function __py_find(s$T, ...a$T) { return typeof s === "string" ? __py_find_impl(s, a[0], a[1], a[2]) : s.find(...a); }"""),

    "__py_index": (("__py_find_impl", "__py_err"), """\
function __py_index(s$T, ...a$T) {
  if (typeof s === "string") {
    const i$T = __py_find_impl(s, a[0], a[1], a[2]);
    if (i < 0) throw __py_err("ValueError", "substring not found");
    return i;
  }
  if (Array.isArray(s) && a.length === 1) {
    const i$T = s.indexOf(a[0]);
    if (i < 0) throw __py_err("ValueError", String(a[0]) + " is not in list");
    return i;
  }
  return s.index(...a);
}"""),

    "__py_count": (("__py_bounds",), """\
function __py_count(s$T, ...a$T) {
  if (typeof s === "string") {
    const sub$T = a[0];
    const cps$T = Array.from(s);
    const [st, en] = __py_bounds(cps.length, a[1], a[2]);
    if (en - st < Array.from(sub).length) return 0;
    if (sub === "") return en - st + 1;
    return cps.slice(st, en).join("").split(sub).length - 1;
  }
  if (Array.isArray(s) && a.length === 1) return s.filter((x$T) => x === a[0]).length;
  return s.count(...a);
}"""),

    "__py_isdigit": ((), """\
const __PY_DIGIT_EXTRA$T = {DIGIT_EXTRA};
function __py_isdigit(s$T, ...a$T) {
  if (typeof s !== "string") return s.isdigit(...a);
  const cps$T = Array.from(s);
  return cps.length > 0 && cps.every((c$T) => /\\p{Nd}/u.test(c) || __PY_DIGIT_EXTRA.includes(c));
}"""),

    "__py_isdecimal": ((), """\
function __py_isdecimal(s$T, ...a$T) { return typeof s === "string" ? /^\\p{Nd}+$/u.test(s) : s.isdecimal(...a); }"""),

    "__py_isalpha": ((), """\
function __py_isalpha(s$T, ...a$T) { return typeof s === "string" ? /^\\p{L}+$/u.test(s) : s.isalpha(...a); }"""),

    "__py_isspace": (("__PY_WS",), """\
function __py_isspace(s$T, ...a$T) {
  if (typeof s !== "string") return s.isspace(...a);
  return s.length > 0 && Array.from(s).every((c$T) => __PY_WS.includes(c));
}"""),

    "__py_titlechar": ((), """\
const __PY_TITLE$T = {TITLE};
function __py_titlechar(c$T) { return Object.prototype.hasOwnProperty.call(__PY_TITLE, c) ? __PY_TITLE[c] : c.toUpperCase(); }"""),

    "__py_capitalize": (("__py_titlechar",), """\
function __py_capitalize(s$T, ...a$T) {
  if (typeof s !== "string") return s.capitalize(...a);
  const cps$T = Array.from(s);
  if (cps.length === 0) return "";
  // Lower-case the rest in context (Greek final sigma), as CPython does.
  return __py_titlechar(cps[0]) + s.toLowerCase().slice(cps[0].toLowerCase().length);
}"""),

    "__py_title": (("__py_titlechar",), """\
function __py_title(s$T, ...a$T) {
  if (typeof s !== "string") return s.title(...a);
  // CPython: a character is title-cased when the previous one is not cased,
  // otherwise lower-cased. Each run starts at an uncased boundary.
  const cps$T = Array.from(s);
  const cased$T = (c$T) => /\\p{Cased}/u.test(c);
  let out$T = "";
  let i$T = 0;
  while (i < cps.length) {
    let j$T = i + 1;
    while (j < cps.length && cased(cps[j - 1])) j++;
    const run$T = cps.slice(i, j).join("");
    out += __py_titlechar(cps[i]) + run.toLowerCase().slice(cps[i].toLowerCase().length);
    i = j;
  }
  return out;
}"""),

    "__py_float_repr": ((), """\
function __py_float_repr(x$T) {
  if (Number.isNaN(x)) return "nan";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  if (Number.isInteger(x)) return BigInt(x).toString();
  const [m, ex] = x.toExponential().split("e");
  const e$T = parseInt(ex, 10);
  const neg$T = m[0] === "-";
  const digits$T = m.replace("-", "").replace(".", "");
  let body$T;
  if (e < -4 || e >= 16) {
    body = digits[0] + (digits.length > 1 ? "." + digits.slice(1) : "") + "e" + (e < 0 ? "-" : "+") + String(Math.abs(e)).padStart(2, "0");
  } else if (e < 0) {
    body = "0." + "0".repeat(-e - 1) + digits;
  } else {
    body = digits.slice(0, e + 1) + "." + digits.slice(e + 1);
  }
  return (neg ? "-" : "") + body;
}"""),

    "__py_repr": (("__py_float_repr",), """\
function __py_repr(v$T)$R {
  if (typeof v === "string") {
    const q$T = v.includes("'") && !v.includes('"') ? '"' : "'";
    let out$T = q;
    for (const c of Array.from(v)) {
      const cp$T = c.codePointAt(0);
      if (c === q || c === "\\\\") out += "\\\\" + c;
      else if (c === "\\n") out += "\\\\n";
      else if (c === "\\r") out += "\\\\r";
      else if (c === "\\t") out += "\\\\t";
      else if (c !== " " && /[\\p{Cc}\\p{Cf}\\p{Cs}\\p{Co}\\p{Cn}\\p{Zl}\\p{Zp}\\p{Zs}]/u.test(c)) {
        out += cp < 0x100 ? "\\\\x" + cp.toString(16).padStart(2, "0")
          : cp < 0x10000 ? "\\\\u" + cp.toString(16).padStart(4, "0")
          : "\\\\U" + cp.toString(16).padStart(8, "0");
      } else out += c;
    }
    return out + q;
  }
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  if (typeof v === "number") return __py_float_repr(v);
  if (Array.isArray(v)) return "[" + v.map(__py_repr).join(", ") + "]";
  if (v instanceof Set) return v.size ? "{" + Array.from(v).map(__py_repr).join(", ") + "}" : "set()";
  if (v instanceof Map) return "{" + Array.from(v).map(([k, x]) => __py_repr(k) + ": " + __py_repr(x)).join(", ") + "}";
  if (typeof v === "object" && typeof v.__repr__ === "function") return v.__repr__();
  if (typeof v === "object" && Object.getPrototypeOf(v) === Object.prototype) {
    return "{" + Object.entries(v).map(([k, x]) => __py_repr(k) + ": " + __py_repr(x)).join(", ") + "}";
  }
  return String(v);
}"""),

    "__py_str": (("__py_repr",), """\
function __py_str(v$T) {
  if (typeof v === "string") return v;
  if (v !== null && typeof v === "object" && typeof v.__str__ === "function") return v.__str__();
  return __py_repr(v);
}"""),

    "__py_print": (("__py_str",), """\
function __py_print(args$T, sep$T, end$T) {
  const s$T = (sep === undefined || sep === null) ? " " : sep;
  const e$T = (end === undefined || end === null) ? "\\n" : end;
  const line$T = args.map(__py_str).join(s);
  if (e === "\\n") console.log(line);
  else if (Reflect.get(globalThis, "process")) Reflect.get(globalThis, "process").stdout.write(line + e);
  else throw new Error("print(end=...) needs a Node.js stdout");
}"""),

    "__py_format": (("__py_err", "__py_str"), """\
function __py_format(s$T, pos$T, kw$T) {
  if (typeof s !== "string") return s.format(...pos, ...(Object.keys(kw).length ? [kw] : []));
  let out$T = "", i$T = 0, auto$T = 0, mode$T = null;
  while (i < s.length) {
    const c$T = s[i];
    if (c === "{" && s[i + 1] === "{") { out += "{"; i += 2; continue; }
    if (c === "}" && s[i + 1] === "}") { out += "}"; i += 2; continue; }
    if (c === "}") throw __py_err("ValueError", "Single '}' encountered in format string");
    if (c !== "{") { out += c; i++; continue; }
    const close$T = s.indexOf("}", i + 1);
    if (close < 0) throw __py_err("ValueError", "expected '}' before end of string");
    const field$T = s.slice(i + 1, close);
    if (/[:!.\\[{]/.test(field)) {
      throw __py_err("NotImplementedError", "str.format: only {}, {0} and {name} fields are translated to JS, not {" + field + "}");
    }
    let v$T;
    if (field === "" || /^[0-9]+$/.test(field)) {
      const m$T = field === "" ? "auto" : "manual";
      if (mode !== null && mode !== m) {
        throw __py_err("ValueError", m === "auto"
          ? "cannot switch from manual field specification to automatic field numbering"
          : "cannot switch from automatic field numbering to manual field specification");
      }
      mode = m;
      const k$T = field === "" ? auto++ : parseInt(field, 10);
      if (k >= pos.length) throw __py_err("IndexError", "Replacement index " + k + " out of range for positional args tuple");
      v = pos[k];
    } else {
      if (!Object.prototype.hasOwnProperty.call(kw, field)) throw __py_err("KeyError", "'" + field + "'");
      v = kw[field];
    }
    out += __py_str(v);
    i = close + 1;
  }
  return out;
}"""),

    "__py_len": (("__py_err", "__py_typename"), """\
function __py_len(o$T) {
  if (typeof o === "string") return Array.from(o).length;
  if (Array.isArray(o) || o instanceof Uint8Array) return o.length;
  if (o instanceof Set || o instanceof Map) return o.size;
  if (o !== null && typeof o === "object") {
    if (typeof o.__len__ === "function") return o.__len__();
    if (Object.getPrototypeOf(o) === Object.prototype) return Object.keys(o).length;
  }
  throw __py_err("TypeError", "object of type '" + __py_typename(o) + "' has no len()");
}"""),
}

# Python str method -> (helper, positional parameter names for keyword args).
STR_METHODS: dict[str, tuple[str, tuple[str, ...]]] = {
    "upper": ("__py_upper", ()),
    "lower": ("__py_lower", ()),
    "strip": ("__py_strip", ("chars",)),
    "lstrip": ("__py_lstrip", ("chars",)),
    "rstrip": ("__py_rstrip", ("chars",)),
    "split": ("__py_split", ("sep", "maxsplit")),
    "join": ("__py_join", ("iterable",)),
    "replace": ("__py_replace", ("old", "new", "count")),
    "startswith": ("__py_startswith", ("prefix", "start", "end")),
    "endswith": ("__py_endswith", ("suffix", "start", "end")),
    "find": ("__py_find", ("sub", "start", "end")),
    "index": ("__py_index", ("sub", "start", "end")),
    "count": ("__py_count", ("sub", "start", "end")),
    "isdigit": ("__py_isdigit", ()),
    "isdecimal": ("__py_isdecimal", ()),
    "isalpha": ("__py_isalpha", ()),
    "isspace": ("__py_isspace", ()),
    "capitalize": ("__py_capitalize", ()),
    "title": ("__py_title", ()),
}


def prelude(used: set[str], type_suffix: str) -> str:
    """JS source for the helpers in ``used`` and their dependencies, each
    once, dependencies first, in a stable order."""
    order: list[str] = []

    def visit(name: str) -> None:
        if name in order:
            return
        for dep in _HELPERS[name][0]:
            visit(dep)
        order.append(name)

    for name in sorted(used):
        visit(name)
    out = []
    for name in order:
        src = _HELPERS[name][1].replace("$T", type_suffix).replace("$R", type_suffix and ": string")
        if "{" in src and any(k in src for k in ("{WS}", "{DIGIT_EXTRA}", "{TITLE}")):
            t = _tables()
            for key, val in t.items():
                src = src.replace("{" + key + "}", val)
        out.append(src)
    return "\n".join(out)
