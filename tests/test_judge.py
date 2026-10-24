from core.config import Condition
from core.transcript import Transcript, Turn, Word
from evals.judge import describe, truth_excerpt
from extract.schema import Insight, InsightType, Quote


def turn(speaker: str, start: float, text: str) -> Turn:
    words = [Word(text=t, start=start + i, end=start + i + 0.5) for i, t in enumerate(text.split())]
    return Turn(speaker=speaker, start=start, end=words[-1].end, words=words)


CLEAN = Transcript(meeting_id="m", condition=Condition.CLEAN, turns=[
    turn("PM", 0, "welcome everyone"),
    turn("UI", 100, "I will check the cost"),
    turn("ME", 110, "sounds good"),
    turn("ID", 300, "rubber case then"),
])


def insight(*spans: tuple[float, float], **kw) -> Insight:
    base = dict(id="m.farfield.r0.000", meeting_id="m", condition=Condition.FARFIELD,
                type=InsightType.ACTION_ITEM, summary="UI checks the cost", owner="ME",
                evidence=[Quote(text="x", speaker="ME", start=s, end=e) for s, e in spans])
    return Insight(**(base | kw))


def test_excerpt_shows_true_speakers_within_window():
    text = truth_excerpt(CLEAN, insight((101, 104)), pad=20)
    assert text.splitlines() == ["[01:40] UI: I will check the cost", "[01:50] ME: sounds good"]


def test_excerpt_merges_close_quotes_and_splits_far_ones():
    assert "..." not in truth_excerpt(CLEAN, insight((101, 102), (110, 111)), pad=20)
    far = truth_excerpt(CLEAN, insight((101, 102), (300, 301)), pad=20)
    assert far.count("\n...\n") == 1 and "ID: rubber case then" in far


def test_excerpt_window_with_no_speech_says_so():
    assert truth_excerpt(CLEAN, insight((200, 201)), pad=20) == "(nothing was said in this window)"


def test_describe_never_names_the_condition():
    d = describe(insight((101, 104)))
    assert "Owner: ME" in d and "farfield" not in d
