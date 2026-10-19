"""Text normalization so alignment compares words, not transcription conventions.

AMI spells numbers out, transcribes fillers and writes acronyms as "T_V_"; Whisper writes
digits, drops fillers and writes "TV". Both sides go through the same tokens() before alignment.

Remaining WER is dominated by deletions, and most of those sit in overlapping speech
(backchannels like "yeah"/"okay" under another speaker): Whisper transcribes one voice at a time.
"""

import re

from num2words import num2words

FILLERS = {"um", "uh", "mm", "hmm", "hm", "mm-hmm", "uh-huh", "um-hmm", "mm-mm", "uh-uh",
           "ah", "er", "erm", "eh"}
RESPELL = {"kay": "okay", "ok": "okay"}
SYMBOLS = {"€": " euro ", "£": " pound ", "$": " dollar ", "%": " percent ", "&": " and "}
NUMBER = re.compile(r"\d+(?:\.\d+)?")
TOKEN = re.compile(r"[a-z0-9'-]+")


def _spell(m: re.Match) -> str:
    s = m.group()
    return f" {num2words(float(s) if '.' in s else int(s))} "


def tokens(text: str) -> list[str]:
    # "1,000" -> "1000"; AMI spells acronyms "L_C_D_" where Whisper writes "LCD"
    t = text.lower().replace(",", "").replace("_", "")
    for sym, word in SYMBOLS.items():
        t = t.replace(sym, word)
    t = NUMBER.sub(_spell, t)
    out = []
    for tok in TOKEN.findall(t):
        tok = tok.strip("'")
        if not tok or tok in FILLERS or tok.endswith("-"):  # fragments like "th-"
            continue
        out.extend(RESPELL.get(p, p) for p in tok.split("-") if p)
    return out
