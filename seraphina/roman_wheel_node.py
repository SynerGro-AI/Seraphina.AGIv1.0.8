# ---------------------------------------------------------------------------
# VENDORED: Roman Wheel Node 1.0.0
#   upstream : https://github.com/SynerGro-AI/roman-wheel-node
#   file     : src/roman_wheel_node/core.py  (commit 940dd75b08fe6a8ec50f798ea904b63d54673d35)
#   sha256   : 1bedc203cacc0813edf46b0bc3be689a2206b149f2a2614eff18cdcc489940e9  (of the upstream file = everything below the END line)
#   license  : MIT, Copyright (c) 2026 SynerGro.AI (same license as this package)
# Vendored so the seraphina-agi wheel stays dependency-free and deterministic.
# Do not edit below; update by re-copying upstream and refreshing the sha256.
# tests/test_claim_gate.py verifies the body hash.
# --- END VENDOR HEADER ---
"""Roman Wheel Node (algorithm v3, package 1.0.0): an exact-copy gate plus learned, auditable evidence fusion.

Every claim an agent wants to put in its trace goes through :func:`roman_wheel_node`.

Pipeline (in order, each step can only make a claim *harder* to accept):

1. **Exact-copy gate** - ``a`` must be 1 (exact hash / binary / invariant match), else BLOCK.
2. **No evidence, no entry** - empty ``scores`` -> BLOCK.
3. **Hard veto** - any source score that clamps to exactly 0 -> BLOCK, whatever its trust.
4. **Fusion** - combine the clamped scores into ``eff`` in [0, 1]:

   * ``mode="geomean"`` / ``"product"`` (v1/v2 behaviour, unchanged).
   * ``mode="bayes"`` (v3): ``eff`` is the posterior P(claim is true), obtained by adding
     each source's log-likelihood ratio, weighted by its learned reliability ``r``.
     A source with ``r < 0.5`` gets a negative weight, so it is inverted automatically.

5. **Decision** - map ``eff`` to an opcode. With a :class:`ThresholdLearner` the ACCEPT
   cut-off is learned from an outcomes ledger; without one the fixed v1 bands are used.

State lives in append-only JSONL ledgers (:class:`LiveWeights`, :class:`ThresholdLearner`).
Nothing is ever edited or deleted: state is rebuilt by replaying the ledger, and decay
("forgetting") is applied *during replay*, so any history can be re-run with other settings.

Public API: ``clamp01``, ``opcode``, ``opcode_learned``, ``LiveWeights``,
``ThresholdLearner``, ``roman_wheel_node``, ``give_feedback``.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

__all__ = ["clamp01", "opcode", "opcode_learned", "LiveWeights", "ThresholdLearner",
           "roman_wheel_node", "give_feedback", "Result", "BAYES_VARIANTS"]
__version__ = "1.0.0"   # package version (algorithm generation: v3)

Result = Tuple[float, str, str]                    # (eff, opcode, status)
Scores = Union[Mapping[str, float], Sequence[float]]
BAYES_VARIANTS = ("hard", "soft", "logit")
_R_MIN, _R_MAX = 0.01, 0.99                         # caps one source's log-odds at +/-4.6
_BLOCK: Result = (0.0, "000", "BLOCK")


def clamp01(x: float) -> float:
    """Clamp ``x`` to the closed interval [0, 1]."""
    return max(0.0, min(1.0, float(x)))


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def opcode(eff: float) -> Tuple[str, str]:
    """Fixed v1 bands: >=0.85 111, >=0.65 110, >=0.35 101 (ACCEPT); >0.05 100 HEDGE; else BLOCK."""
    if eff >= 0.85: return "111", "ACCEPT"
    if eff >= 0.65: return "110", "ACCEPT"
    if eff >= 0.35: return "101", "ACCEPT"
    if eff > 0.05:  return "100", "HEDGE"
    return "000", "BLOCK"


def opcode_learned(eff: float, cutoff: float, hedge_width: float = 0.15) -> Tuple[str, str]:
    """Bands relative to a learned ACCEPT cut-off ``c``.

    ACCEPT iff ``eff >= c``; the span [c, 1] is split in thirds into 101 / 110 / 111.
    HEDGE (100) for ``max(c - hedge_width, 0.05) < eff < c`` (strictly above 0.05); else BLOCK.
    """
    c = clamp01(cutoff)
    if eff >= c:
        span = 1.0 - c
        if eff >= c + 2.0 * span / 3.0: return "111", "ACCEPT"
        if eff >= c + span / 3.0:       return "110", "ACCEPT"
        return "101", "ACCEPT"
    if eff > 0.05 and eff >= c - hedge_width:
        return "100", "HEDGE"
    return "000", "BLOCK"


def _append(path: str, ev: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(ev) + "\n")
        f.flush()


def _replay(path: str) -> Iterable[dict]:
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


class LiveWeights:
    """Per-source reliability ``r = alpha / (alpha + beta)`` learned from right/wrong feedback.

    Args:
        ledger_path: append-only JSONL ledger; replayed on construction.
        prior: Beta prior (alpha, beta); (1, 1) means "no idea", r = 0.5.
        half_life: observations of a source after which old evidence counts half.
            Default 150 (v3). ``None`` = never forget (the v2 default).
    """

    def __init__(self, ledger_path: str = "weights_ledger.jsonl",
                 prior: Tuple[float, float] = (1.0, 1.0),
                 half_life: Optional[float] = 150) -> None:
        self.path = ledger_path
        self.prior = prior
        self.half_life = half_life
        self.decay = 0.5 ** (1.0 / half_life) if half_life else 1.0
        self.state: Dict[str, List[float]] = {}
        for ev in _replay(self.path):
            self._apply(ev)

    def _apply(self, ev: dict) -> None:
        a, b = self.state.setdefault(ev["source"], list(self.prior))
        pa, pb = self.prior
        a = pa + (a - pa) * self.decay
        b = pb + (b - pb) * self.decay
        self.state[ev["source"]] = [a + ev["d_alpha"], b + ev["d_beta"]]

    def reliability(self, source: str) -> float:
        """Current P(source's call is right). Unknown sources return the prior mean."""
        a, b = self.state.get(source, self.prior)
        return a / (a + b)

    def observe(self, source: str, outcome: float, strength: float = 1.0, note: str = "") -> float:
        """Record that ``source`` was right (1) or wrong (0). Append-only. Returns new reliability."""
        o, s = clamp01(outcome), max(0.0, float(strength))
        ev = {"t": time.time(), "source": source, "outcome": o,
              "strength": s, "d_alpha": o * s, "d_beta": (1 - o) * s, "note": note}
        _append(self.path, ev)
        self._apply(ev)
        return self.reliability(source)


class ThresholdLearner:
    """Learns the ACCEPT cut-off that maximises (decayed) accuracy on recent outcomes.

    Each resolved claim appends ``{"mode", "eff", "truth"}`` to the ledger. For a candidate
    cut-off ``c`` the accuracy is (weight of false claims with eff < c + weight of true claims
    with eff >= c) / total weight; the best ``c`` on a 0.001 grid wins (ties -> nearest to
    ``default``). Separate statistics are kept per ``mode`` key, so geomean and bayes never mix.

    Args:
        ledger_path: append-only JSONL ledger; replayed on construction.
        half_life: outcomes (per mode) after which an old outcome counts half; None = never forget.
        min_obs: below this many outcomes for a mode, ``default`` is returned.
        default: cut-off used before enough data (0.5 = "more likely true than not" for bayes).
        hedge_width: width of the HEDGE band just below the cut-off.
    """

    GRID = 1000

    def __init__(self, ledger_path: str = "threshold_ledger.jsonl", half_life: Optional[float] = 500,
                 min_obs: int = 30, default: float = 0.5, hedge_width: float = 0.15) -> None:
        self.path = ledger_path
        self.half_life = half_life
        self.growth = 2.0 ** (1.0 / half_life) if half_life else 1.0   # new weight grows = old decays
        self.min_obs, self.default, self.hedge_width = min_obs, default, hedge_width
        self._t: Dict[str, List[float]] = {}
        self._f: Dict[str, List[float]] = {}
        self._w: Dict[str, float] = {}     # weight of the next outcome (per mode)
        self._n: Dict[str, int] = {}
        self._cache: Dict[str, float] = {}
        for ev in _replay(self.path):
            self._apply(ev)

    def _apply(self, ev: dict) -> None:
        m = ev["mode"]
        if m not in self._t:
            self._t[m] = [0.0] * (self.GRID + 1); self._f[m] = [0.0] * (self.GRID + 1)
            self._w[m], self._n[m] = 1.0, 0
        i = int(round(clamp01(ev["eff"]) * self.GRID))
        (self._t if ev["truth"] else self._f)[m][i] += self._w[m]
        self._w[m] *= self.growth
        self._n[m] += 1
        if self._w[m] > 1e200:                       # renormalise; ratios are unchanged
            k = 1.0 / self._w[m]
            self._t[m] = [x * k for x in self._t[m]]; self._f[m] = [x * k for x in self._f[m]]
            self._w[m] = 1.0
        self._cache.pop(m, None)

    def record(self, eff: float, truth: bool, mode: str = "bayes") -> None:
        """Append one resolved claim (its eff and whether it was actually true)."""
        ev = {"t": time.time(), "mode": mode, "eff": round(clamp01(eff), 3), "truth": bool(truth)}
        _append(self.path, ev)
        self._apply(ev)

    def n(self, mode: str = "bayes") -> int:
        return self._n.get(mode, 0)

    def cutoff(self, mode: str = "bayes") -> float:
        """Current accuracy-maximising ACCEPT cut-off for ``mode``."""
        if self._n.get(mode, 0) < self.min_obs:
            return self.default
        if mode in self._cache:
            return self._cache[mode]
        t, f = self._t[mode], self._f[mode]
        correct = sum(t)                              # cut-off 0: accept everything
        best, best_i = correct, 0
        d_best = abs(0 - self.default * self.GRID)
        for i in range(1, self.GRID + 1):             # moving the cut-off above bin i-1
            correct += f[i - 1] - t[i - 1]
            d = abs(i - self.default * self.GRID)
            if correct > best + 1e-12 * max(1.0, best) or (abs(correct - best) <= 1e-12 * max(1.0, best) and d < d_best):
                best, best_i, d_best = correct, i, d
        self._cache[mode] = best_i / self.GRID
        return self._cache[mode]


def _bayes_llr(s: float, r: float, variant: str) -> float:
    """Log-likelihood ratio log P(score | true) / P(score | false) for one source.

    hard : the source votes (s > 0.5); a vote from a source right with prob. r is worth logit(r).
    soft : treat s as P(source says "true"); LR = (r s + (1-r)(1-s)) / (r (1-s) + (1-r) s).
    logit: confidence-scaled vote, (2r - 1) * logit(s).
    """
    r = min(_R_MAX, max(_R_MIN, r))
    if variant == "hard":
        return 0.0 if s == 0.5 else (_logit(r) if s > 0.5 else -_logit(r))
    sc = min(1 - 1e-6, max(1e-6, s))
    if variant == "soft":
        return math.log((r * sc + (1 - r) * (1 - sc)) / (r * (1 - sc) + (1 - r) * sc))
    if variant == "logit":
        return (2 * r - 1) * _logit(sc)
    raise ValueError(f"unknown bayes variant {variant!r}; choose from {BAYES_VARIANTS}")


def roman_wheel_node(a: float, scores: Scores, live: Optional[LiveWeights] = None,
                     mode: str = "geomean", log_path: Optional[str] = None, flip: bool = False,
                     threshold: Optional[ThresholdLearner] = None, variant: str = "hard",
                     prior: float = 0.5, assumed_reliability: float = 0.75,
                     cutoff: Union[None, float, str] = None) -> Result:
    """Gate, fuse and classify one claim.

    Args:
        a: 1 for an exact copy (hash / binary / invariant match), 0 otherwise.
        scores: ``{source: score}``; a plain list is treated as equal-trust sources ``s0, s1, ...``.
        live: learned source reliabilities, or None (geomean: equal trust; bayes: ``assumed_reliability``).
        mode: ``"geomean"`` (default, v1), ``"product"`` (v1) or ``"bayes"`` (v3, posterior P(true)).
        log_path: optional append-only audit log of inputs, reliabilities and result.
        flip: geomean/product only - invert sources with r < 0.5 (bayes always does this).
        threshold: optional :class:`ThresholdLearner`; if given, ACCEPT iff eff >= its learned
            cut-off for key ``mode`` (``"bayes:<variant>"`` for bayes).
        cutoff: used only when ``threshold`` is None. ``None`` (default): geomean/product use the
            fixed v1 bands (ACCEPT >= 0.35); bayes uses 0.5, the decision boundary of a posterior.
            A float sets a fixed ACCEPT cut-off with relative bands; ``"fixed"`` forces v1 bands.
        variant: bayes likelihood model, one of ``"hard"`` (default, best in benchmarks), ``"soft"``, ``"logit"``.
        prior: bayes prior P(true) before any evidence.
        assumed_reliability: bayes reliability for every source when ``live`` is None.

    Returns:
        ``(eff, opcode, status)`` with eff rounded to 3 decimals and status in ACCEPT/HEDGE/BLOCK.
    """
    if isinstance(scores, (list, tuple)):
        scores = {f"s{i}": w for i, w in enumerate(scores)}
    key = f"bayes:{variant}" if mode == "bayes" else mode
    result: Result
    if a <= 0 or not scores:
        result = _BLOCK                                    # gate fail / no evidence
    else:
        ws = {k: clamp01(v) for k, v in scores.items()}
        if any(v == 0.0 for v in ws.values()):
            result = _BLOCK                                # hard veto
        elif mode == "bayes":
            p0 = min(1 - 1e-9, max(1e-9, prior))
            z = _logit(p0) + sum(_bayes_llr(ws[k], live.reliability(k) if live else assumed_reliability, variant)
                                 for k in ws)
            eff = round(_sigmoid(z), 3)
            result = (eff, *_decide(eff, threshold, key, 0.5 if cutoff is None else cutoff))
        else:
            result = _fuse_v2(ws, live, mode, flip, threshold, key, cutoff)
    if log_path:
        _append(log_path, {"t": time.time(), "a": a, "scores": dict(scores), "mode": key,
                           "reliability": {k: live.reliability(k) for k in scores} if live else None,
                           "cutoff": threshold.cutoff(key) if threshold else cutoff,
                           "eff": result[0], "opcode": result[1], "status": result[2]})
    return result


def _decide(eff: float, threshold: Optional[ThresholdLearner], key: str,
            cutoff: Union[None, float, str] = None) -> Tuple[str, str]:
    if threshold is not None:
        return opcode_learned(eff, threshold.cutoff(key), threshold.hedge_width)
    if cutoff is None or cutoff == "fixed":
        return opcode(eff)
    return opcode_learned(eff, float(cutoff))


def _fuse_v2(ws: Dict[str, float], live: Optional[LiveWeights], mode: str, flip: bool,
             threshold: Optional[ThresholdLearner], key: str,
             cutoff: Union[None, float, str] = None) -> Result:
    """v2 reliability-weighted geometric mean / product (behaviour kept bit-for-bit)."""
    rel = {k: (live.reliability(k) if live else 1.0) for k in ws}
    if flip:
        use = {k: (1.0 - ws[k] if rel[k] < 0.5 else ws[k]) for k in ws}
        use = {k: max(1e-3, v) for k, v in use.items()}
        inf = {k: abs(2 * rel[k] - 1) for k in ws}
    else:
        use, inf = ws, rel
    if sum(inf.values()) < 1e-9:
        return _BLOCK                                       # every source is pure noise
    if mode == "product":
        eff = math.prod(use[k] ** inf[k] for k in ws)
    else:
        eff = math.exp(sum(inf[k] * math.log(use[k]) for k in ws) / sum(inf.values()))
    eff = round(min(1.0, eff), 3)
    return (eff, *_decide(eff, threshold, key, cutoff))


def give_feedback(scores: Mapping[str, float], truth: bool, live: Optional[LiveWeights] = None,
                  threshold: Optional[ThresholdLearner] = None, eff: Optional[float] = None,
                  mode: str = "bayes", variant: str = "hard") -> None:
    """Close the loop once a claim's truth is known.

    Each source is marked right if its vote (score > 0.5) matched ``truth``; if ``threshold``
    and ``eff`` are given, the outcome is also added to the threshold ledger under the same
    key the node uses. Both writes are append-only.
    """
    if live is not None:
        for k, v in scores.items():
            live.observe(k, 1.0 if (clamp01(v) > 0.5) == bool(truth) else 0.0)
    if threshold is not None and eff is not None:
        threshold.record(eff, truth, f"bayes:{variant}" if mode == "bayes" else mode)


if __name__ == "__main__":
    for a, ws in [(1, [0.9, 0.92, 0.88]), (1, [0.7] * 4), (0, [0.95, 0.9]),
                  (1, [0.8, 0.0, 0.9]), (1, [1.5, 0.9]), (1, [])]:
        print(" ", a, ws, roman_wheel_node(a, ws))
