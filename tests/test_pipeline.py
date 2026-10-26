import pytest
from core.config import Condition
from core.transcript import Transcript, Turn, Word
from evals.speaker_swap import swap_speakers
from pipeline.align import align, map_roles, relabel
from pipeline.diarize import assign_speakers, group_turns
from pipeline.text import tokens


def turn(speaker: str, start: float, text: str, conf: float | None = None) -> Turn:
    words = [Word(text=t, start=start + i, end=start + i + 0.8, conf=conf)
             for i, t in enumerate(text.split())]
    return Turn(speaker=speaker, start=start, end=words[-1].end, words=words)


def test_tokens_normalize_both_conventions():
    assert tokens("Um, it's 5 metres.") == ["it's", "five", "metres"]
    assert tokens("Mm-hmm") == []
    assert tokens("th- the remote-control") == ["the", "remote", "control"]
    assert tokens("'Kay, OK") == ["okay", "okay"]
    assert tokens("L_C_D_ T_V_s") == tokens("LCD TVs") == ["lcd", "tvs"]
    assert tokens("€12.50") == ["euro", "twelve", "point", "five"]


def test_assign_speakers_uses_covering_then_nearest_turn():
    words = [Word(text="a", start=0.1, end=0.3), Word(text="b", start=1.9, end=2.1),
             Word(text="c", start=5.0, end=5.2)]
    diar = [{"start": 0.0, "end": 1.0, "speaker": "S0"}, {"start": 1.5, "end": 3.0, "speaker": "S1"}]
    speakers = assign_speakers(words, diar)
    assert speakers == ["S0", "S1", "S1"]
    assert [t.speaker for t in group_turns(words, speakers)] == ["S0", "S1", "S1"]  # 2.9 s pause splits


def test_map_roles_is_one_to_one_by_overlap():
    clean = Transcript(meeting_id="m", condition=Condition.CLEAN,
                       turns=[turn("PM", 0, "a b c"), turn("ID", 10, "d e f")])
    diar = [{"start": 0, "end": 3, "speaker": "SPEAKER_01"},
            {"start": 10, "end": 13, "speaker": "SPEAKER_00"}]
    assert map_roles(diar, clean) == {"SPEAKER_01": "PM", "SPEAKER_00": "ID"}


def test_align_flags_mishearing_and_speaker_mixup():
    clean = Transcript(meeting_id="m", condition=Condition.CLEAN, turns=[
        turn("PM", 0, "we choose the rubber case"), turn("ID", 10, "i will ask manufacturing")])
    asr = Transcript(meeting_id="m", condition=Condition.FARFIELD, turns=[
        turn("S0", 0, "we choose the rubber cage", conf=0.9),
        turn("S0", 10, "i", conf=0.9), turn("S1", 11, "will ask manufacturing", conf=0.9)])
    relabel(asr, {"S0": "PM", "S1": "ID"})
    stats = align(clean, asr)

    words = asr.words()
    assert [w.match for w, _ in words[:5]] == ["ok", "ok", "ok", "ok", "sub"]
    i_word, i_speaker = words[5]
    assert (i_word.ref_speaker, i_speaker) == ("ID", "PM")  # "I" given to the wrong person
    assert stats["sub"] == 1 / 9 and stats["del"] == 0
    assert stats["speaker_err"] == 1 / 9


def _swap_clean() -> Transcript:
    # 40 turns of varied length (1-6 words) so word share and turn share differ.
    roles = ["PM", "ME", "UI", "ID"]
    return Transcript(meeting_id="m", condition=Condition.CLEAN,
                      turns=[turn(roles[i % 4], i * 10, " ".join(["w"] * (1 + i % 6))) for i in range(40)])


def _relabelled_share(t: Transcript) -> float:
    words = [(w, turn.speaker) for turn in t.turns for w in turn.words]
    return sum(w.ref_speaker != spk for w, spk in words) / len(words)


def test_speaker_swap_extremes_seeding_and_truth():
    clean = _swap_clean()
    none, r0 = swap_speakers(clean, rate=0.0)
    every, r1 = swap_speakers(clean, rate=1.0)
    assert r0 == 0 and [t.speaker for t in none.turns] == [t.speaker for t in clean.turns]
    assert r1 == 1 and all(t.speaker != t.words[0].ref_speaker for t in every.turns)
    assert swap_speakers(clean, 0.3)[0].model_dump() == swap_speakers(clean, 0.3)[0].model_dump()
    assert clean.turns[0].words[0].ref_speaker is None  # original untouched


@pytest.mark.parametrize("target", [0.02, 0.05, 0.08, 0.15, 0.25])
def test_speaker_swap_hits_intermediate_word_rates(target):
    from evals.speaker_swap import TOLERANCE
    swapped, achieved = swap_speakers(_swap_clean(), rate=target)
    assert achieved == pytest.approx(_relabelled_share(swapped))  # reported = measured
    assert abs(achieved - target) <= TOLERANCE  # one-word turns make every target reachable
