"""One transcript format for every condition, human or ASR.

Human transcripts have conf=None; ASR words carry the recognizer's word probability.
Speakers are AMI roles (PM/ME/UI/ID) once diarization labels are mapped by pipeline.align.
"""

from pydantic import BaseModel, Field

from core.config import Condition


class Word(BaseModel):
    text: str
    start: float
    end: float
    conf: float | None = None


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
        return self.turns[-1].end if self.turns else 0.0
