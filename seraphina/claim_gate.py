"""Claim gate for Seraphina: every claim must pass the Roman Wheel Node before it is trusted.

This wraps the vendored :mod:`seraphina.roman_wheel_node` (upstream:
https://github.com/SynerGro-AI/roman-wheel-node) with a small, Seraphina-shaped API:

* :class:`ClaimGate`: an exact-copy gate (``a``, or a SHA-256 match) plus multi-source scoring.
  With ``ledger_dir`` it learns source reliability and its ACCEPT cut-off from feedback in
  append-only JSONL ledgers. Without one it is stateless: it writes no files and is fully deterministic.
* :func:`gate_translation`: gates an RWAST translation. The exact-copy bit is the RWL1 carrier
  round-trip (``pack(unpack(pack(t))) == pack(t)``), and the three Triad axes (Geometric,
  Verification, Mercy-Civ) are the sources. As in ``TriadScore.consensus``, an axis of exactly 0 vetoes.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Mapping, Optional, Union

from .roman_wheel_node import LiveWeights, ThresholdLearner, give_feedback, roman_wheel_node

if TYPE_CHECKING:  # pragma: no cover
    from .rwl.ast_ir.nodes import Node

__all__ = ["ClaimGate", "GateDecision", "gate_translation", "sha256_matches"]


@dataclass(frozen=True)
class GateDecision:
    """Outcome of one gated claim."""
    eff: float
    opcode: str
    status: str            # "ACCEPT" | "HEDGE" | "BLOCK"
    scores: Dict[str, float]

    @property
    def accepted(self) -> bool:
        return self.status == "ACCEPT"


def sha256_matches(content: Union[bytes, str], expected_sha256: str) -> int:
    """1 if ``content`` hashes to ``expected_sha256`` (hex, case-insensitive) exactly, else 0."""
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    return int(hashlib.sha256(data).hexdigest() == expected_sha256.strip().lower())


class ClaimGate:
    """Exact-copy gate + learned evidence fusion for claims.

    Args:
        ledger_dir: directory for ``weights.jsonl``, ``threshold.jsonl`` and the ``claims.jsonl`` audit log.
            ``None`` = stateless: no learning, no files written.
        mode: ``"bayes"`` (posterior P(true), default) or ``"geomean"`` / ``"product"`` (v1 behaviour).
        variant: bayes likelihood model (``"hard"`` is the benchmarked default).
        half_life: source-reliability forgetting, in observations per source (None = never forget).
        threshold_half_life: forgetting for the learned ACCEPT cut-off.
        assumed_reliability: bayes reliability used for every source when there is no ledger.
        cutoff: fixed ACCEPT cut-off used when there is no ledger (None = the node's default:
            0.5 for bayes, the v1 bands with ACCEPT at >= 0.35 for geomean/product).
    """

    def __init__(self, ledger_dir: Optional[str] = None, mode: str = "bayes", variant: str = "hard",
                 half_life: Optional[float] = 150, threshold_half_life: Optional[float] = 500,
                 assumed_reliability: float = 0.75, cutoff: Union[None, float, str] = None) -> None:
        self.mode, self.variant, self.assumed_reliability = mode, variant, assumed_reliability
        self.cutoff = cutoff
        self.live: Optional[LiveWeights] = None
        self.threshold: Optional[ThresholdLearner] = None
        self.audit_path: Optional[str] = None
        if ledger_dir is not None:
            os.makedirs(ledger_dir, exist_ok=True)
            self.live = LiveWeights(os.path.join(ledger_dir, "weights.jsonl"), half_life=half_life)
            self.threshold = ThresholdLearner(os.path.join(ledger_dir, "threshold.jsonl"),
                                              half_life=threshold_half_life)
            self.audit_path = os.path.join(ledger_dir, "claims.jsonl")

    def check(self, scores: Mapping[str, float], *, a: Optional[int] = None,
              content: Union[bytes, str, None] = None, expected_sha256: Optional[str] = None) -> GateDecision:
        """Gate one claim. Give either ``a`` (1 = exact copy verified) or ``content`` + ``expected_sha256``."""
        if a is None:
            if content is None or expected_sha256 is None:
                raise ValueError("provide a=0/1, or content and expected_sha256")
            a = sha256_matches(content, expected_sha256)
        sc = {str(k): float(v) for k, v in scores.items()}
        eff, op, status = roman_wheel_node(a, sc, self.live, mode=self.mode, variant=self.variant,
                                           threshold=self.threshold, log_path=self.audit_path,
                                           assumed_reliability=self.assumed_reliability,
                                           cutoff=self.cutoff)
        return GateDecision(eff, op, status, sc)

    def feedback(self, decision: GateDecision, truth: bool) -> None:
        """Record whether a gated claim turned out true (append-only). No-op when stateless."""
        if self.live is None:
            return
        give_feedback(decision.scores, truth, live=self.live, threshold=self.threshold,
                      eff=decision.eff, mode=self.mode, variant=self.variant)


def gate_translation(original: "Node", translated: "Node", gate: Optional[ClaimGate] = None) -> GateDecision:
    """Gate an RWAST translation claim ("``translated`` faithfully represents ``original``").

    Without ``gate`` this uses a stateless ``ClaimGate(mode="geomean", cutoff=0.65)``: the geometric
    mean of the three Triad axes, accepted from the v1 "110" band (0.65) upward. The v1 floor of 0.35
    is too lax here: a one-line stub translation of an 8-line function scores 0.385. This default
    needs no feedback and is deterministic. Pass a learning ``ClaimGate`` to tune the cut-off from outcomes.
    """
    from .rwl.ast_ir.consensus import score
    from .rwl.ast_ir.serial import pack, unpack

    blob = pack(translated)
    a = int(pack(unpack(blob)) == blob)
    s = score(original, translated)
    g = gate if gate is not None else ClaimGate(mode="geomean", cutoff=0.65)
    return g.check({"geometric": s.geometric, "verification": s.verification, "mercy_civ": s.mercy_civ}, a=a)
