"""Load the GPU pod's faster-whisper + pyannote output as a Transcript.

In:  data/asr/{meeting}.{condition}.json and .diar.json (from gpu/transcribe.py)
Out: Transcript with word confidences and anonymous speakers, plus the diarization turns.
"""

import json

from core.config import ASR_OUT, Condition
from core.transcript import Transcript, Word
from pipeline.diarize import assign_speakers, group_turns


def load_asr(meeting_id: str, condition: Condition | str) -> tuple[Transcript, list[dict]]:
    stem = f"{meeting_id}.{Condition(condition)}"
    asr = json.loads((ASR_OUT / f"{stem}.json").read_text(encoding="utf-8"))
    diar = json.loads((ASR_OUT / f"{stem}.diar.json").read_text(encoding="utf-8"))
    diar_turns = diar["exclusive_turns"] or diar["turns"]

    words = [Word(text=w["text"], start=w["start"], end=w["end"], conf=w["prob"])
             for w in asr["words"] if w["text"]]
    turns = group_turns(words, assign_speakers(words, diar_turns))
    return Transcript(meeting_id=meeting_id, condition=Condition(condition), turns=turns), diar_turns
