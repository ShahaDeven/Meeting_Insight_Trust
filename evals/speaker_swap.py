"""SPEAKER_SWAP condition: human words with a share of turns given to the wrong role.

Isolates speaker mix-ups from mishearing. Every word keeps its true speaker in ref_speaker,
so attribution can tell exactly which words were relabeled. Seeded per meeting.
"""

import random

from core.config import Condition
from core.transcript import Transcript


def swap_speakers(clean: Transcript, rate: float, seed: int = 0) -> Transcript:
    rng = random.Random(f"{clean.meeting_id}:{seed}")
    roles = sorted({t.speaker for t in clean.turns})
    turns = []
    for t in clean.turns:
        new = t.model_copy(deep=True)
        for w in new.words:
            w.ref_speaker = t.speaker
        if rng.random() < rate:
            new.speaker = rng.choice([r for r in roles if r != t.speaker])
        turns.append(new)
    return Transcript(meeting_id=clean.meeting_id, condition=Condition.SPEAKER_SWAP, turns=turns)
