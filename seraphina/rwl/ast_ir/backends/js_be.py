"""JavaScript code generator (RWAST → JavaScript ES2020+).

Operator / builtin mapping table (Python → JS):
    BoolOp  and→&&  or→||
    UnaryOp not→!
    Compare ==→===  !=→!==  is→===  is not→!==
    BinOp // → Math.floor(lhs / rhs)   ** stays **
    None→null  True→true  False→false
    def→function  class→class
    for x in y → for (const x of y)
    f-strings → template literals  `${...}`
    print(...)  → console.log(...)
    len(x)      → x.length    (1-arg only)
    str/int/float/abs/max/min/round → String/parseInt/parseFloat/Math.abs/Math.max/Math.min/Math.round
"""
from __future__ import annotations

from ..nodes import Node, NodeType

_INDENT = "  "   # 2-space JS convention

# Operators preserved verbatim
_BINOP_SAME = {"+", "-", "*", "/", "%", "<<", ">>", "|", "&", "^", "@", "**"}
_AUGOP_MAP = {
    "+=": "+=", "-=": "-=", "*=": "*=", "/=": "/=",
    "%=": "%=", "**=": "**=", "<<=": "<<=", ">>=": ">>=",
    "|=": "|=", "&=": "&=", "^=": "^=", "//=": None,  # special-cased
    "@=": None,
}
_CMPOP_MAP = {
    "==": "===", "!=": "!==", "<": "<", "<=": "<=", ">": ">", ">=": ">=",
    "is": "===", "is not": "!==", "in": None, "not in": None,  # special
}
_BOOLOP_MAP = {"and": "&&", "or": "||"}
_BUILTINS = {
    "print": "console.log",
    "str": "String",
    "int": "parseInt",
    "float": "parseFloat",
    "abs": "Math.abs",
    "max": "Math.max",
    "min": "Math.min",
    "round": "Math.round",
    "sorted": "Array.from",
    "list": "Array.from",
    "dict": "Object.fromEntries",
    "set": "new Set",
    "isinstance": None,   # best-effort fallback
}


