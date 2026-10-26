"""SPEAKER_SWAP condition: human words with a target share of WORDS given to the wrong role.

Isolates speaker mix-ups from mishearing. The dose is a word-level rate (matching how the
far-field speaker error is measured): turns are visited in a seeded random order and a turn is
relabelled only if doing so moves the share of relabelled words closer to the target. The
achieved rate is returned and recorded, and is within TOLERANCE of the target unless a single
turn is too long to land closer (then the closest reachable rate is used).

Caveat: these are synthetic, whole-turn swaps. Real diarization errors also split turns and
cluster around overlaps and speaker changes, so this is a dose-matched control, not a replica.
"""

import random

from core.config import Condition
from core.transcript import Transcript

TOLERANCE = 0.005  # achieved word share within half a percentage point of the target


def swap_speakers(clean: Transcript, rate: float, seed: int = 0) -> tuple[Transcript, float]:
    """Return the SPEAKER_SWAP transcript and the word share actually relabelled."""
    rng = random.Random(f"{clean.meeting_id}:{seed}")
    roles = sorted({t.speaker for t in clean.turns})
    total = sum(len(t.words) for t in clean.turns) or 1
    order = list(range(len(clean.turns)))
    rng.shuffle(order)

    sizes = [len(t.words) for t in clean.turns]
    chosen, moved = set(), 0
    gap = lambda m: abs(m / total - rate)  # noqa: E731
    # Local search: add a turn, or drop a chosen one, whenever that moves closer to the target.
    for _ in range(4):
        for i in order:
            delta = -sizes[i] if i in chosen else sizes[i]
            if gap(moved + delta) < gap(moved):
                chosen.symmetric_difference_update({i})
                moved += delta
            if gap(moved) <= TOLERANCE:
                break
        if gap(moved) <= TOLERANCE:
            break
        # Exchange move: replace one chosen turn with an unchosen one of a better length.
        best = None
        for i in chosen:
            for j in order:
                if j not in chosen and gap(moved - sizes[i] + sizes[j]) < gap(moved) and (
                        best is None or gap(moved - sizes[i] + sizes[j]) < gap(moved - sizes[best[0]] + sizes[best[1]])):
                    best = (i, j)
        if best is None:
            break  # closest reachable rate
        chosen.discard(best[0])
        chosen.add(best[1])
        moved += sizes[best[1]] - sizes[best[0]]

    turns = []
    for i, t in enumerate(clean.turns):
        new = t.model_copy(deep=True)
        for w in new.words:
            w.ref_speaker = t.speaker
        if i in chosen:
            new.speaker = rng.choice([r for r in roles if r != t.speaker])
        turns.append(new)
    swapped = Transcript(meeting_id=clean.meeting_id, condition=Condition.SPEAKER_SWAP, turns=turns)
    return swapped, moved / total
