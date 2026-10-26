"""Build all four transcript conditions for every meeting, plus an ASR quality table.

  python -m pipeline.build                      # all six series
  python -m pipeline.build --series ES2004      # one series
  python -m pipeline.build --swap-rate 0.1      # fixed swap rate instead of matched

Writes data/transcripts/{meeting}.{condition}.json and data/results/asr_quality.csv.
By default each meeting's swap targets its far-field word-level speaker error, so SPEAKER_SWAP
carries the same dose of speaker confusion as the real far-field run and nothing else. Target and
achieved word shares are recorded per meeting (swap_target, swap_achieved).
"""

import argparse

import pandas as pd

from core.config import RESULTS, SERIES, Condition, meetings
from core.transcript import save_transcript
from evals.speaker_swap import swap_speakers
from pipeline.align import align, map_roles, relabel
from pipeline.ami import load_clean
from pipeline.asr import load_asr


def build_meeting(mid: str, swap_rate: float | None) -> list[dict]:
    clean = load_clean(mid)
    save_transcript(clean)
    rows = []
    for cond in (Condition.HEADSET, Condition.FARFIELD):
        asr, diar_turns = load_asr(mid, cond)
        relabel(asr, map_roles(diar_turns, clean))
        stats = align(clean, asr)
        save_transcript(asr)
        confs = [w.conf for w, _ in asr.words()]
        rows.append({"meeting": mid, "series": mid[:-1], "condition": str(cond),
                     "minutes": round(clean.duration / 60, 1), "mean_conf": sum(confs) / len(confs),
                     **stats})
    target = rows[-1]["speaker_err"] if swap_rate is None else swap_rate
    swapped, achieved = swap_speakers(clean, target)
    save_transcript(swapped)
    for r in rows:
        r["swap_target"], r["swap_achieved"] = target, achieved
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--series", nargs="+", default=SERIES)
    p.add_argument("--swap-rate", type=float, default=None)
    args = p.parse_args()

    rows = []
    for mid in meetings(args.series):
        rows += build_meeting(mid, args.swap_rate)
        far = rows[-1]
        print(f"{mid}: headset WER {rows[-2]['wer']:.1%}, far-field WER {far['wer']:.1%}, "
              f"far-field speaker err {far['speaker_err']:.1%}, swap achieved {far['swap_achieved']:.1%}",
              flush=True)

    df = pd.DataFrame(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS / "asr_quality.csv", index=False)

    w = df.assign(wt=df.ref_tokens)
    cols = ["wer", "sub", "del", "ins", "speaker_err"]
    pooled = w.groupby("condition").apply(
        lambda g: pd.Series({c: (g[c] * g.wt).sum() / g.wt.sum() for c in cols}),
        include_groups=False)
    print("\nPooled by condition (weighted by reference words):")
    print(pooled.map(lambda x: f"{x:.1%}").to_string())
    by_site = w.assign(site=w.series.str[:2]).groupby(["site", "condition"]).apply(
        lambda g: (g.wer * g.wt).sum() / g.wt.sum(), include_groups=False)
    print("\nWER by recording site:")
    print(by_site.unstack().map(lambda x: f"{x:.1%}").to_string())


if __name__ == "__main__":
    main()
