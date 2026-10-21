"""Tests for the Roman Wheel Node claim gate. Run from the repo root: python -m pytest -q tests"""
import hashlib, json, os, random, re

import pytest

import seraphina
from seraphina import ClaimGate, GateDecision, gate_translation
from seraphina import roman_wheel_node as rwn
from seraphina.claim_gate import sha256_matches
from seraphina.rwl.ast_ir import emit, parse

SRC = '''
def area(w, h):
    if w <= 0 or h <= 0:
        return 0
    total = w * h
    for i in range(3):
        total = total + i
    return total
'''


def test_vendored_body_matches_recorded_upstream_hash():
    path = rwn.__file__
    text = open(path, "rb").read()
    header, body = text.split(b"# --- END VENDOR HEADER ---\n", 1)
    recorded = re.search(rb"sha256\s*:\s*([0-9a-f]{64})", header).group(1).decode()
    assert hashlib.sha256(body).hexdigest() == recorded
    assert b"github.com/SynerGro-AI/roman-wheel-node" in header and b"MIT" in header


def test_original_six_reference_calls():
    cases = [((1, [0.9, 0.92, 0.88]), (0.9, "111", "ACCEPT")), ((1, [0.7] * 4), (0.7, "110", "ACCEPT")),
             ((0, [0.95, 0.9]), (0.0, "000", "BLOCK")), ((1, [0.8, 0.0, 0.9]), (0.0, "000", "BLOCK")),
             ((1, [1.5, 0.9]), (0.949, "111", "ACCEPT")), ((1, []), (0.0, "000", "BLOCK"))]
    for args, expected in cases:
        assert rwn.roman_wheel_node(*args) == expected


def test_public_exports():
    assert {"ClaimGate", "GateDecision", "gate_translation"} <= set(seraphina.__all__)


def test_sha256_gate():
    h = hashlib.sha256(b"claim").hexdigest()
    assert sha256_matches(b"claim", h) == 1 and sha256_matches("claim", h.upper()) == 1
    assert sha256_matches(b"claim!", h) == 0
    g = ClaimGate()
    assert g.check({"x": 0.99}, content=b"claim!", expected_sha256=h).status == "BLOCK"
    assert g.check({"x": 0.99, "y": 0.95}, content=b"claim", expected_sha256=h).accepted


def test_gate_requires_exactness_input():
    with pytest.raises(ValueError):
        ClaimGate().check({"x": 0.9})


def test_stateless_gate_blocks_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    g = ClaimGate()
    assert g.check({}, a=1).status == "BLOCK"
    assert g.check({"x": 0.9}, a=0).status == "BLOCK"
    assert g.check({"x": 0.9, "veto": 0.0}, a=1).status == "BLOCK"
    d = g.check({"x": 0.9}, a=1)
    g.feedback(d, True)
    assert os.listdir(tmp_path) == []


def test_stateless_gate_is_deterministic():
    a = [ClaimGate().check({"p": 0.8, "q": 0.3, "r": 0.7}, a=1) for _ in range(3)]
    assert len({(d.eff, d.opcode, d.status) for d in a}) == 1


def test_learning_gate_learns_and_replays(tmp_path):
    d = str(tmp_path / "ledgers"); rng = random.Random(0)
    g = ClaimGate(ledger_dir=d)
    for _ in range(400):
        truth = rng.random() < 0.5
        good = truth if rng.random() < 0.9 else not truth
        liar = (not truth) if rng.random() < 0.9 else truth
        sc = {"good": 0.9 if good else 0.1, "liar": 0.9 if liar else 0.1}
        g.feedback(g.check(sc, a=1), truth)
    assert g.live.reliability("good") > 0.8 and g.live.reliability("liar") < 0.2
    # a liar saying "false" is evidence for "true"
    assert g.check({"good": 0.9, "liar": 0.1}, a=1).accepted
    g2 = ClaimGate(ledger_dir=d)                      # replay the append-only ledgers
    assert g2.live.reliability("good") == g.live.reliability("good")
    assert g2.threshold.cutoff("bayes:hard") == g.threshold.cutoff("bayes:hard")
    lines = open(os.path.join(d, "claims.jsonl")).read().splitlines()
    assert len(lines) == 401 and json.loads(lines[-1])["mode"] == "bayes:hard"


def test_gate_translation_faithful_roundtrip_accepts():
    original = parse(SRC, "python")
    translated = parse(emit(original, "python"), "python")
    d = gate_translation(original, translated)
    assert isinstance(d, GateDecision) and d.accepted and d.eff >= 0.85
    assert set(d.scores) == {"geometric", "verification", "mercy_civ"}


def test_gate_translation_lossy_is_not_accepted():
    original = parse(SRC, "python")
    lossy = parse("x = 1", "python")
    d = gate_translation(original, lossy)
    assert d.eff == 0.385 and not d.accepted       # would pass the lax v1 0.35 floor
    assert d.eff < gate_translation(original, original).eff


def test_gate_translation_with_learning_gate(tmp_path):
    original = parse(SRC, "python")
    g = ClaimGate(ledger_dir=str(tmp_path))
    d = gate_translation(original, original, gate=g)
    assert d.status in {"ACCEPT", "HEDGE", "BLOCK"} and 0.0 <= d.eff <= 1.0
