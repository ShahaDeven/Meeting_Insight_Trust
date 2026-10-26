"""Export precomputed results for the static review console (web/).

  python -m app.export
Out: web/public/data/{meeting,memory,findings}.json and web/public/audio/*.mp3

The console runs no models: everything it shows is produced here from the pipeline outputs.
Risk scores are the held-out (leave-one-series-out) predictions, and each insight's "why" comes
from a logistic model fitted without the featured series, so explanations match the scores.
"""

import json
import subprocess
from collections import defaultdict

import numpy as np
import pandas as pd

from core.config import DATA, INSIGHTS, PRIMARY_SERIES, RESULTS, ROOT, SERIES, Condition
from core.jsonl import read_jsonl
from core.transcript import load_transcript
from evals.audit_sheet import current_verdicts
from extract.extractor import STAGES
from extract.memory_strategies import MEMORY, STRATEGIES, Record
from extract.schema import Insight
from risk.policy import ASR, COST
from risk.train import feature_columns, models

WEB = ROOT / "web" / "public"
MEETING, SERIES_ID = "TS3003c", "TS3003"

AUDIO = {"clean": ("Mix-Headset", "headset microphones"),
         "farfield": ("Array1-01", "one far-field room microphone")}
SHOWN = ("clean", "farfield")

# Numeric feature -> (phrase when above average, phrase when below average)
PHRASES = {
    "model_confidence": ("Extractor was confident", "Extractor was unsure"),
    "hedges": ("Hedged wording ('maybe', 'I think')", "No hedged wording"),
    "agrees": ("Explicit agreement words", "No explicit agreement words"),
    "quote_conf_min": ("Recognizer confident in every quoted word", "Recognizer unsure of a quoted word"),
    "quote_conf_mean": ("High recognizer confidence on the quote", "Low recognizer confidence on the quote"),
    "quote_low_conf_share": ("Several low-confidence words in the quote", "Few low-confidence words"),
    "meeting_conf_mean": ("Clean recording overall", "Noisy recording overall"),
    "turns_nearby": ("Lively back-and-forth around the quote", "Few speaker turns around the quote"),
    "speakers_nearby": ("Several people speaking around it", "Few people speaking around it"),
    "quote_speakers": ("Quotes from several speakers", "Quotes from one speaker"),
    "n_quotes": ("Several supporting quotes", "A single supporting quote"),
    "quote_words": ("Long quote", "Short quote"),
    "min_match_score": ("Quote matches the transcript exactly", "Quote only loosely matches the transcript"),
    "has_value": ("Carries a figure", "No figure"),
    "has_deadline": ("Carries a deadline", "No deadline"),
    "is_asr": ("Machine transcript", "Human transcript"),
}
TYPE_PHRASE = {"action_item": "Action item", "decision": "Decision claim", "open_risk": "Open risk",
               "cost_figure": "Cost figure"}


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def encode_audio() -> dict:
    out = {}
    (WEB / "audio").mkdir(parents=True, exist_ok=True)
    for cond, (mic, _) in AUDIO.items():
        src = DATA / "audio" / f"{MEETING}.{mic}.wav"
        dst = WEB / "audio" / f"{MEETING}.{cond}.mp3"
        if not dst.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1",
                            "-ar", "16000", "-b:a", "24k", str(dst)], check=True)
        out[cond] = f"audio/{dst.name}"
    return out


def explainer(features: pd.DataFrame):
    """Logistic model fitted without the featured series; returns per-insight drivers."""
    cols = feature_columns(features)
    train = features[features.series != SERIES_ID]
    pipe = models()["logistic"].fit(train[cols], train.wrong)
    scaler, lr = pipe[0], pipe[-1]

    def why(row: pd.Series, lane: str) -> list[dict]:
        z = (row[cols].to_numpy(dtype=float) - scaler.mean_) / scaler.scale_
        contrib = dict(zip(cols, z * lr.coef_[0]))
        # Group one-hot features so the phrase describes what the insight actually is.
        drivers = {}
        kind = next(c.removeprefix("type_") for c in cols if c.startswith("type_") and row[c] == 1)
        drivers[TYPE_PHRASE[kind]] = sum(v for c, v in contrib.items() if c.startswith("type_"))
        owner_part = contrib.pop("owner_team") + contrib.pop("owner_named")
        if kind == "action_item":
            owner = ("Owner given as 'the team'" if row["owner_team"] else
                     "Owner is a named person" if row["owner_named"] else "No owner named")
            drivers[owner] = owner_part
        else:  # only action items have owners; for other types this is part of the type
            drivers[TYPE_PHRASE[kind]] += owner_part
        # The recognizer features measure one thing; explain them as one.
        rec = [c for c in ("quote_conf_min", "quote_conf_mean", "quote_low_conf_share") if c in contrib]
        if rec:
            v = sum(contrib.pop(c) for c in rec)
            drivers["Recognizer unsure of the quoted words" if v > 0
                    else "Recognizer confident in the quoted words"] = v
        for c, v in contrib.items():
            if c in PHRASES:
                above = row[c] > scaler.mean_[cols.index(c)]
                drivers[PHRASES[c][0 if above else 1]] = v
        sign = 1 if lane == "review" else -1  # held: what raises risk; auto: what lowers it
        ranked = sorted(((t, v) for t, v in drivers.items() if sign * v > 0.15), key=lambda tv: -sign * tv[1])
        return [{"text": t, "raises_risk": bool(v > 0), "weight": round(float(v), 2)} for t, v in ranked[:3]]
    return why


