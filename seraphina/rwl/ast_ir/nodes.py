"""RWAST node types and dataclass.

The Roman Wheel AST (RWAST) is a language-agnostic semantic IR.
Every node is a (kind, data, children) triple:

    kind     — NodeType enum (fits in u8)
    data     — JSON-serialisable dict of scalar fields
    children — ordered list of child Node objects

RWAST captures SEMANTICS, not source fidelity.  Source fidelity is the
job of the RWL byte-IR layer (codec.py).  Comments and formatting are
intentionally dropped; type annotations are preserved as strings where
present and inferred as 'any' where not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class NodeType(IntEnum):
    # --- structural ---
    MODULE          = 0
    BLOCK           = 1
    # --- imports ---
    IMPORT          = 2
    IMPORT_FROM     = 3
    EXPORT          = 4
    # --- definitions ---
    FUNCTION_DEF    = 5
    ASYNC_FUNC      = 6
    CLASS_DEF       = 7
    PARAM           = 8
    DECORATOR       = 9
    # --- assignment ---
    ASSIGN          = 10
    AUG_ASSIGN      = 11
    # --- control flow ---
    RETURN          = 12
    IF              = 13
    WHILE           = 14
    FOR             = 15
    BREAK           = 16
    CONTINUE        = 17
    PASS            = 18
    RAISE           = 19
    TRY             = 20
    EXCEPT_CLAUSE   = 21
    WITH            = 22
    ASSERT          = 23
    DELETE          = 24
    GLOBAL_STMT     = 25
    NONLOCAL_STMT   = 26
    # --- expressions ---
    CALL            = 27
    KWARG           = 28
    STARRED         = 29
    BIN_OP          = 30
    UNARY_OP        = 31
    COMPARE         = 32
    BOOL_OP         = 33
    TERNARY         = 34
    LAMBDA          = 35
    YIELD           = 36
    AWAIT           = 37
    COMPREHENSION   = 38
    # --- primaries ---
    NAME            = 39
    CONST           = 40
    ATTR            = 41
    SUBSCRIPT       = 42
    SLICE           = 43
    # --- literals ---
    LIST_LIT        = 44
    DICT_LIT        = 45
    TUPLE_LIT       = 46
    SET_LIT         = 47
    TEMPLATE_STR    = 48   # f-string / JS template literal
    # --- JS-specific ---
    ARROW_FUNC      = 49
    SPREAD          = 50
    # --- fallback ---
    EXPR_STMT       = 51
    UNKNOWN         = 52


@dataclass
class Node:
    """A single RWAST node."""
    kind: NodeType
    data: dict[str, Any] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)

    # convenience
    def first_child(self, kind: NodeType | None = None) -> "Node | None":
        if kind is None:
            return self.children[0] if self.children else None
        return next((c for c in self.children if c.kind == kind), None)

    def all_children(self, kind: NodeType) -> list["Node"]:
        return [c for c in self.children if c.kind == kind]

    def __repr__(self) -> str:
        return f"Node({self.kind.name}, data={self.data!r}, children=[{len(self.children)}])"
