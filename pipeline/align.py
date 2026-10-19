"""Align an ASR transcript to the AMI human transcript.

- map_roles: anonymous diarization speakers -> AMI roles by maximum total time overlap
  (one-to-one). A real meeting bot gets names from the platform; this is that oracle mapping,
  so remaining speaker errors are words put in the wrong speaker's cluster.
- align: word-level alignment on normalized tokens. Each ASR word gets match (ok/sub/ins)
  and ref_speaker (who said the human-transcript word it aligned to).
"""

from collections import Counter

import jiwer
import numpy as np
from scipy.optimize import linear_sum_assignment

from core.transcript import Transcript
from pipeline.text import tokens


def map_roles(diar_turns: list[dict], clean: Transcript) -> dict[str, str]:
    speakers = sorted({t["speaker"] for t in diar_turns})
    roles = sorted({t.speaker for t in clean.turns})
    cs = np.array([t.start for t in clean.turns])
    ce = np.array([t.end for t in clean.turns])
    cr = np.array([roles.index(t.speaker) for t in clean.turns])
    overlap = np.zeros((len(speakers), len(roles)))
    for t in diar_turns:
        ov = np.clip(np.minimum(ce, t["end"]) - np.maximum(cs, t["start"]), 0, None)
        overlap[speakers.index(t["speaker"])] += np.bincount(cr, weights=ov, minlength=len(roles))
    rows, cols = linear_sum_assignment(-overlap)
    mapping = {s: s for s in speakers}  # extra clusters keep their anonymous label
    mapping.update({speakers[r]: roles[c] for r, c in zip(rows, cols)})
    return mapping


def relabel(t: Transcript, mapping: dict[str, str]) -> None:
    for turn in t.turns:
        turn.speaker = mapping.get(turn.speaker, turn.speaker)


def align(clean: Transcript, asr: Transcript) -> dict:
    """Annotate asr words in place; return error counts for this meeting."""
    ref_tok, ref_spk = [], []
    for w, spk in clean.words():
        for tok in tokens(w.text):
            ref_tok.append(tok)
            ref_spk.append(spk)

    hyp_words = asr.words()
    hyp_tok, hyp_owner = [], []
    for i, (w, _) in enumerate(hyp_words):
        for tok in tokens(w.text):
            hyp_tok.append(tok)
            hyp_owner.append(i)

    out = jiwer.process_words(" ".join(ref_tok), " ".join(hyp_tok))
    status: list[str] = [""] * len(hyp_tok)
    true_spk: list[str | None] = [None] * len(hyp_tok)
    for chunk in out.alignments[0]:
        for k, h in enumerate(range(chunk.hyp_start_idx, chunk.hyp_end_idx)):
            if chunk.type == "insert":
                status[h] = "ins"
            else:  # equal / substitute pair hyp and ref tokens one-to-one
                status[h] = "ok" if chunk.type == "equal" else "sub"
                true_spk[h] = ref_spk[chunk.ref_start_idx + k]

    per_word: dict[int, list[int]] = {}
    for h, i in enumerate(hyp_owner):
        per_word.setdefault(i, []).append(h)
    spk_checked = spk_wrong = 0
    for i, hs in per_word.items():
        w, spk = hyp_words[i]
        sts = {status[h] for h in hs}
        w.match = "ok" if sts == {"ok"} else "ins" if sts == {"ins"} else "sub"
        voices = Counter(true_spk[h] for h in hs if true_spk[h])
        if voices:
            w.ref_speaker = voices.most_common(1)[0][0]
            spk_checked += 1
            spk_wrong += w.ref_speaker != spk

    n = len(ref_tok)
    return {"ref_tokens": n, "wer": out.wer, "sub": out.substitutions / n,
            "del": out.deletions / n, "ins": out.insertions / n,
            "speaker_err": spk_wrong / max(spk_checked, 1)}
