"""Per-insight risk features: only what a production system has at write time.

Allowed: the insight itself, the extractor's output, the transcript it was extracted from
(words, recognizer confidences, speaker turns). Not allowed: anything derived from the human
transcript or the alignment to it (match / ref_speaker), which would leak the label.

  python -m risk.features
Out: data/results/risk_features.csv (one row per judged insight)
"""

import re

import numpy as np
import pandas as pd

from core.config import INSIGHTS, RESULTS, Condition
from core.jsonl import read_jsonl
from core.transcript import Transcript, load_transcript
from evals.audit_sheet import current_verdicts
from extract.schema import Insight, InsightType

HEDGES = re.compile(r"\b(maybe|might|could|perhaps|probably|possibly|i think|i guess|"
                    r"i suppose|not sure|should we|what if|or something|kind of|sort of)\b|\?")
AGREES = re.compile(r"\b(decided|agreed|let's|we'll|we will|we're going to|we are going to|"
                    r"go with|settled|definitely|final)\b")
WINDOW = 10.0  # seconds either side of a quote for turn density


def _quote_words(t: Transcript, ins: Insight):
    for q in ins.evidence:
        for turn in t.turns:
            for w in turn.words:
                if q.start <= w.start <= q.end:
                    yield w


def features(ins: Insight, t: Transcript) -> dict:
    words = list(_quote_words(t, ins))
    confs = [w.conf for w in words if w.conf is not None]
    asr = bool(confs)
    text = " ".join(q.text.lower() for q in ins.evidence)
    lo = min(q.start for q in ins.evidence) - WINDOW
    hi = max(q.end for q in ins.evidence) + WINDOW
    near = [turn for turn in t.turns if turn.end >= lo and turn.start <= hi]
    all_confs = [w.conf for turn in t.turns for w in turn.words if w.conf is not None]
    row = {f"type_{k}": int(ins.type == k) for k in InsightType}
    row |= {
        "owner_team": int(ins.owner == "team"),
        "owner_named": int(ins.owner not in (None, "team")),
        "has_value": int(ins.value is not None),
        "has_deadline": int(ins.deadline is not None),
        "model_confidence": ins.model_confidence or 0,
        "n_quotes": len(ins.evidence),
        "quote_words": len(words),
        "min_match_score": min(q.match_score for q in ins.evidence),
        "is_asr": int(asr),
        # Human transcripts have no recognizer confidence; treat them as fully confident.
        "quote_conf_mean": float(np.mean(confs)) if asr else 1.0,
        "quote_conf_min": float(min(confs)) if asr else 1.0,
        "quote_low_conf_share": float(np.mean([c < 0.5 for c in confs])) if asr else 0.0,
        "meeting_conf_mean": float(np.mean(all_confs)) if all_confs else 1.0,
        "hedges": len(HEDGES.findall(text)),
        "agrees": len(AGREES.findall(text)),
        "turns_nearby": len(near),
        "speakers_nearby": len({turn.speaker for turn in near}),
        "quote_speakers": len({q.speaker for q in ins.evidence}),
    }
    return row


def build() -> pd.DataFrame:
    verdicts, cache, rows = current_verdicts(), {}, []
    for f in sorted(INSIGHTS.glob("*.r*.jsonl")):
        if f.name.endswith(".rejected.jsonl"):
            continue
        for ins in read_jsonl(f, Insight):
            v = verdicts.get(ins.id)
            if v is None or v["verdict"] == "unsure":
                continue
            key = (ins.meeting_id, ins.condition)
            if key not in cache:
                cache[key] = load_transcript(*key)
            rows.append({"insight_id": ins.id, "meeting": ins.meeting_id,
                         "series": ins.meeting_id[:-1], "condition": str(ins.condition),
                         "run": ins.run, "wrong": int(v["verdict"] == "wrong"),
                         "failure": v["failure"], **features(ins, cache[key])})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build()
    RESULTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS / "risk_features.csv", index=False)
    print(f"{len(df)} insights, {df.wrong.mean():.1%} wrong (judge v2).")
    print(df.groupby("wrong")[["model_confidence", "quote_conf_min", "hedges", "agrees",
                               "turns_nearby"]].mean().round(2).to_string())
