"""RWAST public API — Roman Wheel Abstract Syntax Tree.

Provides semantic cross-language translation via a language-neutral IR.

    parse(source, lang)              → Node
    translate(source, from_, to_)    → str
    encode_ast(root)                 → bytes  (RWL1 carrier)
    decode_ast(blob)                 → Node
    score(original, translated)      → TriadScore
"""
from .nodes import Node, NodeType
from .serial import pack, unpack, encode_tree as encode_ast, decode_tree as decode_ast
from .frontends import parse
from .backends import emit
from .consensus import score, TriadScore


def translate(source: str, from_lang: str, to_lang: str) -> str:
    """Translate source code from one language to another via RWAST."""
    root = parse(source, from_lang)
    return emit(root, to_lang)


__all__ = [
    "Node", "NodeType",
    "pack", "unpack", "encode_ast", "decode_ast",
    "parse", "emit", "translate",
    "score", "TriadScore",
]
