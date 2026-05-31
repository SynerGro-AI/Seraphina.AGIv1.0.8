"""TypeScript code generator (RWAST → TypeScript).

Extends JSBackend, adding:
  - parameter type annotations (`: any` unless PARAM has annotation)
  - function return type (`: any` or `: void`)
  - `export` keyword prefix on top-level functions/classes
"""
from __future__ import annotations

from ..nodes import Node, NodeType
from .js_be import JSBackend


class TSBackend(JSBackend):
    lang = "ts"
    _type_suffix = ": any"

    def _func_param(self, p: Node) -> str:
        name = p.data.get("name", "_")
        kind = p.data.get("kind", "pos")
        ann = p.data.get("annotation")
        default = p.children[0] if p.children else None
        if kind == "var":
            type_str = f": {ann}[]" if ann else ": any[]"
            return f"...{name}{type_str}"
        if kind == "kwvar":
            return f"kwargs: Record<string, any> = {{}}"
        type_str = f": {ann}" if ann else ": any"
        default_str = f" = {self.emit(default, 0)}" if default else ""
        return f"{name}{type_str}{default_str}"

    def _return_type_ann(self, node: Node) -> str:
        returns = node.data.get("returns")
        if returns:
            return f": {returns}"
        # Check if any child is a RETURN with a value
        body_node = node.first_child(NodeType.BLOCK)
        if body_node:
            for c in body_node.children:
                if c.kind == NodeType.RETURN and c.children:
                    return ": any"
        return ": void"

    def _emit_class_def(self, node: Node, depth: int) -> str:
        # TS classes get `export` at top level (depth=0)
        result = super()._emit_class_def(node, depth)
        if depth == 0:
            result = "export " + result
        return result

    def _emit_function_def(self, node: Node, depth: int) -> str:
        result = self._emit_func_common(node, depth, async_kw="")
        if depth == 0:
            result = "export " + result
        return result

    def _emit_async_func(self, node: Node, depth: int) -> str:
        result = self._emit_func_common(node, depth, async_kw="async ")
        if depth == 0:
            result = "export " + result
        return result


def emit_ts(root: Node) -> str:
    return TSBackend().emit(root)
