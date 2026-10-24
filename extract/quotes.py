"""Pin a model-cited quote to real transcript words, timestamps and speaker.

The model cites a line number and copies a quote. The quote is supported only if its
normalized tokens match a window of that line or a nearby one (token-level similarity
>= MIN_SCORE). The stored quote is the transcript's own words, so play-from-here and the
speaker check use ground truth, not the model's copy.
"""

from rapidfuzz.distance import Levenshtein

from core.transcript import Transcript, Turn, Word
from pipeline.text import tokens

MIN_SCORE = 0.8
NEIGHBOURS = 2  # line numbers drift by one or two when turns are short
SLACK = 2       # window may be this many tokens shorter/longer than the quote


def locate(t: Transcript, line: int, quote: str) -> tuple[Turn, list[Word], float] | None:
    q = tokens(quote)
    if not q:
        return None
    order = [line] + [line + d * s for d in range(1, NEIGHBOURS + 1) for s in (-1, 1)]
    best: tuple[Turn, list[Word], float] | None = None
    for i in order:
        if not 0 <= i < len(t.turns):
            continue
        turn = t.turns[i]
        toks, owner = [], []
        for wi, w in enumerate(turn.words):
            for tok in tokens(w.text):
                toks.append(tok)
                owner.append(wi)
        if not toks:
            continue
        # Windows a little shorter or longer than the quote absorb a dropped or added edge
        # word (e.g. far-field loses the "I" the model restores from context).
        sizes = {max(1, min(len(q) + d, len(toks))) for d in range(-SLACK, SLACK + 1)}
        for n in sorted(sizes, key=lambda n: abs(n - len(q))):  # ties go to the closest size
            for s in range(len(toks) - n + 1):
                score = Levenshtein.normalized_similarity(q, toks[s:s + n])
                if best is None or score > best[2]:
                    best = (turn, turn.words[owner[s]:owner[s + n - 1] + 1], score)
        if best and best[2] == 1.0:
            break  # exact match; nearer lines were searched first
    return best if best and best[2] >= MIN_SCORE else None
