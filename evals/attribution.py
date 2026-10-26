"""Attribute wrong insights to mishearing, speaker mix-ups, or the model.

The ladder is the attribution: the same meetings, extracted from four transcripts that differ
in one thing at a time. Wrong-rate at CLEAN is the model's own error; SPEAKER_SWAP minus CLEAN
is what speaker confusion adds (dose matched to each meeting's far-field speaker error);
HEADSET/FARFIELD minus SPEAKER_SWAP is what mishearing adds. Shares of the noisy wrong-rate
and their 95% CIs come from resampling whole recording series.

Read as exploratory: the swap is a dose-matched synthetic control (whole-turn relabels), not a
replica of real diarization errors; labels come from a strict LLM judge with fair agreement
(kappa 0.27) with a human; and mishearing and speaker errors can interact on the same insight
(see interaction()), so the shares are a decomposition of rates, not exclusive causes.

Per-insight evidence signals (misheard / dropped / wrong-speaker words around the quote) are
kept as risk-model features and as a control, NOT as per-insight causes: on this data they are
about as common under correct insights as under wrong ones, i.e. noise damage is mostly
non-local (a lost reversal or hedge elsewhere), not garbled words in the insight's own quote.

  python -m evals.attribution
Out: data/results/attribution_insights.csv, data/results/attribution_ladder.csv
"""

import random
from collections import defaultdict

import pandas as pd

from core.config import INSIGHTS, RESULTS, Condition
from core.jsonl import read_jsonl
from core.transcript import Transcript, load_transcript
from evals.audit_sheet import current_verdicts
from extract.schema import Insight
from pipeline.text import tokens

LADDER = [Condition.CLEAN, Condition.SPEAKER_SWAP, Condition.HEADSET, Condition.FARFIELD]
DROP_PAD = 1.0       # seconds around a quote checked for dropped words
DROP_SHARE = 0.2     # share of real words missing from the window that counts as "dropped"


def _clean_tokens(clean: Transcript, start: float, end: float) -> int:
    return sum(len(tokens(w.text)) for t in clean.turns for w in t.words if start <= w.start <= end)


def evidence_signals(ins: Insight, asr: Transcript, clean: Transcript) -> dict:
    """What went wrong in the transcript under this insight's quotes."""
    misheard = wrong_speaker = heard = 0
    real = 0
    for q in ins.evidence:
        lo, hi = q.start - DROP_PAD, q.end + DROP_PAD
        for turn in asr.turns:
            for w in turn.words:
                if lo <= w.start <= hi:
                    n = len(tokens(w.text))
                    if q.start <= w.start <= q.end and w.match in ("sub", "ins"):
                        misheard += 1
                    if w.match != "ins":  # None = human words (SPEAKER_SWAP), never misheard
                        heard += n
                    if (q.start <= w.start <= q.end and w.ref_speaker
                            and w.ref_speaker != turn.speaker):
                        wrong_speaker += 1
        real += _clean_tokens(clean, lo, hi)
    dropped = max(0.0, 1 - heard / real) if real else 0.0
    return {"misheard_words": misheard, "wrong_speaker_words": wrong_speaker,
            "dropped_share": round(dropped, 3)}


def per_insight(verdicts: dict) -> pd.DataFrame:
    rows, cache = [], {}
    for f in sorted(INSIGHTS.glob("*.r*.jsonl")):
        if f.name.endswith(".rejected.jsonl"):
            continue
        for ins in read_jsonl(f, Insight):
            v = verdicts.get(ins.id)
            if v is None:
                continue
            row = {"insight_id": ins.id, "meeting": ins.meeting_id, "series": ins.meeting_id[:-1],
                   "condition": str(ins.condition), "run": ins.run, "type": str(ins.type),
                   "verdict": v["verdict"], "failure": v["failure"],
                   "model_confidence": ins.model_confidence}
            if ins.condition != Condition.CLEAN:
                key = (ins.meeting_id, ins.condition)
                if key not in cache:
                    cache[key] = (load_transcript(*key), load_transcript(ins.meeting_id, "clean"))
                row |= evidence_signals(ins, *cache[key])
            rows.append(row)
    return pd.DataFrame(rows)


