"""Guards the review asked for: spend cap, label leakage, series isolation, quote bounds,
write policy, and deterministic evaluation. No API calls, no corpus data."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from core.config import Condition
from core.llm import Budget, BudgetExceeded
from core.transcript import Transcript, Turn, Word
from extract.schema import Insight, InsightType, Quote
from risk import train
from risk.features import features
from risk.policy import COST, confusion, policy_flags


def usage(inp: int, out: int):
    return SimpleNamespace(input_tokens=inp, output_tokens=out,
                           cache_creation_input_tokens=0, cache_read_input_tokens=0)


def test_budget_charges_real_prices_and_stops_at_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("core.llm.USAGE_LOG", tmp_path / "usage.jsonl")
    b = Budget(max_usd=0.01)
    b.check()  # nothing spent yet
    cost = b.charge("claude-haiku-5-5", usage(50_000, 10_000), "test", 1.0)
    assert cost == pytest.approx((50_000 * 0.10 + 10_000 * 0.50) / 1e6)
    b.charge("claude-haiku-5-5", usage(50_000, 10_000), "test", 1.0)
    with pytest.raises(BudgetExceeded):
        b.check()
    assert len((tmp_path / "usage.jsonl").read_text().splitlines()) == 2


def test_quotes_must_have_ordered_nonnegative_times():
    Quote(text="ok", speaker="PM", start=1.0, end=1.0)
    with pytest.raises(ValidationError):
        Quote(text="ok", speaker="PM", start=5.0, end=4.0)
    with pytest.raises(ValidationError):
        Quote(text="ok", speaker="PM", start=-1.0, end=2.0)
    with pytest.raises(ValidationError):
        Quote(text="ok", speaker="PM", start=0, end=1, match_score=1.2)


def _asr(match: str | None, ref: str | None) -> Transcript:
    words = [Word(text=w, start=i, end=i + 0.5, conf=0.6, match=match, ref_speaker=ref)
             for i, w in enumerate("maybe we could use kinetic charging".split())]
    return Transcript(meeting_id="m", condition=Condition.FARFIELD,
                      turns=[Turn(speaker="ID", start=0, end=6, words=words)])


def test_risk_features_ignore_reference_derived_labels():
    ins = Insight(id="m.farfield.r0.000", meeting_id="m", condition=Condition.FARFIELD,
                  type=InsightType.DECISION, summary="Kinetic charging chosen", model_confidence=60,
                  evidence=[Quote(text="use kinetic charging", speaker="ID", start=3, end=5.5)])
    # Alignment fields (match, ref_speaker) come from the human transcript: changing them must
    # not change a single feature, or the risk model would be reading the answer key.
    assert features(ins, _asr(None, None)) == features(ins, _asr("sub", "PM"))
    assert not {c for c in features(ins, _asr(None, None)) if "match" in c and c != "min_match_score"}


def test_cross_validation_never_trains_on_the_held_out_series(monkeypatch):
    seen = []

    class Spy:
        def fit(self, X, y):
            self.train_series = set(X["series_tag"])
            return self

        def predict_proba(self, X):
            seen.append((self.train_series, set(X["series_tag"])))
            return np.tile([0.5, 0.5], (len(X), 1))

    monkeypatch.setattr(train, "models", lambda *a, **k: {"logistic": Spy(), "xgboost": Spy()})
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"insight_id": [f"i{k}" for k in range(60)], "meeting": "m", "condition": "farfield",
                       "series": np.repeat(["A", "B", "C"], 20), "wrong": rng.integers(0, 2, 60),
                       "model_confidence": 50, "quote_conf_min": 0.9})
    df["series_tag"] = df.series
    train.cross_val(df, ["series_tag"])
    assert seen and all(not (trained & tested) for trained, tested in seen)


def test_write_policy_reviews_when_expected_cost_exceeds_one_review():
    d = pd.DataFrame({"logistic": [0.10, 0.19, 0.21, 0.45, 0.55, 0.10],
                      "type": ["decision", "decision", "decision", "open_risk", "open_risk", "cost_figure"],
                      "wrong": [0, 1, 1, 0, 1, 1]})
    flags = policy_flags(d)
    assert flags.tolist() == [False, False, True, False, True, False]  # 0.10 < 1/8 for cost figures
    assert 1 / COST["cost_figure"] == pytest.approx(0.125)
    m = confusion(d.wrong.to_numpy(), flags)
    assert (m["recall_wrong"], m["precision_review"], m["review_rate"]) == (0.5, 1.0, pytest.approx(2 / 6))
    assert m["auto_error"] == pytest.approx(2 / 4)


def test_evaluation_is_deterministic():
    rng = np.random.default_rng(1)
    s = pd.DataFrame({"meeting": "m", "series": np.repeat(list("ABCDEF"), 30),
                      "condition": "farfield", "wrong": rng.integers(0, 2, 180)})
    for col in train.SCORES:
        s[col] = rng.random(180)
    a, b = train.evaluate(s, n_boot=200), train.evaluate(s, n_boot=200)
    pd.testing.assert_frame_equal(a, b)
