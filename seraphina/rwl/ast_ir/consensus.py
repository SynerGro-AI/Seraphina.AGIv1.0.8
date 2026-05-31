"""Roman Wheel Triad consensus scoring for RWAST translations.

Scores a translated RWAST against the original across three axes:
    Geometric   — structural fidelity (node count, depth, shape)
    Verification — semantic coverage (how many node kinds survived)
    Mercy-Civ   — graceful degradation (unknown/fallback node ratio)

Each axis returns 0.0..1.0.  The Triad consensus is the harmonic mean
(same formula used by RomanWheelTriad in seraphina.core).
"""
from __future__ import annotations

from dataclasses import dataclass

from .nodes import Node, NodeType


@dataclass
class TriadScore:
    geometric: float      # structural shape similarity
    verification: float   # semantic kind coverage
    mercy_civ: float      # low-fallback reward

    @property
    def consensus(self) -> float:
        """Harmonic mean of the three axes."""
        vals = [self.geometric, self.verification, self.mercy_civ]
        if any(v == 0 for v in vals):
            return 0.0
        return 3.0 / sum(1.0 / v for v in vals)

    def __str__(self) -> str:
        return (f"Geometric={self.geometric:.3f}  "
                f"Verification={self.verification:.3f}  "
                f"Mercy-Civ={self.mercy_civ:.3f}  "
                f"Consensus={self.consensus:.3f}")


def _count_nodes(node: Node) -> int:
    return 1 + sum(_count_nodes(c) for c in node.children)


def _depth(node: Node) -> int:
    if not node.children:
        return 0
    return 1 + max(_depth(c) for c in node.children)


def _kind_set(node: Node) -> set:
    s = {node.kind}
    for c in node.children:
        s |= _kind_set(c)
    return s


def _fallback_ratio(node: Node) -> float:
    total = _count_nodes(node)
    if total == 0:
        return 1.0
    fallbacks = sum(
        1 for n in _iter_nodes(node)
        if n.kind in (NodeType.UNKNOWN, NodeType.EXPR_STMT) and n.data.get("raw")
    )
    return fallbacks / total


def _iter_nodes(node: Node):
    yield node
    for c in node.children:
        yield from _iter_nodes(c)


def score(original: Node, translated: Node) -> TriadScore:
    """Score a translation against the original RWAST."""
    orig_count = _count_nodes(original)
    trans_count = _count_nodes(translated)
    orig_depth = max(_depth(original), 1)
    trans_depth = max(_depth(translated), 1)

    # Geometric: size + depth similarity (ratio of smaller/larger)
    size_ratio = min(orig_count, trans_count) / max(orig_count, trans_count)
    depth_ratio = min(orig_depth, trans_depth) / max(orig_depth, trans_depth)
    geometric = (size_ratio + depth_ratio) / 2

    # Verification: Jaccard of node kind sets
    orig_kinds = _kind_set(original)
    trans_kinds = _kind_set(translated)
    if not orig_kinds and not trans_kinds:
        verification = 1.0
    else:
        verification = len(orig_kinds & trans_kinds) / len(orig_kinds | trans_kinds)

    # Mercy-Civ: 1 - fallback_ratio (reward low-fallback translations)
    mercy_civ = max(0.0, 1.0 - _fallback_ratio(translated))

    return TriadScore(geometric=geometric, verification=verification, mercy_civ=mercy_civ)
