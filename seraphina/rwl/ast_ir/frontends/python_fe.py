"""Python → RWAST frontend.

Uses Python's stdlib `ast` module for a complete, correct parse of any
valid Python 3.8+ source.  The visitor walks every AST node and emits
the corresponding RWAST node tree.
"""
from __future__ import annotations

import ast as _ast
from typing import Any

from ..nodes import Node, NodeType

# --------------------------------------------------------------------------
# Operator string tables
# --------------------------------------------------------------------------
_BINOP: dict[type, str] = {
    _ast.Add: "+",   _ast.Sub: "-",   _ast.Mult: "*",  _ast.Div: "/",
    _ast.FloorDiv: "//", _ast.Mod: "%", _ast.Pow: "**",
    _ast.LShift: "<<", _ast.RShift: ">>",
    _ast.BitOr: "|", _ast.BitAnd: "&", _ast.BitXor: "^",
    _ast.MatMult: "@",
}
_UNOP: dict[type, str] = {
    _ast.UAdd: "+", _ast.USub: "-", _ast.Invert: "~", _ast.Not: "not",
}
_CMPOP: dict[type, str] = {
    _ast.Eq: "==",  _ast.NotEq: "!=",  _ast.Lt: "<",  _ast.LtE: "<=",
    _ast.Gt: ">",   _ast.GtE: ">=",
    _ast.Is: "is",  _ast.IsNot: "is not",
    _ast.In: "in",  _ast.NotIn: "not in",
}
_BOOLOP: dict[type, str] = {_ast.And: "and", _ast.Or: "or"}
_AUGOP: dict[type, str] = {
    _ast.Add: "+=",    _ast.Sub: "-=",    _ast.Mult: "*=",   _ast.Div: "/=",
    _ast.FloorDiv: "//=", _ast.Mod: "%=", _ast.Pow: "**=",
    _ast.LShift: "<<=", _ast.RShift: ">>=",
    _ast.BitOr: "|=",  _ast.BitAnd: "&=", _ast.BitXor: "^=", _ast.MatMult: "@=",
}


