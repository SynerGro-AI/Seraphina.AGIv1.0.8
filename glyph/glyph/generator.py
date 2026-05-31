"""Glyph Generator — compiles native .GL source files into executable Python.

.GL is Seraphina's first-class source format. Tiny, deterministic, line-based
syntax. Every .GL file transpiles to a Python module that runs under the
existing sandbox + identity context.

Syntax (v0.4):

    # comments start with '#'         (first line may be a shebang/comment)
    @glyph    <name>
    @version  <X.Y.Z>
    @runtime  octalang|python

    emit  <IDENT> = <literal>         # literal: int, float, "string", true, false, null

    invoke <fn> [kwargs ...]          # fn in allowlist
    require <other_glyph> <spec>      # advisory dep

    # v0.4 additions:
    when   <bool_expr> invoke <fn> [kwargs ...]
    signal <name> [kwargs ...]

Bool expr grammar (whitelist only):
    IDENT
    not IDENT
    IDENT == <literal>
    IDENT in (<literal>, <literal>, ...)
IDENT must refer to a prior `emit` in the same file.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


class GLSyntaxError(SyntaxError):
    pass


_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_STRING = re.compile(r'^"((?:[^"\\]|\\.)*)"$')
_ALLOWED_INVOKE = {"register_self", "assert_context"}

# Per-statement line patterns.
_DIRECTIVE_RE = re.compile(r"^(@glyph|@version|@runtime)\s+(\S+)\s*$")
_EMIT_RE = re.compile(r"^emit\s+([A-Za-z_]\w*)\s*=\s*(.+?)\s*$")
_INVOKE_RE = re.compile(r"^invoke\s+([A-Za-z_]\w*)(?:\s+(.+?))?\s*$")
_REQUIRE_RE = re.compile(r"^require\s+([A-Za-z_]\w*)\s+(\S.*)$")
_WHEN_RE = re.compile(
    r"^when\s+(.+?)\s+invoke\s+([A-Za-z_]\w*)(?:\s+(.+?))?\s*$"
)
_SIGNAL_RE = re.compile(r"^signal\s+([A-Za-z_]\w*)(?:\s+(.+?))?\s*$")
_EMOTION_RE = re.compile(r"^emotion(?:\s+(.+?))?\s*$")
# Token in a kwargs string: KEY=VALUE where VALUE is a number, bool/null, or "quoted string"
_KWARG_TOKEN_RE = re.compile(
    r'([A-Za-z_]\w*)\s*=\s*("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?)'
)

# Bool-expr forms (whitelist).
_BE_IDENT_RE = re.compile(r"^([A-Za-z_]\w*)$")
_BE_NOT_RE = re.compile(r"^not\s+([A-Za-z_]\w*)$")
_BE_EQ_RE = re.compile(r"^([A-Za-z_]\w*)\s*==\s*(.+)$")
_BE_IN_RE = re.compile(r"^([A-Za-z_]\w*)\s+in\s+\((.+)\)$")


@dataclass
class GLDocument:
    name: str = ""
    version: str = ""
    runtime: str = "octalang"
    emits: list[tuple[str, object]] = field(default_factory=list)
    invocations: list[tuple[str, dict]] = field(default_factory=list)
    requires: list[tuple[str, str]] = field(default_factory=list)
    # v0.4
    whens: list[tuple[tuple, str, dict]] = field(default_factory=list)
    signals: list[tuple[str, dict]] = field(default_factory=list)
    # v0.6 — emotional weights (joy/fear/curiosity/...). Validated at parse time.
    emotion: dict = field(default_factory=dict)
    # Body source order for non-emit statements: list of (kind, index-into-list)
    body_order: list[tuple[str, int]] = field(default_factory=list)


def _parse_literal(token: str) -> object:
    m = _STRING.match(token)
    if m:
        return m.group(1).encode("utf-8").decode("unicode_escape")
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "null":
        return None
    if _NUMBER.match(token):
        return float(token) if "." in token else int(token)
    raise GLSyntaxError(f"unsupported literal: {token!r}")


def _parse_kwargs(rest: str) -> dict:
    out: dict = {}
    pos = 0
    s = rest.strip()
    while pos < len(s):
        while pos < len(s) and s[pos].isspace():
            pos += 1
        if pos >= len(s):
            break
        m = _KWARG_TOKEN_RE.match(s, pos)
        if not m:
            raise GLSyntaxError(f"expected key=value at {s[pos:]!r}")
        out[m.group(1)] = _parse_literal(m.group(2))
        pos = m.end()
    return out


def _split_top_commas(s: str) -> list[str]:
    """Split on commas not inside double-quoted strings."""
    out: list[str] = []
    buf = ""
    in_str = False
    esc = False
    for ch in s:
        if esc:
            buf += ch
            esc = False
            continue
        if in_str:
            if ch == "\\":
                buf += ch
                esc = True
                continue
            if ch == '"':
                in_str = False
            buf += ch
            continue
        if ch == '"':
            in_str = True
            buf += ch
            continue
        if ch == ",":
            out.append(buf)
            buf = ""
            continue
        buf += ch
    out.append(buf)
    return [p for p in out if p.strip()]


def _parse_bool_expr(text: str, defined: set[str]) -> tuple:
    t = text.strip()
    m = _BE_IDENT_RE.match(t)
    if m:
        ident = m.group(1)
        if ident not in defined:
            raise GLSyntaxError(f"when references undefined emit: {ident!r}")
        return ("ident", ident)
    m = _BE_NOT_RE.match(t)
    if m:
        ident = m.group(1)
        if ident not in defined:
            raise GLSyntaxError(f"when references undefined emit: {ident!r}")
        return ("not", ident)
    m = _BE_IN_RE.match(t)
    if m:
        ident = m.group(1)
        if ident not in defined:
            raise GLSyntaxError(f"when references undefined emit: {ident!r}")
        parts = [_parse_literal(p.strip()) for p in _split_top_commas(m.group(2))]
        if not parts:
            raise GLSyntaxError(f"when 'in (...)' needs at least one literal: {text!r}")
        return ("in", ident, parts)
    m = _BE_EQ_RE.match(t)
    if m:
        ident = m.group(1)
        if ident not in defined:
            raise GLSyntaxError(f"when references undefined emit: {ident!r}")
        return ("eq", ident, _parse_literal(m.group(2).strip()))
    raise GLSyntaxError(f"unsupported when expression: {text!r}")


def parse(source: str) -> GLDocument:
    doc = GLDocument()
    defined_emits: set[str] = set()
    for lineno, raw in enumerate(source.splitlines(), 1):
        # Comment stripping handles shebang-style first lines (# @glyph foo, #!python, etc.)
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        m = _DIRECTIVE_RE.match(line)
        if m:
            head, val = m.group(1), m.group(2)
            if head == "@glyph":
                if not _IDENT.match(val):
                    raise GLSyntaxError(f"line {lineno}: bad glyph name {val!r}")
                doc.name = val
            elif head == "@version":
                if not _VERSION.match(val):
                    raise GLSyntaxError(f"line {lineno}: bad version {val!r}")
                doc.version = val
            elif head == "@runtime":
                if val not in {"octalang", "python"}:
                    raise GLSyntaxError(f"line {lineno}: bad runtime {val!r}")
                doc.runtime = val
            continue

        m = _EMIT_RE.match(line)
        if m:
            ident, value = m.group(1), m.group(2)
            try:
                doc.emits.append((ident, _parse_literal(value)))
            except GLSyntaxError as e:
                raise GLSyntaxError(f"line {lineno}: {e}") from None
            defined_emits.add(ident)
            continue

        # `when` MUST be tried before `invoke` (its tail contains the word "invoke").
        m = _WHEN_RE.match(line)
        if m:
            cond_text, fn, rest = m.group(1), m.group(2), m.group(3) or ""
            if fn not in _ALLOWED_INVOKE:
                raise GLSyntaxError(f"line {lineno}: when invoke {fn!r} not allowed")
            try:
                cond = _parse_bool_expr(cond_text, defined_emits)
                kwargs = _parse_kwargs(rest)
            except GLSyntaxError as e:
                raise GLSyntaxError(f"line {lineno}: {e}") from None
            doc.whens.append((cond, fn, kwargs))
            doc.body_order.append(("when", len(doc.whens) - 1))
            continue

        m = _INVOKE_RE.match(line)
        if m:
            fn, rest = m.group(1), m.group(2) or ""
            if fn not in _ALLOWED_INVOKE:
                raise GLSyntaxError(f"line {lineno}: invoke {fn!r} not allowed")
            try:
                doc.invocations.append((fn, _parse_kwargs(rest)))
            except GLSyntaxError as e:
                raise GLSyntaxError(f"line {lineno}: {e}") from None
            doc.body_order.append(("invoke", len(doc.invocations) - 1))
            continue

        m = _SIGNAL_RE.match(line)
        if m:
            name, rest = m.group(1), m.group(2) or ""
            try:
                kwargs = _parse_kwargs(rest)
            except GLSyntaxError as e:
                raise GLSyntaxError(f"line {lineno}: {e}") from None
            doc.signals.append((name, kwargs))
            doc.body_order.append(("signal", len(doc.signals) - 1))
            continue

        m = _EMOTION_RE.match(line)
        if m:
            rest = m.group(1) or ""
            try:
                kwargs = _parse_kwargs(rest)
            except GLSyntaxError as e:
                raise GLSyntaxError(f"line {lineno}: {e}") from None
            for k, v in kwargs.items():
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise GLSyntaxError(
                        f"line {lineno}: emotion {k!r} must be a number, got {v!r}")
                fv = float(v)
                if not (0.0 <= fv <= 1.0):
                    raise GLSyntaxError(
                        f"line {lineno}: emotion {k!r} must be in [0.0, 1.0], got {v!r}")
                doc.emotion[k] = fv
            continue

        m = _REQUIRE_RE.match(line)
        if m:
            doc.requires.append((m.group(1), m.group(2).strip()))
            doc.body_order.append(("require", len(doc.requires) - 1))
            continue

        head = line.split()[0]
        raise GLSyntaxError(f"line {lineno}: unknown statement {head!r}")
    return doc


_KWARG_ALIASES = {
    # .GL ergonomic name -> real glyph API kwarg
    "register_self": {"trust": "trust_delta"},
}


def _bridge_kwargs(fn: str, kwargs: dict, doc_name: str) -> dict:
    """Translate ergonomic .GL kwargs into the real glyph.<fn> signature."""
    aliases = _KWARG_ALIASES.get(fn, {})
    out = {aliases.get(k, k): v for k, v in kwargs.items()}
    if fn == "register_self" and "component" not in out:
        out = {"component": doc_name or "anonymous", **out}
    return out


def _cond_to_py(cond: tuple) -> str:
    kind = cond[0]
    if kind == "ident":
        return cond[1]
    if kind == "not":
        return f"(not {cond[1]})"
    if kind == "eq":
        return f"({cond[1]} == {cond[2]!r})"
    if kind == "in":
        items = ", ".join(repr(x) for x in cond[2])
        if len(cond[2]) == 1:
            return f"({cond[1]} in ({items},))"
        return f"({cond[1]} in ({items}))"
    raise GLSyntaxError(f"unknown cond kind: {kind!r}")


def transpile(doc: GLDocument) -> str:
    """Emit deterministic Python source from a parsed GLDocument."""
    lines: list[str] = [
        "# auto-generated by glyph.generator — do not edit",
        "import glyph",
        f"__gl_name__ = {doc.name!r}",
        f"__gl_version__ = {doc.version!r}",
        f"__gl_runtime__ = {doc.runtime!r}",
        f"__gl_requires__ = {doc.requires!r}",
        f"__gl_emotion__ = {doc.emotion!r}",
    ]
    # Emits bound first so they're available to any body statement.
    for ident, value in doc.emits:
        lines.append(f"{ident} = {value!r}")
    # Body statements in source order.
    for kind, idx in doc.body_order:
        if kind == "invoke":
            fn, kw = doc.invocations[idx]
            bridged = _bridge_kwargs(fn, kw, doc.name)
            kw_str = ", ".join(f"{k}={v!r}" for k, v in bridged.items())
            lines.append(f"glyph.{fn}({kw_str})")
        elif kind == "when":
            cond, fn, kw = doc.whens[idx]
            bridged = _bridge_kwargs(fn, kw, doc.name)
            kw_str = ", ".join(f"{k}={v!r}" for k, v in bridged.items())
            lines.append(f"if {_cond_to_py(cond)}: glyph.{fn}({kw_str})")
        elif kind == "signal":
            name, kw = doc.signals[idx]
            payload_parts = ", ".join(f"{k!r}: {v!r}" for k, v in sorted(kw.items()))
            lines.append(f"glyph.emit_signal({name!r}, {{{payload_parts}}})")
        elif kind == "require":
            # advisory metadata only; recorded in __gl_requires__ header.
            pass
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Canonical re-emit (used by `glyph fmt`).
# --------------------------------------------------------------------------- #

def _literal_to_gl(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        # json.dumps gives a properly-escaped double-quoted string —
        # exactly matches .GL string literal grammar.
        return json.dumps(v, ensure_ascii=False)
    raise GLSyntaxError(f"unrepresentable literal in .GL: {v!r}")


def _kwargs_to_gl(kwargs: dict) -> str:
    return " ".join(f"{k}={_literal_to_gl(v)}" for k, v in sorted(kwargs.items()))


def _cond_to_gl(cond: tuple) -> str:
    kind = cond[0]
    if kind == "ident":
        return cond[1]
    if kind == "not":
        return f"not {cond[1]}"
    if kind == "eq":
        return f"{cond[1]} == {_literal_to_gl(cond[2])}"
    if kind == "in":
        items = ", ".join(_literal_to_gl(x) for x in cond[2])
        return f"{cond[1]} in ({items})"
    raise GLSyntaxError(f"unknown cond kind: {kind!r}")


def format_gl(doc: GLDocument) -> str:
    """Re-emit a parsed GLDocument in canonical form. Idempotent."""
    lines: list[str] = []
    if doc.name:
        lines.append(f"@glyph {doc.name}")
    if doc.version:
        lines.append(f"@version {doc.version}")
    if doc.runtime:
        lines.append(f"@runtime {doc.runtime}")

    if doc.emits:
        if lines:
            lines.append("")
        for ident, value in doc.emits:
            lines.append(f"emit {ident} = {_literal_to_gl(value)}")

    if doc.emotion:
        if lines:
            lines.append("")
        kws = " ".join(f"{k}={_literal_to_gl(v)}" for k, v in sorted(doc.emotion.items()))
        lines.append(f"emotion {kws}")

    if doc.body_order:
        if lines:
            lines.append("")
        for kind, idx in doc.body_order:
            if kind == "invoke":
                fn, kw = doc.invocations[idx]
                tail = (" " + _kwargs_to_gl(kw)) if kw else ""
                lines.append(f"invoke {fn}{tail}")
            elif kind == "when":
                cond, fn, kw = doc.whens[idx]
                tail = (" " + _kwargs_to_gl(kw)) if kw else ""
                lines.append(f"when {_cond_to_gl(cond)} invoke {fn}{tail}")
            elif kind == "signal":
                name, kw = doc.signals[idx]
                tail = (" " + _kwargs_to_gl(kw)) if kw else ""
                lines.append(f"signal {name}{tail}")
            elif kind == "require":
                name, spec = doc.requires[idx]
                lines.append(f"require {name} {spec}")
    return "\n".join(lines) + "\n"


def compile_file(src: str | Path, out: str | Path) -> Path:
    """Read a .GL file, parse + transpile, write the .py companion. Returns out path."""
    src_p, out_p = Path(src), Path(out)
    doc = parse(src_p.read_text(encoding="utf-8"))
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(transpile(doc), encoding="utf-8")
    return out_p


def compile_tree(code_dir: str | Path) -> list[Path]:
    """Compile every .GL under `code_dir` to a sibling .py file. Returns generated paths."""
    root = Path(code_dir)
    generated: list[Path] = []
    for gl in sorted(root.rglob("*.GL")):
        py = gl.with_suffix(".py")
        compile_file(gl, py)
        generated.append(py)
    return generated
