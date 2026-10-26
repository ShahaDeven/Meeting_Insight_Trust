"""Destination logic of the console export: deadlines onto the calendar, insights onto fields."""

from app.export import due_of, field_link
from core.config import Condition
from extract.schema import Insight, InsightType, Quote


def test_spoken_deadlines_map_onto_the_series_calendar():
    assert due_of("for the next meeting", "b") == {"kind": "meeting", "part": "c"}
    assert due_of("Next meeting", "d") == {"kind": "after"}           # no meeting after d
    assert due_of("before we finish today", "a") == {"kind": "meeting", "part": "a"}
    assert due_of("in about 10 minutes", "c") == {"kind": "text", "text": "in about 10 minutes"}
    assert due_of(None, "c") == {"kind": "none"}


def _insight(start: float) -> Insight:
    return Insight(id="m.farfield.r0.000", meeting_id="TS3003c", condition=Condition.FARFIELD,
                   type=InsightType.DECISION, summary="s",
                   evidence=[Quote(text="q", speaker="PM", start=start, end=start + 3)])


def test_insight_links_to_the_nearest_field_change_within_30_seconds():
    written = [{"slot": "power_source", "start": 100.0}, {"slot": "case", "start": 160.0},
               {"slot": "no_quote", "start": None}]
    assert field_link(_insight(110.0), written) == "power_source"
    assert field_link(_insight(150.0), written) == "case"
    assert field_link(_insight(400.0), written) is None   # nothing within 30 s