# --------------------------------------------------------------------------
# visitor
# --------------------------------------------------------------------------
class _Visitor:
    def visit(self, node: _ast.AST) -> Node:
        method = f"visit_{type(node).__name__}"
        return getattr(self, method, self._fallback)(node)

    def _fallback(self, node: _ast.AST) -> Node:
        return Node(NodeType.UNKNOWN, data={"raw": f"# {type(node).__name__}"})

    def _block(self, stmts: list[_ast.stmt]) -> Node:
        return Node(NodeType.BLOCK, children=[self.visit(s) for s in stmts])

    def _annotation(self, ann) -> str | None:
        if ann is None:
            return None
        try:
            return _ast.unparse(ann)
        except Exception:
            return None

    # --- module -------------------------------------------------------
    def visit_Module(self, node: _ast.Module) -> Node:
        return Node(NodeType.MODULE, children=[self.visit(s) for s in node.body])

    # --- imports ------------------------------------------------------
    def visit_Import(self, node: _ast.Import) -> Node:
        names = [[a.name, a.asname] for a in node.names]
        return Node(NodeType.IMPORT, data={"names": names})

    def visit_ImportFrom(self, node: _ast.ImportFrom) -> Node:
        names = [[a.name, a.asname] for a in node.names]
        return Node(NodeType.IMPORT_FROM,
                    data={"module": node.module or "", "names": names, "level": node.level})

    # --- functions / classes ------------------------------------------
    def _params(self, args: _ast.arguments) -> list[Node]:
        nodes: list[Node] = []
        # positional-only (Python 3.8+)
        for a in args.posonlyargs:
            nodes.append(Node(NodeType.PARAM,
                              data={"name": a.arg, "kind": "posonly",
                                    "annotation": self._annotation(a.annotation)}))
        # regular positional
        n_defaults = len(args.defaults)
        n_pos = len(args.args)
        for i, a in enumerate(args.args):
            default_idx = i - (n_pos - n_defaults)
            children = []
            if default_idx >= 0:
                children = [self.visit(args.defaults[default_idx])]
            nodes.append(Node(NodeType.PARAM,
                              data={"name": a.arg, "kind": "pos",
                                    "annotation": self._annotation(a.annotation)},
                              children=children))
        # *args
        if args.vararg:
            nodes.append(Node(NodeType.PARAM,
                              data={"name": args.vararg.arg, "kind": "var",
                                    "annotation": self._annotation(args.vararg.annotation)}))
        # keyword-only
        for a, default in zip(args.kwonlyargs, args.kw_defaults):
            children = [self.visit(default)] if default is not None else []
            nodes.append(Node(NodeType.PARAM,
                              data={"name": a.arg, "kind": "kw",
                                    "annotation": self._annotation(a.annotation)},
                              children=children))
        # **kwargs
        if args.kwarg:
            nodes.append(Node(NodeType.PARAM,
                              data={"name": args.kwarg.arg, "kind": "kwvar",
                                    "annotation": self._annotation(args.kwarg.annotation)}))
        return nodes

    def _func(self, node, is_async: bool) -> Node:
        kind = NodeType.ASYNC_FUNC if is_async else NodeType.FUNCTION_DEF
        params = self._params(node.args)
        body = self._block(node.body)
        decorators = [Node(NodeType.DECORATOR, children=[self.visit(d)])
                      for d in node.decorator_list]
        return Node(kind,
                    data={"name": node.name,
                          "returns": self._annotation(node.returns)},
                    children=params + [body] + decorators)

    def visit_FunctionDef(self, node: _ast.FunctionDef) -> Node:
        return self._func(node, False)

    def visit_AsyncFunctionDef(self, node: _ast.AsyncFunctionDef) -> Node:
        return self._func(node, True)

    def visit_ClassDef(self, node: _ast.ClassDef) -> Node:
        bases = [self.visit(b) for b in node.bases]
        body = self._block(node.body)
        decorators = [Node(NodeType.DECORATOR, children=[self.visit(d)])
                      for d in node.decorator_list]
        return Node(NodeType.CLASS_DEF,
                    data={"name": node.name},
                    children=bases + [body] + decorators)

    # --- assignment ---------------------------------------------------
    def visit_Assign(self, node: _ast.Assign) -> Node:
        targets = [self.visit(t) for t in node.targets]
        value = self.visit(node.value)
        return Node(NodeType.ASSIGN, children=targets + [value])

    def visit_AnnAssign(self, node: _ast.AnnAssign) -> Node:
        target = self.visit(node.target)
        ann = self._annotation(node.annotation)
        children = [target]
        if node.value is not None:
            children.append(self.visit(node.value))
        return Node(NodeType.ASSIGN, data={"annotation": ann}, children=children)

    def visit_AugAssign(self, node: _ast.AugAssign) -> Node:
        op = _AUGOP.get(type(node.op), "+=")
        return Node(NodeType.AUG_ASSIGN, data={"op": op},
                    children=[self.visit(node.target), self.visit(node.value)])

    def visit_NamedExpr(self, node: _ast.NamedExpr) -> Node:
        return Node(NodeType.ASSIGN, data={"walrus": True},
                    children=[self.visit(node.target), self.visit(node.value)])

    # --- control flow -------------------------------------------------
    def visit_Return(self, node: _ast.Return) -> Node:
        children = [self.visit(node.value)] if node.value else []
        return Node(NodeType.RETURN, children=children)

    def visit_If(self, node: _ast.If) -> Node:
        test = self.visit(node.test)
        body = self._block(node.body)
        orelse = self._block(node.orelse) if node.orelse else Node(NodeType.BLOCK)
        return Node(NodeType.IF, children=[test, body, orelse])

    def visit_While(self, node: _ast.While) -> Node:
        test = self.visit(node.test)
        body = self._block(node.body)
        return Node(NodeType.WHILE, children=[test, body])

    def visit_For(self, node: _ast.For) -> Node:
        target = self.visit(node.target)
        iter_ = self.visit(node.iter)
        body = self._block(node.body)
        return Node(NodeType.FOR, children=[target, iter_, body])

    def visit_AsyncFor(self, node: _ast.AsyncFor) -> Node:
        n = self.visit_For(node)
        n.data["async"] = True
        return n

    def visit_Break(self, _) -> Node:
        return Node(NodeType.BREAK)

    def visit_Continue(self, _) -> Node:
        return Node(NodeType.CONTINUE)

    def visit_Pass(self, _) -> Node:
        return Node(NodeType.PASS)

    def visit_Raise(self, node: _ast.Raise) -> Node:
        children = []
        if node.exc:
            children.append(self.visit(node.exc))
        if node.cause:
            children.append(self.visit(node.cause))
        return Node(NodeType.RAISE, data={"cause": node.cause is not None},
                    children=children)

    def visit_Try(self, node: _ast.Try) -> Node:
        body = self._block(node.body)
        handlers = [self._except(h) for h in node.handlers]
        else_block = self._block(node.orelse) if node.orelse else Node(NodeType.BLOCK)
        finally_block = self._block(node.finalbody) if node.finalbody else Node(NodeType.BLOCK)
        return Node(NodeType.TRY,
                    children=[body] + handlers + [else_block, finally_block])

    def visit_TryStar(self, node) -> Node:
        return self.visit_Try(node)  # treat ExceptionGroup as regular Try

    def _except(self, handler: _ast.ExceptHandler) -> Node:
        type_node = self.visit(handler.type) if handler.type else Node(NodeType.PASS)
        body = self._block(handler.body)
        return Node(NodeType.EXCEPT_CLAUSE,
                    data={"name": handler.name},
                    children=[type_node, body])

    def visit_With(self, node: _ast.With) -> Node:
        items: list[Node] = []
        for item in node.items:
            items.append(self.visit(item.context_expr))
            items.append(self.visit(item.optional_vars)
                         if item.optional_vars else Node(NodeType.PASS))
        body = self._block(node.body)
        return Node(NodeType.WITH, children=items + [body])

    def visit_Assert(self, node: _ast.Assert) -> Node:
        children = [self.visit(node.test)]
        if node.msg:
            children.append(self.visit(node.msg))
        return Node(NodeType.ASSERT, children=children)

    def visit_Delete(self, node: _ast.Delete) -> Node:
        return Node(NodeType.DELETE, children=[self.visit(t) for t in node.targets])

    def visit_Global(self, node: _ast.Global) -> Node:
        return Node(NodeType.GLOBAL_STMT, data={"names": node.names})

    def visit_Nonlocal(self, node: _ast.Nonlocal) -> Node:
        return Node(NodeType.NONLOCAL_STMT, data={"names": node.names})

    def visit_Expr(self, node: _ast.Expr) -> Node:
        return Node(NodeType.EXPR_STMT, children=[self.visit(node.value)])

    # --- expressions --------------------------------------------------
    def visit_Call(self, node: _ast.Call) -> Node:
        func = self.visit(node.func)
        args = [self.visit(a) for a in node.args]
        kwargs = [Node(NodeType.KWARG,
                       data={"key": kw.arg},
                       children=[self.visit(kw.value)])
                  for kw in node.keywords]
        return Node(NodeType.CALL, children=[func] + args + kwargs)

    def visit_BinOp(self, node: _ast.BinOp) -> Node:
        op = _BINOP.get(type(node.op), "+")
        return Node(NodeType.BIN_OP, data={"op": op},
                    children=[self.visit(node.left), self.visit(node.right)])

    def visit_UnaryOp(self, node: _ast.UnaryOp) -> Node:
        op = _UNOP.get(type(node.op), "-")
        return Node(NodeType.UNARY_OP, data={"op": op},
                    children=[self.visit(node.operand)])

    def visit_Compare(self, node: _ast.Compare) -> Node:
        ops = [_CMPOP.get(type(o), "==") for o in node.ops]
        left = self.visit(node.left)
        comparators = [self.visit(c) for c in node.comparators]
        return Node(NodeType.COMPARE, data={"ops": ops},
                    children=[left] + comparators)

    def visit_BoolOp(self, node: _ast.BoolOp) -> Node:
        op = _BOOLOP.get(type(node.op), "and")
        return Node(NodeType.BOOL_OP, data={"op": op},
                    children=[self.visit(v) for v in node.values])

    def visit_IfExp(self, node: _ast.IfExp) -> Node:
        return Node(NodeType.TERNARY,
                    children=[self.visit(node.test),
                               self.visit(node.body),
                               self.visit(node.orelse)])

    def visit_Lambda(self, node: _ast.Lambda) -> Node:
        params = self._params(node.args)
        body = self.visit(node.body)
        return Node(NodeType.LAMBDA, children=params + [body])

    def visit_Yield(self, node: _ast.Yield) -> Node:
        children = [self.visit(node.value)] if node.value else []
        return Node(NodeType.YIELD, data={"from": False}, children=children)

    def visit_YieldFrom(self, node: _ast.YieldFrom) -> Node:
        return Node(NodeType.YIELD, data={"from": True}, children=[self.visit(node.value)])

    def visit_Await(self, node: _ast.Await) -> Node:
        return Node(NodeType.AWAIT, children=[self.visit(node.value)])

    # --- primaries ----------------------------------------------------
    def visit_Name(self, node: _ast.Name) -> Node:
        return Node(NodeType.NAME, data={"id": node.id})

    def visit_Constant(self, node: _ast.Constant) -> Node:
        v = node.value
        if v is None:
            return Node(NodeType.CONST, data={"type": "none", "value": None})
        if isinstance(v, bool):
            return Node(NodeType.CONST, data={"type": "bool", "value": v})
        if isinstance(v, int):
            return Node(NodeType.CONST, data={"type": "int", "value": v})
        if isinstance(v, float):
            return Node(NodeType.CONST, data={"type": "float", "value": v})
        if isinstance(v, str):
            return Node(NodeType.CONST, data={"type": "str", "value": v})
        if isinstance(v, bytes):
            return Node(NodeType.CONST, data={"type": "bytes",
                                               "value": list(v)})
        return Node(NodeType.CONST, data={"type": "str", "value": repr(v)})

    def visit_Attribute(self, node: _ast.Attribute) -> Node:
        return Node(NodeType.ATTR, data={"attr": node.attr},
                    children=[self.visit(node.value)])

    def visit_Subscript(self, node: _ast.Subscript) -> Node:
        return Node(NodeType.SUBSCRIPT,
                    children=[self.visit(node.value), self.visit(node.slice)])

    def visit_Slice(self, node: _ast.Slice) -> Node:
        lo = self.visit(node.lower) if node.lower else Node(NodeType.PASS)
        hi = self.visit(node.upper) if node.upper else Node(NodeType.PASS)
        step = self.visit(node.step) if node.step else Node(NodeType.PASS)
        return Node(NodeType.SLICE, children=[lo, hi, step])

    def visit_Starred(self, node: _ast.Starred) -> Node:
        return Node(NodeType.STARRED, children=[self.visit(node.value)])

    # --- literals -----------------------------------------------------
    def visit_List(self, node: _ast.List) -> Node:
        return Node(NodeType.LIST_LIT, children=[self.visit(e) for e in node.elts])

    def visit_Tuple(self, node: _ast.Tuple) -> Node:
        return Node(NodeType.TUPLE_LIT, children=[self.visit(e) for e in node.elts])

    def visit_Set(self, node: _ast.Set) -> Node:
        return Node(NodeType.SET_LIT, children=[self.visit(e) for e in node.elts])

    def visit_Dict(self, node: _ast.Dict) -> Node:
        children: list[Node] = []
        for k, v in zip(node.keys, node.values):
            children.append(self.visit(k) if k is not None else Node(NodeType.STARRED))
            children.append(self.visit(v))
        return Node(NodeType.DICT_LIT, children=children)

    def visit_JoinedStr(self, node: _ast.JoinedStr) -> Node:
        """f-string → TEMPLATE_STR with parts as children."""
        parts: list[Node] = []
        for v in node.values:
            if isinstance(v, _ast.Constant):
                parts.append(self.visit(v))
            elif isinstance(v, _ast.FormattedValue):
                parts.append(self.visit(v.value))
            else:
                parts.append(self.visit(v))
        return Node(NodeType.TEMPLATE_STR, children=parts)

    def visit_FormattedValue(self, node: _ast.FormattedValue) -> Node:
        return self.visit(node.value)

    # --- comprehensions -----------------------------------------------
    def _comprehension(self, kind: str, elt_nodes: list[Node],
                        generators: list[_ast.comprehension]) -> Node:
        children = elt_nodes[:]
        for gen in generators:
            children.append(Node(NodeType.FOR,
                                 data={"comp": True},
                                 children=[self.visit(gen.target),
                                           self.visit(gen.iter)]))
            for cond in gen.ifs:
                children.append(Node(NodeType.IF,
                                     data={"comp": True},
                                     children=[self.visit(cond),
                                               Node(NodeType.BLOCK),
                                               Node(NodeType.BLOCK)]))
        return Node(NodeType.COMPREHENSION, data={"kind": kind}, children=children)

    def visit_ListComp(self, node: _ast.ListComp) -> Node:
        return self._comprehension("list", [self.visit(node.elt)], node.generators)

    def visit_SetComp(self, node: _ast.SetComp) -> Node:
        return self._comprehension("set", [self.visit(node.elt)], node.generators)

    def visit_DictComp(self, node: _ast.DictComp) -> Node:
        return self._comprehension("dict",
                                   [self.visit(node.key), self.visit(node.value)],
                                   node.generators)

    def visit_GeneratorExp(self, node: _ast.GeneratorExp) -> Node:
        return self._comprehension("gen", [self.visit(node.elt)], node.generators)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def parse_python(source: str) -> Node:
    """Parse Python source code into an RWAST tree."""
    tree = _ast.parse(source, mode="exec")
    return _Visitor().visit(tree)
