"""Python code generator (RWAST → Python source).

Generates clean, readable Python 3.9+ from a RWAST tree.
Used both for Python→Python round-trips and as a reference backend.
"""
from __future__ import annotations

from ..nodes import Node, NodeType

_INDENT = "    "

# Python operator precedence (higher = tighter binding)
_PREC: dict[str, int] = {
    "**": 12, "~": 11, "not": 3,
    "*": 10, "/": 10, "//": 10, "%": 10, "@": 10,
    "+": 9, "-": 9, "<<": 8, ">>": 8, "&": 7, "^": 6, "|": 5,
    "==": 4, "!=": 4, "<": 4, "<=": 4, ">": 4, ">=": 4,
    "is": 4, "is not": 4, "in": 4, "not in": 4,
    "and": 2, "or": 1,
}


def _needs_parens(node: Node, parent_op: str) -> bool:
    if node.kind == NodeType.BIN_OP:
        op = node.data.get("op", "+")
        return _PREC.get(op, 0) < _PREC.get(parent_op, 0)
    if node.kind in (NodeType.BOOL_OP, NodeType.COMPARE, NodeType.TERNARY):
        return True
    return False


class PythonBackend:
    def __init__(self, indent: str = _INDENT):
        self._ind = indent

    def emit(self, node: Node, depth: int = 0) -> str:
        method = f"_emit_{node.kind.name.lower()}"
        fn = getattr(self, method, self._emit_unknown)
        return fn(node, depth)

    def _pad(self, depth: int) -> str:
        return self._ind * depth

    def _emit_unknown(self, node: Node, depth: int) -> str:
        raw = node.data.get("raw", f"# unknown: {node.kind.name}")
        return self._pad(depth) + raw

    def _emit_module(self, node: Node, depth: int) -> str:
        return "\n".join(self.emit(c, depth) for c in node.children)

    def _emit_block(self, node: Node, depth: int) -> str:
        if not node.children:
            return self._pad(depth) + "pass"
        return "\n".join(self.emit(c, depth) for c in node.children)

    # --- imports ---
    def _emit_import(self, node: Node, depth: int) -> str:
        parts = []
        for name, alias in node.data.get("names", []):
            parts.append(f"{name} as {alias}" if alias else name)
        return self._pad(depth) + "import " + ", ".join(parts)

    def _emit_import_from(self, node: Node, depth: int) -> str:
        module = node.data.get("module", "")
        level = node.data.get("level", 0)
        dots = "." * level
        parts = []
        for name, alias in node.data.get("names", []):
            parts.append(f"{name} as {alias}" if alias else name)
        names_str = ", ".join(parts)
        return self._pad(depth) + f"from {dots}{module} import {names_str}"

    # --- functions / classes ---
    def _emit_function_def(self, node: Node, depth: int) -> str:
        return self._func(node, depth, "def")

    def _emit_async_func(self, node: Node, depth: int) -> str:
        return self._func(node, depth, "async def")

    def _func(self, node: Node, depth: int, keyword: str) -> str:
        name = node.data.get("name", "_fn")
        returns = node.data.get("returns")
        params = node.all_children(NodeType.PARAM)
        body_node = node.first_child(NodeType.BLOCK)
        decorators = node.all_children(NodeType.DECORATOR)
        dec_lines = [self._pad(depth) + "@" + self.emit(d.children[0], 0)
                     for d in decorators if d.children]
        param_strs = [self._param_str(p) for p in params]
        ret = f" -> {returns}" if returns else ""
        sig = f"{self._pad(depth)}{keyword} {name}({', '.join(param_strs)}){ret}:"
        body_str = (self._emit_block(body_node, depth + 1)
                    if body_node else self._pad(depth + 1) + "pass")
        return "\n".join(dec_lines + [sig, body_str])

    def _param_str(self, node: Node) -> str:
        name = node.data.get("name", "_")
        kind = node.data.get("kind", "pos")
        ann = node.data.get("annotation")
        default = node.children[0] if node.children else None
        prefix = ""
        if kind == "var":
            prefix = "*"
        elif kind == "kwvar":
            prefix = "**"
        ann_str = f": {ann}" if ann else ""
        default_str = f" = {self.emit(default, 0)}" if default else ""
        return f"{prefix}{name}{ann_str}{default_str}"

    def _emit_class_def(self, node: Node, depth: int) -> str:
        name = node.data.get("name", "_Cls")
        body_node = node.first_child(NodeType.BLOCK)
        decorators = node.all_children(NodeType.DECORATOR)
        bases = [c for c in node.children
                 if c.kind not in (NodeType.BLOCK, NodeType.DECORATOR)]
        dec_lines = [self._pad(depth) + "@" + self.emit(d.children[0], 0)
                     for d in decorators if d.children]
        base_str = f"({', '.join(self.emit(b, 0) for b in bases)})" if bases else ""
        header = f"{self._pad(depth)}class {name}{base_str}:"
        body_str = (self._emit_block(body_node, depth + 1)
                    if body_node else self._pad(depth + 1) + "pass")
        return "\n".join(dec_lines + [header, body_str])

    # --- assignment ---
    def _emit_assign(self, node: Node, depth: int) -> str:
        ann = node.data.get("annotation")
        if len(node.children) == 1:
            target = self.emit(node.children[0], 0)
            ann_str = f": {ann}" if ann else ""
            return self._pad(depth) + f"{target}{ann_str}"
        *targets, value = node.children
        target_str = " = ".join(self.emit(t, 0) for t in targets)
        ann_str = f": {ann}" if ann else ""
        return self._pad(depth) + f"{target_str}{ann_str} = {self.emit(value, 0)}"

    def _emit_aug_assign(self, node: Node, depth: int) -> str:
        op = node.data.get("op", "+=")
        target, value = node.children[0], node.children[1]
        return self._pad(depth) + f"{self.emit(target, 0)} {op} {self.emit(value, 0)}"

    # --- control flow ---
    def _emit_return(self, node: Node, depth: int) -> str:
        if node.children:
            return self._pad(depth) + f"return {self.emit(node.children[0], 0)}"
        return self._pad(depth) + "return"

    def _emit_if(self, node: Node, depth: int) -> str:
        test, body, orelse = node.children[0], node.children[1], node.children[2]
        lines = [f"{self._pad(depth)}if {self.emit(test, 0)}:",
                 self._emit_block(body, depth + 1)]
        if orelse.children:
            # elif flattening: if orelse has a single IF child
            if (len(orelse.children) == 1 and orelse.children[0].kind == NodeType.IF):
                inner = orelse.children[0]
                inner_str = self._emit_if(inner, depth)
                lines.append(self._pad(depth) + "el" + inner_str.lstrip())
            else:
                lines.append(f"{self._pad(depth)}else:")
                lines.append(self._emit_block(orelse, depth + 1))
        return "\n".join(lines)

    def _emit_while(self, node: Node, depth: int) -> str:
        test, body = node.children[0], node.children[1]
        return "\n".join([f"{self._pad(depth)}while {self.emit(test, 0)}:",
                          self._emit_block(body, depth + 1)])

    def _emit_for(self, node: Node, depth: int) -> str:
        target, iter_, body = node.children[0], node.children[1], node.children[2]
        return "\n".join([
            f"{self._pad(depth)}for {self.emit(target, 0)} in {self.emit(iter_, 0)}:",
            self._emit_block(body, depth + 1)
        ])

    def _emit_break(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "break"

    def _emit_continue(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "continue"

    def _emit_pass(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "pass"

    def _emit_raise(self, node: Node, depth: int) -> str:
        if not node.children:
            return self._pad(depth) + "raise"
        has_cause = node.data.get("cause", False)
        if has_cause and len(node.children) >= 2:
            return self._pad(depth) + (f"raise {self.emit(node.children[0], 0)}"
                                        f" from {self.emit(node.children[1], 0)}")
        return self._pad(depth) + f"raise {self.emit(node.children[0], 0)}"

    def _emit_try(self, node: Node, depth: int) -> str:
        body = node.children[0]
        handlers = [c for c in node.children[1:] if c.kind == NodeType.EXCEPT_CLAUSE]
        rest = [c for c in node.children[1:] if c.kind == NodeType.BLOCK]
        else_block = rest[0] if len(rest) >= 1 else None
        finally_block = rest[1] if len(rest) >= 2 else None
        lines = [f"{self._pad(depth)}try:", self._emit_block(body, depth + 1)]
        for h in handlers:
            lines.append(self._emit_except_clause(h, depth))
        if else_block and else_block.children:
            lines += [f"{self._pad(depth)}else:", self._emit_block(else_block, depth + 1)]
        if finally_block and finally_block.children:
            lines += [f"{self._pad(depth)}finally:", self._emit_block(finally_block, depth + 1)]
        return "\n".join(lines)

    def _emit_except_clause(self, node: Node, depth: int) -> str:
        type_node, body = node.children[0], node.children[1]
        name = node.data.get("name")
        if type_node.kind == NodeType.PASS:
            return "\n".join([f"{self._pad(depth)}except:",
                              self._emit_block(body, depth + 1)])
        as_str = f" as {name}" if name else ""
        return "\n".join([
            f"{self._pad(depth)}except {self.emit(type_node, 0)}{as_str}:",
            self._emit_block(body, depth + 1)
        ])

    def _emit_with(self, node: Node, depth: int) -> str:
        body = node.children[-1]
        items_flat = node.children[:-1]
        items: list[str] = []
        for i in range(0, len(items_flat), 2):
            ctx = self.emit(items_flat[i], 0)
            as_node = items_flat[i + 1] if i + 1 < len(items_flat) else None
            if as_node and as_node.kind != NodeType.PASS:
                items.append(f"{ctx} as {self.emit(as_node, 0)}")
            else:
                items.append(ctx)
        return "\n".join([f"{self._pad(depth)}with {', '.join(items)}:",
                          self._emit_block(body, depth + 1)])

    def _emit_assert(self, node: Node, depth: int) -> str:
        test = self.emit(node.children[0], 0)
        msg = f", {self.emit(node.children[1], 0)}" if len(node.children) > 1 else ""
        return self._pad(depth) + f"assert {test}{msg}"

    def _emit_delete(self, node: Node, depth: int) -> str:
        targets = ", ".join(self.emit(c, 0) for c in node.children)
        return self._pad(depth) + f"del {targets}"

    def _emit_global_stmt(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "global " + ", ".join(node.data.get("names", []))

    def _emit_nonlocal_stmt(self, node: Node, depth: int) -> str:
        return self._pad(depth) + "nonlocal " + ", ".join(node.data.get("names", []))

    def _emit_expr_stmt(self, node: Node, depth: int) -> str:
        if node.data.get("raw"):
            return self._pad(depth) + node.data["raw"]
        if node.children:
            return self._pad(depth) + self.emit(node.children[0], 0)
        return self._pad(depth) + "pass"

    # --- expressions (depth-0) ---
    def _emit_call(self, node: Node, depth: int) -> str:
        func = self.emit(node.children[0], 0)
        args: list[str] = []
        for c in node.children[1:]:
            if c.kind == NodeType.KWARG:
                key = c.data.get("key")
                val = self.emit(c.children[0], 0) if c.children else "None"
                args.append(f"**{val}" if key is None else f"{key}={val}")
            elif c.kind == NodeType.STARRED:
                inner = self.emit(c.children[0], 0) if c.children else "_"
                args.append(f"*{inner}")
            else:
                args.append(self.emit(c, 0))
        return f"{func}({', '.join(args)})"

    def _emit_bin_op(self, node: Node, depth: int) -> str:
        op = node.data.get("op", "+")
        left, right = node.children[0], node.children[1]
        ls = self.emit(left, 0)
        rs = self.emit(right, 0)
        if _needs_parens(left, op):
            ls = f"({ls})"
        if _needs_parens(right, op):
            rs = f"({rs})"
        return f"{ls} {op} {rs}"

    def _emit_unary_op(self, node: Node, depth: int) -> str:
        op = node.data.get("op", "-")
        operand = self.emit(node.children[0], 0)
        if node.children[0].kind in (NodeType.BIN_OP, NodeType.BOOL_OP, NodeType.COMPARE):
            operand = f"({operand})"
        space = " " if op == "not" else ""
        return f"{op}{space}{operand}"

    def _emit_compare(self, node: Node, depth: int) -> str:
        ops = node.data.get("ops", ["=="])
        parts = [self.emit(node.children[0], 0)]
        for op, comp in zip(ops, node.children[1:]):
            parts.append(op)
            parts.append(self.emit(comp, 0))
        return " ".join(parts)

    def _emit_bool_op(self, node: Node, depth: int) -> str:
        op = node.data.get("op", "and")
        parts = []
        for c in node.children:
            s = self.emit(c, 0)
            if c.kind in (NodeType.BOOL_OP,) and c.data.get("op") != op:
                s = f"({s})"
            parts.append(s)
        return f" {op} ".join(parts)

    def _emit_ternary(self, node: Node, depth: int) -> str:
        test, body, orelse = node.children
        return (f"{self.emit(body, 0)} if {self.emit(test, 0)}"
                f" else {self.emit(orelse, 0)}")

    def _emit_lambda(self, node: Node, depth: int) -> str:
        body = node.children[-1]
        params = node.children[:-1]
        param_str = ", ".join(self._param_str(p) for p in params)
        return f"lambda {param_str}: {self.emit(body, 0)}"

    def _emit_yield(self, node: Node, depth: int) -> str:
        from_yield = node.data.get("from", False)
        kw = "yield from" if from_yield else "yield"
        val = f" {self.emit(node.children[0], 0)}" if node.children else ""
        return self._pad(depth) + f"{kw}{val}"

    def _emit_await(self, node: Node, depth: int) -> str:
        return f"await {self.emit(node.children[0], 0)}"

    def _emit_name(self, node: Node, depth: int) -> str:
        return node.data.get("id", "_")

    def _emit_const(self, node: Node, depth: int) -> str:
        t = node.data.get("type", "none")
        v = node.data.get("value")
        if t == "none":
            return "None"
        if t == "bool":
            return "True" if v else "False"
        if t == "str":
            return repr(str(v))
        if t == "bytes":
            return repr(bytes(v) if isinstance(v, list) else v)
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
        step = "" if node.children[2].kind == NodeType.PASS else self.emit(node.children[2], 0)
        return f"{lo}:{hi}" + (f":{step}" if step else "")

    def _emit_starred(self, node: Node, depth: int) -> str:
        return f"*{self.emit(node.children[0], 0)}" if node.children else "*_"

    def _emit_list_lit(self, node: Node, depth: int) -> str:
        return "[" + ", ".join(self.emit(c, 0) for c in node.children) + "]"

    def _emit_tuple_lit(self, node: Node, depth: int) -> str:
        items = ", ".join(self.emit(c, 0) for c in node.children)
        return f"({items},)" if len(node.children) == 1 else f"({items})"

    def _emit_set_lit(self, node: Node, depth: int) -> str:
        if not node.children:
            return "set()"
        return "{" + ", ".join(self.emit(c, 0) for c in node.children) + "}"

    def _emit_dict_lit(self, node: Node, depth: int) -> str:
        pairs: list[str] = []
        children = node.children
        for i in range(0, len(children) - 1, 2):
            k, v = children[i], children[i + 1]
            if k.kind == NodeType.STARRED:
                pairs.append(f"**{self.emit(v, 0)}")
            else:
                pairs.append(f"{self.emit(k, 0)}: {self.emit(v, 0)}")
        return "{" + ", ".join(pairs) + "}"

    def _emit_template_str(self, node: Node, depth: int) -> str:
        parts: list[str] = []
        for c in node.children:
            if c.kind == NodeType.CONST and c.data.get("type") == "str":
                parts.append(c.data.get("value", ""))
            else:
                parts.append("{" + self.emit(c, 0) + "}")
        inner = "".join(parts)
        inner = inner.replace("'", "\\'")
        return f"f'{inner}'"

    def _emit_comprehension(self, node: Node, depth: int) -> str:
        kind = node.data.get("kind", "list")
        children = node.children[:]
        if kind == "dict":
            key_s = self.emit(children.pop(0), 0)
            val_s = self.emit(children.pop(0), 0)
            elt_s = f"{key_s}: {val_s}"
        else:
            elt_s = self.emit(children.pop(0), 0)
        clauses: list[str] = []
        for c in children:
            if c.kind == NodeType.FOR:
                target = self.emit(c.children[0], 0)
                iter_ = self.emit(c.children[1], 0)
                clauses.append(f"for {target} in {iter_}")
            elif c.kind == NodeType.IF and c.data.get("comp"):
                clauses.append(f"if {self.emit(c.children[0], 0)}")
        body = " ".join(clauses)
        if kind == "list":
            return f"[{elt_s} {body}]"
        if kind == "set":
            return "{" + f"{elt_s} {body}" + "}"
        if kind == "dict":
            return "{" + f"{elt_s} {body}" + "}"
        return f"({elt_s} {body})"

    def _emit_decorator(self, node: Node, depth: int) -> str:
        if node.children:
            return self._pad(depth) + "@" + self.emit(node.children[0], 0)
        return ""


def emit_python(root: Node) -> str:
    return PythonBackend().emit(root)