def export_meeting(verdicts: dict, scores: pd.DataFrame, features: pd.DataFrame, audio: dict) -> dict:
    """Lanes follow the explicit write policy in risk.policy: review when risk >= 1/COST[type]."""
    why = explainer(features)
    feats = features.set_index("insight_id")
    conds = {}
    for cond in SHOWN:
        t = load_transcript(MEETING, cond)
        turns = [{"speaker": turn.speaker, "start": round(turn.start, 2), "end": round(turn.end, 2),
                  "words": [[w.text, round(w.start, 2),
                             None if w.conf is None else round(w.conf, 2),
                             1 if w.match in ("sub", "ins") else 0] for w in turn.words]}
                 for turn in t.turns]
        confs = defaultdict(list)
        for turn in t.turns:
            for w in turn.words:
                if w.conf is not None:
                    confs[int(w.start // 10)].append(w.conf)
        track = [round(float(np.mean(confs[b])), 3) if confs.get(b) else None
                 for b in range(int(t.duration // 10) + 1)] if confs else []
        insights = []
        for ins in read_jsonl(INSIGHTS / f"{MEETING}.{cond}.r0.jsonl", Insight):
            if ins.id not in scores.index:
                continue
            risk = float(scores.loc[ins.id, "logistic"])
            threshold = 1 / COST[str(ins.type)]
            lane = "review" if risk >= threshold else "auto"
            v = verdicts[ins.id]
            insights.append({
                "id": ins.id, "type": str(ins.type), "summary": ins.summary, "owner": ins.owner,
                "value": ins.value, "deadline": ins.deadline, "risk": round(risk, 3),
                "lane": lane, "threshold": round(threshold, 3),
                "extractor_confidence": ins.model_confidence,
                "quotes": [{"text": q.text, "speaker": q.speaker, "start": round(q.start, 2),
                            "end": round(q.end, 2), "at": mmss(q.start)} for q in ins.evidence],
                "why": why(feats.loc[ins.id], lane),
                "reviewer": {"verdict": v["verdict"], "failure": v["failure"], "reason": v["reason"]},
            })
        insights.sort(key=lambda i: i["quotes"][0]["start"])
        rejected = [{"type": r["type"], "summary": r["summary"], "reason": r["reason"],
                     "quotes": [q["text"] for q in r["quotes"]]}
                    for r in read_jsonl(INSIGHTS / f"{MEETING}.{cond}.r0.rejected.jsonl")]
        conds[cond] = {"audio": audio[cond], "microphone": AUDIO[cond][1],
                       "transcript": "human transcript" if cond == "clean" else "speech recognition",
                       "turns": turns, "confidence": track, "insights": insights, "rejected": rejected}
    return {"meeting": MEETING, "series": SERIES_ID, "stage": STAGES[MEETING[-1]],
            "duration": round(max(c["turns"][-1]["end"] for c in conds.values()), 1),
            "policy": {"costs": COST, "thresholds": {k: round(1 / v, 3) for k, v in COST.items()}},
            "conditions": conds}


def export_memory() -> dict:
    gold = json.loads((DATA / "gold" / "state_final.json").read_text(encoding="utf-8"))[SERIES_ID]
    matches = [json.loads(line) for s in STRATEGIES
               for line in (RESULTS / f"memory_matches.{s}.jsonl").read_text(encoding="utf-8").splitlines()]
    out = {"series": SERIES_ID, "stages": {m: STAGES[m] for m in "abcd"},
           "gold": [{"slot": g["slot"], "category": g["category"], "after": g["after"]} for g in gold],
           "strategies": {}}
    for s in STRATEGIES:
        out["strategies"][s] = {}
        for cond in SHOWN:
            records, queues = {}, {}
            for m in "abcd":
                path = MEMORY / s / f"{SERIES_ID}.{cond}.{m}.json"
                records[m] = [x.model_dump(mode="json") for x in
                              Record.model_validate_json(path.read_text(encoding="utf-8")).slots]
                q = path.with_suffix(".review.json")
                if q.exists():
                    queues[m] = json.loads(q.read_text(encoding="utf-8"))
            status = {r["slot"]: {"status": r["status"], "record_row": r["record_row"], "reason": r["reason"]}
                      for r in matches if r["strategy"] == s and r["series"] == SERIES_ID and r["condition"] == cond}
            out["strategies"][s][cond] = {"records": records, "review": queues, "scored": status}
    return out


def catch_curve(scores: pd.DataFrame) -> dict:
    y = scores.wrong.to_numpy()
    out = {}
    for col in ("logistic", "base_model_conf", "base_quote_conf"):
        order = np.argsort(-scores[col].to_numpy(), kind="stable")
        cum = np.cumsum(y[order]) / y.sum()
        out[col] = [round(float(cum[int(round(b / 100 * len(y))) - 1]) if b else 0.0, 4)
                    for b in range(0, 101, 2)]
    return out


def export_findings(scores: pd.DataFrame) -> dict:
    ladder = pd.read_csv(RESULTS / "attribution_ladder.csv").set_index("measure")
    human = pd.read_csv(RESULTS / "risk_human_check.csv").set_index("score")
    mem = pd.read_csv(RESULTS / "memory_scores.csv")
    asr = pd.read_csv(RESULTS / "asr_quality.csv")
    usage = [json.loads(line) for line in (RESULTS / "llm_usage.jsonl").read_text().splitlines()]
    spend = defaultdict(float)
    for u in usage:
        spend[u["tag"].split(":")[0]] += u["usd"]
    pick = lambda m: {k: round(float(ladder.loc[m, k]), 4) for k in ("value", "ci_low", "ci_high")}  # noqa: E731
    wt = asr.assign(w=asr.ref_tokens)
    wer = {c: round(float((g.wer * g.w).sum() / g.w.sum()), 4) for c, g in wt.groupby("condition")}
    return {
        "corpus": {"meetings": len(SERIES) * 4, "series": len(SERIES), "verified_series": len(PRIMARY_SERIES),
                   "hours_per_mic": round(float(asr[asr.condition == "farfield"].minutes.sum() / 60), 1),
                   "wer": wer, "insights": int(len(scores))},
        "ladder": {m: pick(m) for m in ("clean", "speaker_swap", "headset", "farfield",
                                         "farfield_share_model", "farfield_share_mishearing",
                                         "farfield_share_speaker")},
        "risk": {
            # Deployment-relevant: headset + far-field ASR only. Clean and swap are controls.
            "catch_curve": catch_curve(scores[scores.condition.isin(ASR)].reset_index(drop=True)),
            "deploy": json.loads((RESULTS / "deploy_eval.json").read_text(encoding="utf-8")),
            "human_auroc": {k: round(float(v), 3) for k, v in human.auroc_vs_human.items()},
            "human_n": int(human.n.iloc[0]),
        },
        "memory": mem.round(3).to_dict("records"),
        "audits": [
            {"name": "First blind audit", "rows": 99, "agreement": 0.55,
             "note": "The rubric was ambiguous about what counts as a decision and about facts reversed later."},
            {"name": "Blind test after the rubric fix", "rows": 50, "agreement": 0.52, "kappa": 0.04,
             "note": "The reviewer reports marking too quickly."},
            {"name": "Final structured blind audit", "rows": 29, "agreement": 0.66, "kappa": 0.27,
             "ci": [0.47, 0.80], "note": "Pre-committed; judge labels hash-frozen before marking."},
        ],
        "cost": {"llm_usd": round(sum(spend.values()), 2), "gpu_usd": 0.35,
                 "by_stage": {k: round(v, 3) for k, v in spend.items()}},
    }


def main() -> None:
    verdicts = current_verdicts()
    scores = pd.read_csv(RESULTS / "risk_scores.csv")
    features = pd.read_csv(RESULTS / "risk_features.csv")
    audio = encode_audio()
    (WEB / "data").mkdir(parents=True, exist_ok=True)
    outputs = {"meeting": export_meeting(verdicts, scores.set_index("insight_id"), features, audio),
               "memory": export_memory(), "findings": export_findings(scores)}
    for name, obj in outputs.items():
        path = WEB / "data" / f"{name}.json"
        path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1024:.0f} KB")
    for f in sorted((WEB / "audio").glob("*.mp3")):
        print(f"{f.relative_to(ROOT)}: {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