def _decompose(r: dict) -> dict:
    """Added wrong-rate per rung, and each source's share of the noisy wrong-rate."""
    out = {"speaker_adds": r["speaker_swap"] - r["clean"]}
    for asr in ("headset", "farfield"):
        out[f"{asr}_mishearing_adds"] = r[asr] - r["speaker_swap"]
        out[f"{asr}_share_model"] = r["clean"] / r[asr]
        out[f"{asr}_share_speaker"] = (r["speaker_swap"] - r["clean"]) / r[asr]
        out[f"{asr}_share_mishearing"] = (r[asr] - r["speaker_swap"]) / r[asr]
    return out


def control(df: pd.DataFrame) -> pd.DataFrame:
    """How often each evidence signal sits under correct vs wrong insights."""
    d = df[df.verdict.isin(["correct", "wrong"]) & (df.condition != "clean")].copy()
    d["misheard_in_quote"] = d.misheard_words > 0
    d["dropped_over_20pct"] = d.dropped_share > DROP_SHARE
    d["wrong_speaker_in_quote"] = d.wrong_speaker_words > 0
    return d.groupby(["condition", "verdict"])[
        ["misheard_in_quote", "dropped_over_20pct", "wrong_speaker_in_quote"]].mean()


def ladder(df: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Wrong-rate per condition (unsure excluded). CIs resample whole recording series.

    Meetings in a series share a team, room and microphone, so they are not independent: the
    bootstrap draws the 6 series with replacement (and keeps each series' 4 meetings together).
    With 6 groups these intervals are wide, which is the honest reading.
    """
    d = df[df.verdict.isin(["correct", "wrong"])]
    per = d.groupby(["series", "condition"]).verdict.agg(
        wrong=lambda s: (s == "wrong").sum(), n="size").reset_index()
    series = sorted(per.series.unique())
    table = per.pivot(index="series", columns="condition", values=["wrong", "n"]).fillna(0)

    def rates(ss):
        sub = table.loc[ss]
        return {c: sub["wrong"][c].sum() / sub["n"][c].sum() for c in map(str, LADDER)}

    point = rates(series)
    rng = random.Random(seed)
    boots = defaultdict(list)
    for _ in range(n_boot):
        r = rates([rng.choice(series) for _ in series])
        for c, v in r.items():
            boots[c].append(v)
        for k, v in _decompose(r).items():
            boots[k].append(v)
    point |= _decompose(point)
    out = []
    for k, v in point.items():
        b = sorted(boots[k])
        out.append({"measure": k, "value": v, "ci_low": b[int(0.025 * n_boot)],
                    "ci_high": b[int(0.975 * n_boot)]})
    return pd.DataFrame(out)


def interaction(df: pd.DataFrame) -> pd.DataFrame:
    """Exploratory: wrong-rate of far-field/headset insights by which signals sit under the quote.

    Asks whether dropped/misheard words and speaker mix-ups compound on the same insight. These
    are associations within one condition, not causal effects.
    """
    d = df[df.verdict.isin(["correct", "wrong"]) & df.condition.isin(["headset", "farfield"])].copy()
    d["heard_badly"] = (d.misheard_words > 0) | (d.dropped_share > DROP_SHARE)
    d["speaker_mixed"] = d.wrong_speaker_words > 0
    return (d.groupby(["heard_badly", "speaker_mixed"])
             .agg(insights=("verdict", "size"), wrong_rate=("verdict", lambda v: (v == "wrong").mean()))
             .reset_index())


def main() -> None:
    df = per_insight(current_verdicts())
    RESULTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS / "attribution_insights.csv", index=False)
    lad = ladder(df)
    lad.to_csv(RESULTS / "attribution_ladder.csv", index=False)
    ctl = control(df)
    ctl.to_csv(RESULTS / "attribution_control.csv")
    inter = interaction(df)
    inter.to_csv(RESULTS / "attribution_interaction.csv", index=False)

    print("EXPLORATORY. Wrong-rate ladder and decomposition (unsure excluded; 95% CI resampling series):")
    for r in lad.itertuples():
        print(f"  {r.measure:28s} {r.value:6.1%}   [{r.ci_low:6.1%}, {r.ci_high:6.1%}]")
    print("\nControl: share of insights with each signal around their quote")
    print(ctl.map(lambda x: f"{x:.0%}").to_string())
    print("\nInteraction (ASR conditions; association only):")
    print(inter.to_string(index=False, formatters={"wrong_rate": "{:.1%}".format}))


if __name__ == "__main__":
    main()
