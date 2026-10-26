"""Export precomputed results for the static review console (web/).

  python -m app.export
Out: web/public/data/{series,memory,findings}.json, web/public/data/meetings/TS3003{a-d}.json,
     web/public/audio/TS3003{a-d}.{clean,farfield}.mp3

The console runs no models: everything it shows is produced here from the pipeline outputs.
Risk scores are the held-out (leave-one-series-out) predictions, and each insight's "why" comes
from a logistic model fitted without the featured series, so explanations match the scores.
"""

import json
import subprocess
import urllib.request
from collections import defaultdict

import numpy as np
import pandas as pd

from core.config import AMI_MIRROR, DATA, INSIGHTS, PRIMARY_SERIES, RESULTS, ROOT, SERIES
from core.jsonl import read_jsonl
from core.transcript import load_transcript
from evals.audit_sheet import current_verdicts
from extract.extractor import STAGES
from extract.memory_strategies import MEMORY, STRATEGIES, Record
from extract.schema import Insight
from risk.policy import ASR, COST
from risk.train import feature_columns, models

WEB = ROOT / "web" / "public"
SERIES_ID = "TS3003"

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
}
TYPE_PHRASE = {"action_item": "Action item", "decision": "Decision claim", "open_risk": "Open risk",
               "cost_figure": "Cost figure"}


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def encode_audio(mid: str) -> dict:
    """Download (if needed) and re-encode one meeting's two recordings for the console."""
    out = {}
    (WEB / "audio").mkdir(parents=True, exist_ok=True)
    for cond, (mic, _) in AUDIO.items():
        src = DATA / "audio" / f"{mid}.{mic}.wav"
        dst = WEB / "audio" / f"{mid}.{cond}.mp3"
        if not dst.exists():
            if not src.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(f"{AMI_MIRROR}/{mid}/audio/{src.name}", src)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1",
                            "-ar", "16000", "-b:a", "24k", str(dst)], check=True)
        out[cond] = f"audio/{dst.name}"
    return out


NEXT_MEETING = ("next meeting", "next time", "next session", "next one", "for the next")
SAME_MEETING = ("today", "this meeting", "now", "end of the meeting", "before we finish")


def due_of(deadline: str | None, part: str) -> dict:
    """Map a spoken deadline onto the series calendar (the corpus records no clock times)."""
    if not deadline:
        return {"kind": "none"}
    d = deadline.lower()
    if any(k in d for k in NEXT_MEETING):
        nxt = "abcd"[min("abcd".index(part) + 1, 3)]
        return {"kind": "after"} if part == "d" else {"kind": "meeting", "part": nxt}
    if any(k in d for k in SAME_MEETING):
        return {"kind": "meeting", "part": part}
    return {"kind": "text", "text": deadline}


def field_link(ins: Insight, written: list[dict]) -> str | None:
    """The record field change backed by a quote within 30 s of this insight's quotes, if any."""
    best, gap = None, 30.0
    for w in written:
        if w.get("start") is None:
            continue
        for q in ins.evidence:
            d = min(abs(w["start"] - q.start), abs(w["start"] - q.end))
            if d <= gap:
                best, gap = w["slot"], d
    return best


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


