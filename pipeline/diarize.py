"""Attach pyannote speaker turns to ASR words, then group words into turns.

Speakers stay anonymous (SPEAKER_xx) here; pipeline.align maps them to AMI roles.
"""

from bisect import bisect_right

from core.transcript import Turn, Word


def assign_speakers(words: list[Word], turns: list[dict]) -> list[str]:
    """Speaker of the non-overlapping turn covering each word's midpoint, else the nearest turn."""
    turns = sorted(turns, key=lambda t: t["start"])
    starts = [t["start"] for t in turns]
    speakers = []
    for w in words:
        mid = (w.start + w.end) / 2
        i = bisect_right(starts, mid) - 1
        candidates = [turns[j] for j in (i, i + 1) if 0 <= j < len(turns)]
        best = min(candidates, key=lambda t: 0.0 if t["start"] <= mid <= t["end"]
                   else min(abs(mid - t["start"]), abs(mid - t["end"])))
        speakers.append(best["speaker"])
    return speakers


def group_turns(words: list[Word], speakers: list[str], max_gap: float = 2.0) -> list[Turn]:
    """Consecutive words by the same speaker form a turn; a long pause also ends one."""
    turns: list[Turn] = []
    for w, spk in zip(words, speakers):
        last = turns[-1] if turns else None
        if last and last.speaker == spk and w.start - last.end <= max_gap:
            last.words.append(w)
            last.end = w.end
        else:
            turns.append(Turn(speaker=spk, start=w.start, end=w.end, words=[w]))
    return turns