class JSBackend:
    """Generates JavaScript source from an RWAST root node."""

    lang = "js"
    _type_suffix = ""    # TS subclass overrides to ": any"

    def __init__(self, indent: str = _INDENT):
        self._ind = indent

    def emit(self, node: Node, depth: int = 0) -> str:
        method = f"_emit_{node.kind.name.lower()}"
        fn = getattr(self, method, self._emit_unknown)
        return fn(node, depth)

    def _pad(self, depth: int) -> str:
        return self._ind * depth

    def _semi(self) -> str:
        return ";"

    def _emit_unknown(self, node: Node, depth: int) -> str:
        raw = node.data.get("raw", f"/* unknown: {node.kind.name} */")
        return self._pad(depth) + raw + self._semi()

    def _emit_module(self, node: Node, depth: int) -> str:
        parts = [self.emit(c, depth) for c in node.children]
        return "\n".join(parts)

    def _emit_block(self, node: Node, depth: int) -> str:
        if not node.children:
            return ""
        return "\n".join(self.emit(c, depth) for c in node.children)

    # --- imports ---
    def _emit_import(self, node: Node, depth: int) -> str:
        parts = []
        for name, alias in node.data.get("names", []):
            parts.append(f"{name} as {alias}" if alias else name)
        joined = ", ".join(parts)
        return self._pad(depth) + f"import {{ {joined} }}{self._semi()}"

    def _emit_import_from(self, node: Node, depth: int) -> str:
        module = node.data.get("module", "")
        parts = []
        for name, alias in node.data.get("names", []):
            parts.append(f"{name} as {alias}" if alias else name)
        joined = ", ".join(parts)
        return self._pad(depth) + f'import {{ {joined} }} from "{module}"{self._semi()}'

    def _emit_export(self, node: Node, depth: int) -> str:
        if node.children:
            inner = self.emit(node.children[0], 0)
            return self._pad(depth) + f"export {inner}"
        return ""

    # --- functions ---
    def _func_param(self, p: Node) -> str:
        name = p.data.get("name", "_")
        kind = p.data.get("kind", "pos")
        default = p.children[0] if p.children else None
        ts_ann = self._type_suffix  # "" for JS, ": any" for TS
        if kind == "var":
            return f"...{name}"
        if kind == "kwvar":
            return f"kwargs = {{}}"
        default_str = f" = {self.emit(default, 0)}" if default else ""
        return f"{name}{ts_ann}{default_str}"

    def _emit_function_def(self, node: Node, depth: int) -> str:
        return self._emit_func_common(node, depth, async_kw="")

    def _emit_async_func(self, node: Node, depth: int) -> str:
        return self._emit_func_common(node, depth, async_kw="async ")

    def _emit_func_common(self, node: Node, depth: int, async_kw: str) -> str:
        name = node.data.get("name", "_fn")
        params = node.all_children(NodeType.PARAM)
        body_node = node.first_child(NodeType.BLOCK)
        decorators = node.all_children(NodeType.DECORATOR)
        param_strs = [self._func_param(p) for p in params]
        ret_ann = self._return_type_ann(node)
        dec_comments = [self._pad(depth) + f"// @{self.emit(d.children[0], 0)}"
                        for d in decorators if d.children]
        header = (f"{self._pad(depth)}{async_kw}function {name}"
                  f"({', '.join(param_strs)}){ret_ann} {{")
        body_str = (self._emit_block(body_node, depth + 1) + "\n"
                    if body_node and body_node.children else "")
        footer = self._pad(depth) + "}"
        return "\n".join(dec_comments + [header] + ([body_str.rstrip()] if body_str else []) + [footer])

    def _return_type_ann(self, node: Node) -> str:
        return ""   # JS: no annotation; TS overrides

    def _emit_class_def(self, node: Node, depth: int) -> str:
        name = node.data.get("name", "_Cls")
        body_node = node.first_child(NodeType.BLOCK)
        bases = [c for c in node.children
                 if c.kind not in (NodeType.BLOCK, NodeType.DECORATOR)]
        ext = f" extends {', '.join(self.emit(b, 0) for b in bases)}" if bases else ""
        header = f"{self._pad(depth)}class {name}{ext} {{"
        body_str = (self._emit_block(body_node, depth + 1) + "\n"
                    if body_node and body_node.children else "")
        footer = self._pad(depth) + "}"
        return "\n".join([header] + ([body_str.rstrip()] if body_str else []) + [footer])

    # --- assignment ---
    def _emit_assign(self, node: Node, depth: int) -> str:
        if len(node.children) == 1:
            return self._pad(depth) + f"let {self.emit(node.children[0], 0)}{self._semi()}"
        *targets, value = node.children
        target_strs = [self.emit(t, 0) for t in targets]
        value_str = self.emit(value, 0)
        # First assignment: let; subsequent chained: just =
        decl = f"let {target_strs[0]}"
        if len(target_strs) == 1:
            return self._pad(depth) + f"{decl} = {value_str}{self._semi()}"
        # Multiple targets: a = b = val → let b = val; let a = b;
        lines = [self._pad(depth) + f"let {target_strs[-1]} = {value_str}{self._semi()}"]
        for t in reversed(target_strs[:-1]):
            lines.append(self._pad(depth) + f"let {t} = {target_strs[-1]}{self._semi()}")
        return "\n".join(lines)

    def _emit_aug_assign(self, node: Node, depth: int) -> str:
        op = node.data.get("op", "+=")
        target, value = node.children[0], node.children[1]
        js_op = _AUGOP_MAP.get(op)
        if js_op is None:
            # Floor division augmented: x //= y → x = Math.floor(x / y)
            t = self.emit(target, 0)
            v = self.emit(value, 0)
            return self._pad(depth) + f"{t} = Math.floor({t} / {v}){self._semi()}"
        return self._pad(depth) + f"{self.emit(target, 0)} {js_op} {self.emit(value, 0)}{self._semi()}"

    # --- control flow ---
    def _emit_return(self, node: Node, depth: int) -> str:
        if node.children:
            return self._pad(depth) + f"return {self.emit(node.children[0], 0)}{self._semi()}"
        return self._pad(depth) + f"return{self._semi()}"

    def _emit_if(self, node: Node, depth: int) -> str:
        test, body, orelse = node.children[0], node.children[1], node.children[2]
        lines = [f"{self._pad(depth)}if ({self.emit(test, 0)}) {{",
                 self._emit_block(body, depth + 1),
                 self._pad(depth) + "}"]
        if orelse.children:
            if len(orelse.children) == 1 and orelse.children[0].kind == NodeType.IF:
                inner = self._emit_if(orelse.children[0], depth)
                last_close = lines.pop()
                lines[-1] = lines[-1]  # keep
                lines.append(self._pad(depth) + "} else " + inner.lstrip())
            else:
                lines[-1] = self._pad(depth) + "} else {"
                lines.append(self._emit_block(orelse, depth + 1))
                lines.append(self._pad(depth) + "}")
        return "\n".join(l for l in lines if l is not None)

    def _emit_while(self, node: Node, depth: int) -> str:
        test, body = node.children[0], node.children[1]
        return "\n".join([f"{self._pad(depth)}while ({self.emit(test, 0)}) {{",
                          self._emit_block(body, depth + 1),
                          self._pad(depth) + "}"])

    def _emit_for(self, node: Node, depth: int) -> str:
        target, iter_, body = node.children[0], node.children[1], node.children[2]
        return "\n".join([
            f"{self._pad(depth)}for (const {self.emit(target, 0)} of {self.emit(iter_, 0)}) {{",
            self._emit_block(body, depth + 1),
            self._pad(depth) + "}"
        ])

    def _emit_break(self, node: Node, depth: int) -> str:
        return self._pad(depth) + f"break{self._semi()}"

    def _emit_continue(self, node: Node, depth: int) -> str:
        return self._pad(depth) + f"continue{self._semi()}"

    def _emit_pass(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "// pass"

    def _emit_raise(self, node: Node, depth: int) -> str:
        if not node.children:
            return self._pad(depth) + f"throw new Error(){self._semi()}"
        exc = self.emit(node.children[0], 0)
        return self._pad(depth) + f"throw {exc}{self._semi()}"

    def _emit_try(self, node: Node, depth: int) -> str:
        body = node.children[0]
        handlers = [c for c in node.children[1:] if c.kind == NodeType.EXCEPT_CLAUSE]
        rest = [c for c in node.children[1:] if c.kind == NodeType.BLOCK]
        finally_block = rest[1] if len(rest) >= 2 else None
        lines = [f"{self._pad(depth)}try {{",
                 self._emit_block(body, depth + 1),
                 self._pad(depth) + "}"]
        for h in handlers:
            lines.extend(self._emit_except_clause_js(h, depth))
        if finally_block and finally_block.children:
            lines += [f"{self._pad(depth)} finally {{",
                      self._emit_block(finally_block, depth + 1),
                      self._pad(depth) + "}"]
        return "\n".join(lines)

    def _emit_except_clause_js(self, node: Node, depth: int) -> list[str]:
        body = node.children[1]
        name = node.data.get("name") or "e"
        return [f"{self._pad(depth)} catch ({name}) {{",
                self._emit_block(body, depth + 1),
                self._pad(depth) + "}"]

    def _emit_except_clause(self, node: Node, depth: int) -> str:
        return "\n".join(self._emit_except_clause_js(node, depth))

    def _emit_with(self, node: Node, depth: int) -> str:
        body = node.children[-1]
        return "\n".join([f"{self._pad(depth)}{{  // with",
                          self._emit_block(body, depth + 1),
                          self._pad(depth) + "}"])

    def _emit_assert(self, node: Node, depth: int) -> str:
        test = self.emit(node.children[0], 0)
        msg = (f", {self.emit(node.children[1], 0)}"
               if len(node.children) > 1 else f', "Assertion failed"')
        return self._pad(depth) + f"console.assert({test}{msg}){self._semi()}"

    def _emit_delete(self, node: Node, depth: int) -> str:
        lines = [self._pad(depth) + f"delete {self.emit(c, 0)}{self._semi()}"
                 for c in node.children]
        return "\n".join(lines)

    def _emit_global_stmt(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "// global " + ", ".join(node.data.get("names", []))

    def _emit_nonlocal_stmt(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "// nonlocal " + ", ".join(node.data.get("names", []))

    def _emit_expr_stmt(self, node: Node, depth: int) -> str:
        if node.data.get("raw"):
            return self._pad(depth) + node.data["raw"]
        if node.children:
            return self._pad(depth) + self.emit(node.children[0], 0) + self._semi()
        return ""

    # --- expressions ---
    def _emit_call(self, node: Node, depth: int) -> str:
        func_node = node.children[0]
        args_nodes = node.children[1:]
        # Handle len(x) → x.length
        if func_node.kind == NodeType.NAME and func_node.data.get("id") == "len":
            positional = [c for c in args_nodes if c.kind != NodeType.KWARG]
            if len(positional) == 1:
                return self.emit(positional[0], 0) + ".length"
        func_str = self._map_builtin(func_node)
        args: list[str] = []
        for c in args_nodes:
            if c.kind == NodeType.KWARG:
                key = c.data.get("key")
                val = self.emit(c.children[0], 0) if c.children else "undefined"
                args.append(f"...{val}" if key is None else val)
            elif c.kind == NodeType.STARRED:
                args.append(f"...{self.emit(c.children[0], 0)}" if c.children else "...")
            else:
                args.append(self.emit(c, 0))
        return f"{func_str}({', '.join(args)})"

    def _map_builtin(self, func_node: Node) -> str:
        if func_node.kind == NodeType.NAME:
            name = func_node.data.get("id", "")
            if name in _BUILTINS:
                mapped = _BUILTINS[name]
                return mapped if mapped is not None else name
        return self.emit(func_node, 0)

    def _emit_bin_op(self, node: Node, depth: int) -> str:
        op = node.data.get("op", "+")
        left, right = node.children[0], node.children[1]
        ls = self.emit(left, 0)
        rs = self.emit(right, 0)
        if op == "//":
            return f"Math.floor({ls} / {rs})"
        js_op = op  # ** and others stay as-is
        return f"({ls} {js_op} {rs})"

    def _emit_unary_op(self, node: Node, depth: int) -> str:
        op = node.data.get("op", "-")
        operand = self.emit(node.children[0], 0)
        if op == "not":
            return f"!({operand})"
        if op == "~":
            return f"~({operand})"
        return f"{op}{operand}"

    def _emit_compare(self, node: Node, depth: int) -> str:
        ops = node.data.get("ops", ["=="])
        children = node.children
        left = self.emit(children[0], 0)
        parts: list[str] = []
        for i, op in enumerate(ops):
            comp = self.emit(children[i + 1], 0)
            js_op = _CMPOP_MAP.get(op)
            if op == "in":
                parts.append(f"{comp}.includes({left})")
            elif op == "not in":
                parts.append(f"!{comp}.includes({left})")
            else:
                parts.append(f"{left} {js_op} {comp}")
            left = comp
        return " && ".join(parts) if len(parts) > 1 else parts[0]

    def _emit_bool_op(self, node: Node, depth: int) -> str:
        op = _BOOLOP_MAP.get(node.data.get("op", "and"), "&&")
        return f" {op} ".join(f"({self.emit(c, 0)})" for c in node.children)

    def _emit_ternary(self, node: Node, depth: int) -> str:
        test, body, orelse = node.children
        return f"({self.emit(test, 0)} ? {self.emit(body, 0)} : {self.emit(orelse, 0)})"

    def _emit_lambda(self, node: Node, depth: int) -> str:
        body = node.children[-1]
        params = node.children[:-1]
        param_str = ", ".join(self._func_param(p) for p in params)
        return f"({param_str}) => {self.emit(body, 0)}"

    def _emit_arrow_func(self, node: Node, depth: int) -> str:
        return self._emit_lambda(node, depth)

    def _emit_yield(self, node: Node, depth: int) -> str:
        from_yield = node.data.get("from", False)
        kw = "yield*" if from_yield else "yield"
        val = f" {self.emit(node.children[0], 0)}" if node.children else ""
        return self._pad(depth) + f"{kw}{val}{self._semi()}"

    def _emit_await(self, node: Node, depth: int) -> str:
        return f"await {self.emit(node.children[0], 0)}"

    def _emit_name(self, node: Node, depth: int) -> str:
        name = node.data.get("id", "_")
        if name == "None":
            return "null"
        if name == "True":
            return "true"
        if name == "False":
            return "false"
        return name

    def _emit_const(self, node: Node, depth: int) -> str:
        t = node.data.get("type", "none")
        v = node.data.get("value")
        if t == "none":
            return "null"
        if t == "bool":
            return "true" if v else "false"
        if t == "str":
            # Use JSON encoding for safe JS string literal
            import json
            return json.dumps(str(v))
        if t == "bytes":
            data = bytes(v) if isinstance(v, list) else v
            arr = ", ".join(str(b) for b in data)
            return f"new Uint8Array([{arr}])"
        return repr(v)

    def _emit_attr(self, node: Node, depth: int) -> str:
        obj = self.emit(node.children[0], 0)
        return f"{obj}.{node.data.get('attr', '_')}"

    def _emit_subscript(self, node: Node, depth: int) -> str:
        obj = self.emit(node.children[0], 0)
        idx = self.emit(node.children[1], 0)
        return f"{obj}[{idx}]"

    def _emit_slice(self, node: Node, depth: int) -> str:
        lo = "" if node.children[0].kind == NodeType.PASS else self.emit(node.children[0], 0)
        hi = "" if node.children[1].kind == NodeType.PASS else self.emit(node.children[1], 0)
        # JS: array.slice(lo, hi) — step not directly supported
        lo_s = lo or "0"
        hi_s = hi if hi else ""
        return f"/* slice({lo_s}, {hi_s}) */"

    def _emit_starred(self, node: Node, depth: int) -> str:
        return f"...{self.emit(node.children[0], 0)}" if node.children else "..."

    def _emit_spread(self, node: Node, depth: int) -> str:
        return f"...{self.emit(node.children[0], 0)}" if node.children else "..."

    def _emit_list_lit(self, node: Node, depth: int) -> str:
        return "[" + ", ".join(self.emit(c, 0) for c in node.children) + "]"

    def _emit_tuple_lit(self, node: Node, depth: int) -> str:
        return "[" + ", ".join(self.emit(c, 0) for c in node.children) + "]"

    def _emit_set_lit(self, node: Node, depth: int) -> str:
        items = ", ".join(self.emit(c, 0) for c in node.children)
        return f"new Set([{items}])"

    def _emit_dict_lit(self, node: Node, depth: int) -> str:
        pairs: list[str] = []
        children = node.children
        for i in range(0, len(children) - 1, 2):
            k, v = children[i], children[i + 1]
            if k.kind == NodeType.STARRED:
                pairs.append(f"...{self.emit(v, 0)}")
            else:
                key_str = self.emit(k, 0)
                pairs.append(f"{key_str}: {self.emit(v, 0)}")
        return "{" + ", ".join(pairs) + "}"

    def _emit_template_str(self, node: Node, depth: int) -> str:
        parts: list[str] = []
        for c in node.children:
            if c.kind == NodeType.CONST and c.data.get("type") == "str":
                raw = c.data.get("value", "")
                raw = raw.replace("`", "\\`").replace("\\", "\\\\")
                raw = raw.replace("${", "\\${")
                parts.append(raw)
            else:
                parts.append("${" + self.emit(c, 0) + "}")
        return "`" + "".join(parts) + "`"

    def _emit_comprehension(self, node: Node, depth: int) -> str:
        kind = node.data.get("kind", "list")
        children = node.children[:]
        if kind == "dict":
            key_node = children.pop(0)
            val_node = children.pop(0)
        else:
            elt_node = children.pop(0)
        clauses: list[tuple[str, str, str]] = []  # (target, iter, conds)
        for c in children:
            if c.kind == NodeType.FOR:
                target = self.emit(c.children[0], 0)
                iter_ = self.emit(c.children[1], 0)
                clauses.append((target, iter_, ""))
            elif c.kind == NodeType.IF and c.data.get("comp"):
                cond = self.emit(c.children[0], 0)
                if clauses:
                    t, it, existing = clauses[-1]
                    clauses[-1] = (t, it, f"{existing} && {cond}" if existing else cond)
        if not clauses:
            if kind == "dict":
                return "({})  /* dict comp */"
            return "[/* comp */]"
        target, iter_, cond = clauses[0]
        if kind == "list":
            base = f"Array.from({iter_})"
            if cond:
                base += f".filter(({target}) => {cond})"
            return base + f".map(({target}) => {self.emit(elt_node, 0)})"
        if kind == "set":
            base = f"new Set(Array.from({iter_})"
            if cond:
                base += f".filter(({target}) => {cond})"
            return base + f".map(({target}) => {self.emit(elt_node, 0)}))"
        if kind == "dict":
            base = f"Object.fromEntries(Array.from({iter_})"
            if cond:
                base += f".filter(({target}) => {cond})"
            return (base + f".map(({target}) => "
                    f"[{self.emit(key_node, 0)}, {self.emit(val_node, 0)}]))")
        # generator
        base = f"(function*() {{ for (const {target} of {iter_}) {{"
        if cond:
            base += f" if ({cond}) {{"
        base += f" yield {self.emit(elt_node, 0)};"
        if cond:
            base += " }"
        base += " } })()"
        return base


def emit_js(root: Node) -> str:
    return JSBackend().emit(root)