def gated(cond: str, part: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Record fields after a meeting, the changes the gate wrote (with evidence), and those it held."""
    base = MEMORY / "gated_resummarize"
    stem = f"{SERIES_ID}.{cond}.{part}"  # not Path.with_suffix: ".a" would be taken as the suffix
    read = lambda ext: json.loads((base / f"{stem}{ext}").read_text(encoding="utf-8"))  # noqa: E731
    slots, written, held = read(".json")["slots"], read(".evidence.json"), read(".review.json")
    return slots, written, held


def export_meeting(mid: str, verdicts: dict, scores: pd.DataFrame, why, feats: pd.DataFrame,
                   audio: dict) -> dict:
    """Lanes follow the explicit write policy in risk.policy: review when risk >= 1/COST[type]."""
    part = mid[-1]
    conds = {}
    for cond in SHOWN:
        _, written, _ = gated(cond, part)
        t = load_transcript(mid, cond)
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
        for ins in read_jsonl(INSIGHTS / f"{mid}.{cond}.r0.jsonl", Insight):
            if ins.id not in scores.index:
                continue
            risk = float(scores.loc[ins.id, "logistic"])
            threshold = 1 / COST[str(ins.type)]
            lane = "review" if risk >= threshold else "auto"
            v = verdicts[ins.id]
            action = ins.type == "action_item"
            due = due_of(ins.deadline, part) if action else {"kind": "none"}
            insights.append({
                "id": ins.id, "meeting": part, "type": str(ins.type), "summary": ins.summary,
                "owner": ins.owner, "value": ins.value, "deadline": ins.deadline, "risk": round(risk, 3),
                "lane": lane, "threshold": round(threshold, 3),
                "extractor_confidence": ins.model_confidence,
                "quotes": [{"text": q.text, "speaker": q.speaker, "start": round(q.start, 2),
                            "end": round(q.end, 2), "at": mmss(q.start)} for q in ins.evidence],
                "why": why(feats.loc[ins.id], lane),
                "reviewer": {"verdict": v["verdict"], "failure": v["failure"], "reason": v["reason"]},
                # Where this write lands: always the meeting's notes; action items also become a
                # task, and one with a schedulable deadline lands on the calendar.
                "destinations": ["notes"] + (["tasks"] if action else [])
                                + (["calendar"] if due["kind"] in ("meeting", "after") else []),
                "due": due,
                "field": None if action else field_link(ins, written),
            })
        insights.sort(key=lambda i: i["quotes"][0]["start"])
        rejected = [{"type": r["type"], "summary": r["summary"], "reason": r["reason"],
                     "quotes": [q["text"] for q in r["quotes"]]}
                    for r in read_jsonl(INSIGHTS / f"{mid}.{cond}.r0.rejected.jsonl")]
        conds[cond] = {"audio": audio[cond], "microphone": AUDIO[cond][1],
                       "transcript": "human transcript" if cond == "clean" else "speech recognition",
                       "turns": turns, "confidence": track, "insights": insights, "rejected": rejected}
    return {"meeting": mid, "part": part, "series": SERIES_ID, "stage": STAGES[part],
            "duration": round(max(c["turns"][-1]["end"] for c in conds.values()), 1),
            "conditions": conds}


def export_series(meetings: dict[str, dict]) -> dict:
    """Destinations for the whole series: record fields (gate), meeting notes and tasks (policy)."""
    out = {"series": SERIES_ID, "date": "11 October 2004",
           "meetings": [{"part": m["part"], "id": m["meeting"], "stage": m["stage"],
                         "duration": m["duration"]} for m in meetings.values()],
           "policy": {"costs": COST, "thresholds": {k: round(1 / v, 3) for k, v in COST.items()}},
           "conditions": {}}
    for cond in SHOWN:
        fields = {}
        for part in "abcd":
            slots, written, held = gated(cond, part)
            fields[part] = {
                "slots": slots,
                "written": [w | {"at": mmss(w["start"]) if w.get("start") is not None else None}
                            for w in written],
                "held": held,
            }
        notes, tasks = {}, []
        for m in meetings.values():
            ins = m["conditions"][cond]["insights"]
            notes[m["part"]] = [{k: i[k] for k in ("id", "type", "summary", "owner", "value", "deadline",
                                                    "lane", "risk", "threshold", "field")}
                                | {"quote": i["quotes"][0]} for i in ins]
            tasks += [{"id": i["id"], "meeting": m["part"], "task": i["summary"], "owner": i["owner"],
                       "deadline": i["deadline"], "due": i["due"], "lane": i["lane"], "risk": i["risk"],
                       "threshold": i["threshold"], "quote": i["quotes"][0]}
                      for i in ins if i["type"] == "action_item"]
        out["conditions"][cond] = {"fields": fields, "notes": notes, "tasks": tasks}
    return out


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
    why, feats = explainer(features), features.set_index("insight_id")
    (WEB / "data" / "meetings").mkdir(parents=True, exist_ok=True)
    meetings = {}
    for part in "abcd":
        mid = f"{SERIES_ID}{part}"
        meetings[mid] = export_meeting(mid, verdicts, scores.set_index("insight_id"), why, feats,
                                       encode_audio(mid))
    old = WEB / "data" / "meeting.json"  # single-meeting format from before the series view
    if old.exists():
        old.unlink()
    outputs = {f"meetings/{mid}": m for mid, m in meetings.items()}
    outputs |= {"series": export_series(meetings), "memory": export_memory(),
                "findings": export_findings(scores)}
    for name, obj in outputs.items():
        path = WEB / "data" / f"{name}.json"
        path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1024:.0f} KB")
    for f in sorted((WEB / "audio").glob("*.mp3")):
        print(f"{f.relative_to(ROOT)}: {f.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
