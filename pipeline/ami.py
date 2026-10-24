"""Parse the AMI manual annotations: speaker roles and the human transcript (CLEAN)."""

import re
import xml.etree.ElementTree as ET
from functools import cache

from core.config import AMI_RAW, Condition
from core.transcript import Transcript, Turn, Word

MANUAL = AMI_RAW / "manual"
NITE_ID = "{http://nite.sourceforge.net/}id"
HREF = re.compile(r"#id\(([^)]+)\)(?:\.\.id\(([^)]+)\))?")


@cache
def _meetings() -> ET.Element:
    return ET.parse(MANUAL / "corpusResources" / "meetings.xml").getroot()


def roles(meeting_id: str) -> dict[str, str]:
    """Speaker agent letter (A-D) -> role (PM/ME/UI/ID)."""
    for m in _meetings():
        if m.get("observation") == meeting_id:
            return {s.get("nxt_agent"): s.get("role") for s in m.iter("speaker")}
    raise KeyError(f"{meeting_id} not in meetings.xml")


def load_summary(meeting_id: str) -> dict[str, list[str]]:
    """AMI abstractive summary: sentences under abstract / actions / decisions / problems.

    Coarse gold: one sentence often bundles several decisions, and "NA" sections are empty.
    """
    root = ET.parse(MANUAL / "abstractive" / f"{meeting_id}.abssumm.xml").getroot()
    return {section.tag: [s.text.strip() for s in section.iter("sentence") if s.text]
            for section in root}


def load_clean(meeting_id: str) -> Transcript:
    """One turn per AMI segment, speaker = role. Punctuation is attached to the word before it."""
    turns = []
    for agent, role in roles(meeting_id).items():
        elems = list(ET.parse(MANUAL / "words" / f"{meeting_id}.{agent}.words.xml").getroot())
        index = {e.get(NITE_ID): i for i, e in enumerate(elems)}
        segments = ET.parse(MANUAL / "segments" / f"{meeting_id}.{agent}.segments.xml").getroot()
        for seg in segments:
            words: list[Word] = []
            for child in seg:
                m = HREF.search(child.get("href", ""))
                if not m:
                    continue
                first, last = index[m.group(1)], index[m.group(2) or m.group(1)]
                for e in elems[first:last + 1]:
                    if e.tag != "w" or not e.text or e.get("starttime") is None:
                        continue  # vocal sounds, gaps, disfluency markers
                    if e.get("punc") == "true":
                        if words:
                            words[-1].text += e.text
                        continue
                    start = float(e.get("starttime"))
                    words.append(Word(text=e.text, start=start,
                                      end=float(e.get("endtime") or start)))
            if words:
                turns.append(Turn(speaker=role, start=words[0].start, end=words[-1].end,
                                  words=words))
    turns.sort(key=lambda t: (t.start, t.end))
    return Transcript(meeting_id=meeting_id, condition=Condition.CLEAN, turns=turns)
