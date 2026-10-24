from core.config import Condition
from core.transcript import Transcript, Turn, Word
from extract.extractor import _Extraction, _Insight, _Quote, render, to_insights
from extract.quotes import locate
from extract.schema import InsightType


def transcript(*lines: tuple[str, str]) -> Transcript:
    turns, t = [], 0.0
    for speaker, text in lines:
        words = []
        for tok in text.split():
            words.append(Word(text=tok, start=t, end=t + 0.4))
            t += 0.5
        turns.append(Turn(speaker=speaker, start=words[0].start, end=words[-1].end, words=words))
        t += 1.0
    return Transcript(meeting_id="ES2004c", condition=Condition.FARFIELD, turns=turns)


T = transcript(
    ("PM", "Okay so let's get started."),
    ("ID", "think they could get a bit easily lost. Yeah."),
    ("ME", "We decided on a rubber casing for the plastic shell."),
    ("UI", "I'll check the cost of voice recognition by Friday."),
)


def item(type_, quotes, **kw) -> _Insight:
    base = dict(type=type_, summary="s", owner=None, deadline=None, value=None, confidence=70,
                quotes=[_Quote(line=ln, text=tx) for ln, tx in quotes])
    return _Insight(**(base | kw))


def test_render_numbers_lines_with_time_and_speaker():
    assert render(T).splitlines()[2].startswith("L2 [00:")
    assert "] ME: We decided on a rubber casing" in render(T)


def test_locate_exact_and_neighbouring_line():
    turn, words, score = locate(T, 2, "a rubber casing for the plastic shell")
    assert (turn.speaker, score) == ("ME", 1.0)
    assert words[0].text == "a" and words[-1].text == "shell."
    assert locate(T, 0, "a rubber casing for the plastic shell")[0].speaker == "ME"  # cited 2 lines off


def test_locate_tolerates_restored_edge_word_but_not_inventions():
    hit = locate(T, 1, "I think they could get a bit easily lost")  # far-field dropped the "I"
    assert hit and hit[2] >= 0.8 and hit[1][0].text == "think"
    assert locate(T, 2, "we chose a titanium case after all") is None


def test_to_insights_rejects_unsupported_and_cleans_fields():
    raw = _Extraction(insights=[
        item(InsightType.DECISION, [(2, "a rubber casing for the plastic shell")], owner="ME"),
        item(InsightType.ACTION_ITEM, [(3, "I'll check the cost of voice recognition")],
             owner="UI", deadline="Friday"),
        item(InsightType.COST_FIGURE, [(3, "the cost of voice recognition")]),  # no value
        item(InsightType.OPEN_RISK, [(0, "the factory cannot make curved cases")]),  # invented
    ])
    kept, rejected = to_insights(raw, T, run=0)
    assert [i.type for i in kept] == [InsightType.DECISION, InsightType.ACTION_ITEM]
    assert kept[0].owner is None  # owner dropped from a decision
    assert (kept[1].owner, kept[1].deadline, kept[1].evidence[0].speaker) == ("UI", "Friday", "UI")
    assert kept[1].id == "ES2004c.farfield.r0.001"
    assert sorted(r["reason"] for r in rejected) == ["no_value", "unsupported"]
