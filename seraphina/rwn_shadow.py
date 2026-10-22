"""Roman Wheel Node SHADOW-MODE hook for Seraphina (Phase 4). One integration point, no required dependencies.

What it does: every claim Seraphina's agent produces is checked by the frozen Roman Wheel Node policy and logged
(hash-chained audit + a fresh-claims JSONL for later labelling). In shadow mode (the default and the only mode this
hook turns on by itself) the agent's output is returned exactly as it was: same object, same exceptions, no delay
by error. The hook never calls any paid API: xAI judges cannot be enabled from here.

    from seraphina.rwn_shadow import ShadowHook
    hook = ShadowHook()                                   # logs to %LOCALAPPDATA%\\Seraphina\\rwn_shadow on Windows
    answer = hook.wrap(agent.respond)(prompt)             # answer is exactly what agent.respond returned
    hook.observe("claim text", evidence=["exact evidence sentence", ...])   # or log single claims directly

Engine: if the ``roman_wheel_node`` package (>= the phase4-shadow branch) is installed, its ``ShadowRunner`` decides
each claim (ACCEPT / NOT_SURE / BLOCK) with free local sources. If it is not installed, the hook still logs every
claim to a hash-chained JSONL with outcome NOT_SURE (fail closed), so nothing is lost and nothing is trusted.

Configuration (all optional, environment variables or keyword arguments):
    SERAPHINA_RWN_LOG_DIR   log directory (default: %LOCALAPPDATA%\\Seraphina\\rwn_shadow, else ~/.local/share/seraphina/rwn_shadow)
    SERAPHINA_RWN_CORPUS    trusted corpus JSONL ({"doc_id": .., "sentences": [..]} per line): gate + retrieval
    RWN_NLI_DIR             ONNX NLI model directory (DeBERTa-v3-small cross-encoder)
    RWN_NLI2                Hugging Face id/path of MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli (torch)
    RWN_HF_CACHE            Hugging Face cache directory
    RWN_DEVICE              "cpu" (default) or "cuda" (GPU: torch CUDA for nli2, onnxruntime-gpu for the ONNX NLI)
    SERAPHINA_RWN_PROFILE   "local" (default) or "local-lite"; paid profiles are refused
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

__all__ = ["ShadowHook", "default_log_dir", "split_claims"]

_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
_FREE_PROFILES = ("local", "local-lite")


def default_log_dir() -> str:
    env = os.environ.get("SERAPHINA_RWN_LOG_DIR")
    if env:
        return env
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "Seraphina", "rwn_shadow")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "seraphina", "rwn_shadow")


def split_claims(text: str) -> List[str]:
    """Default claim extractor: an agent text output split into sentences (non-text outputs give no claims)."""
    if not isinstance(text, str):
        return []
    return [s.strip() for s in _SPLIT.split(text.strip()) if len(s.strip()) >= 12]


class _FallbackLog:
    """Hash-chained JSONL used when roman_wheel_node is not installed: every claim is logged as NOT_SURE."""

    def __init__(self, log_dir: str) -> None:
        self.path = os.path.join(log_dir, "fresh_claims.jsonl")
        self.head = "0" * 64
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.head = json.loads(line)["hash"]
        self.counts = {"ACCEPT": 0, "NOT_SURE": 0, "BLOCK": 0}

    def observe(self, claim: str, evidence: Optional[Sequence[str]] = None, meta: Optional[Mapping] = None) -> str:
        rec = {"ts": time.time(), "claim": str(claim), "evidence": [str(e) for e in (evidence or [])],
               "outcome": "NOT_SURE", "reason": "roman_wheel_node_not_installed", "meta": dict(meta or {}), "prev": self.head}
        body = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        rec["hash"] = hashlib.sha256((self.head + "|" + body).encode("utf-8")).hexdigest()
        rec["id"] = rec["hash"][:16]
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self.head = rec["hash"]
        self.counts["NOT_SURE"] += 1
        return "NOT_SURE"


def _load_corpus(path: Optional[str]) -> Optional[Dict[str, List[str]]]:
    if not path:
        return None
    out: Dict[str, List[str]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                out[str(d["doc_id"])] = [str(s) for s in d["sentences"]]
    return out


class ShadowHook:
    """Shadow-mode Roman Wheel Node hook for Seraphina. See the module docstring.

    Args:
        log_dir: where logs go (default :func:`default_log_dir`).
        profile: "local" (default) or "local-lite". Paid judge profiles are refused here.
        corpus: trusted ``{doc_id: [sentences]}`` or a JSONL path; without one, evidence can't pass the exact-copy
            gate and claims are logged as BLOCK (unverifiable), which is still useful fresh data.
        extract: ``output -> iterable of claims`` (str, (claim, evidence) or {"claim", "evidence"}); default
            :func:`split_claims`.
        engine: "auto" (roman_wheel_node if installed, else the fallback log), "rwn" or "fallback".
    """

    def __init__(self, log_dir: Optional[str] = None, profile: Optional[str] = None,
                 corpus: Optional[Any] = None, extract: Optional[Callable[[Any], Iterable[Any]]] = None,
                 engine: str = "auto", **rwn_kwargs: Any) -> None:
        self.log_dir = log_dir or default_log_dir()
        os.makedirs(self.log_dir, exist_ok=True)
        self.profile = profile or os.environ.get("SERAPHINA_RWN_PROFILE", "local")
        if self.profile not in _FREE_PROFILES:
            raise ValueError(f"profile {self.profile!r} refused: the Seraphina hook only runs free local profiles {_FREE_PROFILES}")
        for k in ("judges", "enforce"):
            if rwn_kwargs.pop(k, None):
                raise ValueError(f"{k} cannot be enabled from the Seraphina shadow hook")
        self.extract = extract or split_claims
        self.errors = 0
        self._lock = threading.Lock()
        if isinstance(corpus, str) or corpus is None:
            corpus = _load_corpus(corpus or os.environ.get("SERAPHINA_RWN_CORPUS"))
        self.engine_name, self._engine = "fallback", None
        if engine in ("auto", "rwn"):
            try:
                from roman_wheel_node.shadow import ShadowRunner          # optional dependency
                self._engine = ShadowRunner(
                    self.log_dir, profile=self.profile, corpus=corpus, judges=None, enforce=False,
                    nli_dir=os.environ.get("RWN_NLI_DIR"), nli2=os.environ.get("RWN_NLI2") if self.profile == "local" else None,
                    hf_cache=os.environ.get("RWN_HF_CACHE"), device=os.environ.get("RWN_DEVICE", "cpu"), **rwn_kwargs)
                self.engine_name = "roman_wheel_node"
            except ImportError:
                if engine == "rwn":
                    raise
        if self._engine is None:
            self._engine = _FallbackLog(self.log_dir)

    @property
    def counts(self) -> Dict[str, int]:
        return dict(self._engine.counts)

    def observe(self, claim: str, evidence: Optional[Sequence[str]] = None, meta: Optional[Mapping] = None) -> str:
        """Log one claim; returns its outcome (ACCEPT / NOT_SURE / BLOCK). Never raises."""
        try:
            with self._lock:
                v = self._engine.observe(claim, evidence, meta=meta)
            return getattr(v, "outcome", v)
        except Exception as e:                                  # the agent must never see a hook error
            self.errors += 1
            try:
                with open(os.path.join(self.log_dir, "hook_errors.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.time(), "error": f"{type(e).__name__}: {e}"[:300]}) + "\n")
            except Exception:
                pass
            return "NOT_SURE"

    def _check(self, output: Any) -> None:
        try:
            specs = list(self.extract(output))
        except Exception:
            self.errors += 1
            return
        for sp in specs:
            if isinstance(sp, str):
                self.observe(sp)
            elif isinstance(sp, Mapping):
                self.observe(sp.get("claim", ""), sp.get("evidence"), sp.get("meta"))
            elif isinstance(sp, (tuple, list)) and len(sp) == 2:
                self.observe(sp[0], sp[1])

    def wrap(self, fn: Callable) -> Callable:
        """Shadow-wrap an agent function: the return value is passed through untouched (same object)."""
        hook = self

        def wrapped(*args, **kwargs):
            out = fn(*args, **kwargs)                           # agent exceptions propagate untouched
            hook._check(out)
            return out

        wrapped.__wrapped__ = fn                                # type: ignore[attr-defined]
        wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        wrapped.__doc__ = getattr(fn, "__doc__", None)
        return wrapped


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """python -m seraphina.rwn_shadow "some agent text"   (or pipe text on stdin): logs its claims, echoes the text."""
    args = list(sys.argv[1:] if argv is None else argv)
    text = " ".join(args) if args else sys.stdin.read()
    hook = ShadowHook()
    out = hook.wrap(lambda t: t)(text)
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    sys.stderr.write(json.dumps({"engine": hook.engine_name, "profile": hook.profile, "counts": hook.counts,
                                 "log_dir": hook.log_dir}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
