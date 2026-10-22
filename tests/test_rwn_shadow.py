"""Seraphina RWN shadow hook: outputs are never altered, errors never reach the agent, no paid judges, portable paths."""
import json
import os

import pytest

from seraphina.rwn_shadow import ShadowHook, default_log_dir, split_claims


class Obj:
    pass


@pytest.mark.parametrize("engine", ["fallback", "auto"])
def test_output_passes_through_unchanged(tmp_path, engine):
    hook = ShadowHook(str(tmp_path / engine), engine=engine)
    for out in ("Vitamin D lowers the risk of infection. The sky is green today.", None, 42, ["a"], {"k": 1}, Obj()):
        assert hook.wrap(lambda x=out: x)() is out
    lines = open(tmp_path / engine / "fresh_claims.jsonl", encoding="utf-8").read().splitlines()
    assert len(lines) == 2                                      # two sentence claims from the text output
    assert all(json.loads(l)["outcome"] in ("NOT_SURE", "BLOCK") for l in lines)   # no trusted corpus: never ACCEPT


def test_agent_exceptions_propagate(tmp_path):
    hook = ShadowHook(str(tmp_path), engine="fallback")
    err = RuntimeError("agent")

    def bad():
        raise err
    with pytest.raises(RuntimeError) as e:
        hook.wrap(bad)()
    assert e.value is err


def test_hook_errors_are_swallowed(tmp_path):
    hook = ShadowHook(str(tmp_path), engine="fallback", extract=lambda o: 1 / 0)
    o = Obj()
    assert hook.wrap(lambda: o)() is o and hook.errors == 1


def test_fallback_log_is_hash_chained(tmp_path):
    hook = ShadowHook(str(tmp_path), engine="fallback")
    for c in ("first claim here.", "second claim here."):
        hook.observe(c)
    recs = [json.loads(l) for l in open(tmp_path / "fresh_claims.jsonl", encoding="utf-8")]
    assert recs[0]["prev"] == "0" * 64 and recs[1]["prev"] == recs[0]["hash"]


def test_paid_options_refused(tmp_path):
    with pytest.raises(ValueError):
        ShadowHook(str(tmp_path), profile="panel")
    with pytest.raises(ValueError):
        ShadowHook(str(tmp_path), engine="fallback", judges=object())
    with pytest.raises(ValueError):
        ShadowHook(str(tmp_path), engine="fallback", enforce=True)


def test_default_log_dir_is_portable(monkeypatch):
    monkeypatch.delenv("SERAPHINA_RWN_LOG_DIR", raising=False)
    assert default_log_dir().endswith(os.path.join("rwn_shadow"))
    monkeypatch.setenv("SERAPHINA_RWN_LOG_DIR", "X:\\logs")
    assert default_log_dir() == "X:\\logs"
    assert split_claims("One claim about something. Two claims about another!") == [
        "One claim about something.", "Two claims about another!"]
