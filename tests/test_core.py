import pytest
from pydantic import ValidationError

from core.config import PRIMARY_SERIES, Condition, meetings
from core.jsonl import read_jsonl, write_jsonl
from core.transcript import Transcript, Turn, Word
from extract.schema import Insight, InsightType, Quote

QUOTE = Quote(text="let's go with the rubber case", speaker="ID", start=812.4, end=814.1)


def make(**kw) -> Insight:
    base = dict(id="i1", meeting_id="ES2004c", condition=Condition.FARFIELD,
                type=InsightType.DECISION, summary="Rubber case chosen", evidence=[QUOTE])
    return Insight(**(base | kw))


def test_meetings_are_four_per_series():
    ids = meetings(PRIMARY_SERIES)
    assert len(ids) == 4 * len(PRIMARY_SERIES)
    assert ids[:4] == ["ES2004a", "ES2004b", "ES2004c", "ES2004d"]


def test_insight_requires_evidence():
    with pytest.raises(ValidationError):
        make(evidence=[])


def test_cost_figure_requires_value():
    with pytest.raises(ValidationError):
        make(type=InsightType.COST_FIGURE)
    assert make(type=InsightType.COST_FIGURE, value="12.50 EUR").crm_property == "budget"


def test_owner_only_on_action_items():
    with pytest.raises(ValidationError):
        make(owner="PM")
    assert make(type=InsightType.ACTION_ITEM, owner="PM").owner == "PM"


def test_jsonl_round_trip(tmp_path):
    t = Transcript(meeting_id="ES2004a", condition=Condition.HEADSET, turns=[
        Turn(speaker="PM", start=0.0, end=1.2,
             words=[Word(text="okay", start=0.0, end=0.4, conf=0.91),
                    Word(text="everyone", start=0.5, end=1.2, conf=0.62)])])
    path = tmp_path / "t.jsonl"
    assert write_jsonl(path, [t, make()]) == 2
    rows = list(read_jsonl(path))
    assert Transcript.model_validate(rows[0]).turns[0].text == "okay everyone"
    assert Insight.model_validate(rows[1]).condition == Condition.FARFIELD
