"""One transcript format for every condition, human or ASR.

Human transcripts have conf=None; ASR words carry the recognizer's word probability.
Speakers are AMI roles (PM/ME/UI/ID). After alignment each word also records whether it
matched the human transcript and who really said it, which is what error attribution reads.
"""

from typing import Literal

from pydantic import BaseModel, Field

from core.config import TRANSCRIPTS, Condition

Match = Literal["ok", "sub", "ins"]  # matched / misheard / not in the human transcript


class Word(BaseModel):
    text: str
    start: float
    end: float
    conf: float | None = None
    match: Match | None = None       # None for CLEAN and for words that normalize away
    ref_speaker: str | None = None   # true speaker; differs from the turn's speaker on a mix-up


class Turn(BaseModel):
    speaker: str
    start: float
    end: float
    words: list[Word] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


class Transcript(BaseModel):
    meeting_id: str
    condition: Condition
    turns: list[Turn]

    @property
    def duration(self) -> float:
        return max((t.end for t in self.turns), default=0.0)

    def words(self) -> list[tuple[Word, str]]:
        """Every word with its turn's speaker, in time order."""
        return sorted(((w, t.speaker) for t in self.turns for w in t.words),
                      key=lambda ws: ws[0].start)


def transcript_path(meeting_id: str, condition: Condition | str):
    return TRANSCRIPTS / f"{meeting_id}.{Condition(condition)}.json"


def save_transcript(t: Transcript) -> None:
    path = transcript_path(t.meeting_id, t.condition)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(t.model_dump_json(exclude_none=True), encoding="utf-8")


def load_transcript(meeting_id: str, condition: Condition | str) -> Transcript:
    return Transcript.model_validate_json(
        transcript_path(meeting_id, condition).read_text(encoding="utf-8"))
