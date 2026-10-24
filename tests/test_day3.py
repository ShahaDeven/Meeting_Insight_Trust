import pytest

from evals.attribution import _decompose
from evals.audit_final import derive, wilson
from extract.memory_strategies import Slot, _Op, apply_ops
from extract.schema import InsightType

D = InsightType.DECISION


def op(action, slot, value="v", insight=1) -> _Op:
    return _Op(action=action, slot=slot, category=D, value=value, insight=insight)


def test_ledger_applies_only_cited_and_consistent_ops():
    prev = [Slot(slot="Power source", category=D, value="rechargeable")]
    slots, info = apply_ops(prev, [
        op("update", "power source", "kinetic"),        # ok: existing slot, case-insensitive
        op("add", "Case", "rubber"),                     # ok: new slot
        op("update", "Screen", "LCD"),                   # rejected: update of a missing slot
        op("add", "power source", "solar"),              # rejected: add of an existing slot
        op("add", "Colour", "fruit", insight=9),         # rejected: cites a nonexistent insight
        op("retire", "Case", None),                      # rejected: no value
    ], n_insights=3)
    assert {s.slot: s.value for s in slots} == {"Power source": "kinetic", "Case": "rubber"}
    assert info == {"ops": 6, "applied": 2, "rejected": 4}


def test_ledger_without_evidence_keeps_the_old_value():
    prev = [Slot(slot="Task", category=InsightType.ACTION_ITEM, value="ME: research (open)")]
    slots, info = apply_ops(prev, [], n_insights=0)
    assert slots == prev and info["applied"] == 0


def test_final_audit_verdict_is_derived_from_rule_answers():
    assert derive(["yes", "yes", "n-a", "n-a"]) == "correct"
    assert derive(["yes", "no", "n-a", "yes"]) == "wrong"
    assert derive(["yes", "unsure", "n-a", "n-a"]) == "unsure"
    assert derive(["yes", None, None, None]) == "unsure"  # rules 1-2 must be answered
    lo, hi = wilson(19, 29)
    assert 0.46 < lo < 0.48 and 0.79 < hi < 0.81


def test_ladder_decomposition_shares_sum_to_one():
    d = _decompose({"clean": 0.125, "speaker_swap": 0.132, "headset": 0.177, "farfield": 0.193})
    assert d["farfield_mishearing_adds"] == pytest.approx(0.061)
    assert (d["farfield_share_model"] + d["farfield_share_speaker"]
            + d["farfield_share_mishearing"]) == pytest.approx(1.0)


def test_gate_auto_writes_only_quote_backed_changes():
    from core.config import Condition
    from core.transcript import Transcript, Turn, Word
    from extract.memory_strategies import _changes, _Check, apply_checks

    words = [Word(text=w, start=i, end=i + 0.5) for i, w in enumerate("we will use kinetic charging".split())]
    t = Transcript(meeting_id="m", condition=Condition.CLEAN,
                   turns=[Turn(speaker="ID", start=0, end=5, words=words)])
    prev = [Slot(slot="Power", category=D, value="rechargeable"),
            Slot(slot="Colour", category=D, value="grey")]
    proposed = [Slot(slot="Power", category=D, value="kinetic"),
                Slot(slot="Case", category=D, value="rubber")]       # Colour removed
    changes = _changes(prev, proposed)
    assert [(n, old) for n, old, _ in changes] == [("Power", "rechargeable"), ("Case", None),
                                                   ("Colour", "grey")]
    checks = {1: _Check(change=1, supported=True, line=0, quote="use kinetic charging"),
              2: _Check(change=2, supported=True, line=0, quote="the case is made of rubber"),
              3: _Check(change=3, supported=False, line=None, quote=None)}
    record, info = apply_checks(prev, changes, checks, t)
    assert {s.slot: s.value for s in record} == {"Power": "kinetic", "Colour": "grey"}
    assert (info["auto"], info["review"]) == (1, 2)
    assert info["queue"][0]["verifier_said"] == "supported, quote not found"
