"""Quote-backed insight extraction with an LLM.

Same prompt for every condition, and it never says which condition a transcript is, so any
difference in output comes from the transcript alone. Quotes are checked against the
transcript (extract.quotes); insights whose quotes cannot be found are rejected as
unsupported and kept in a .rejected.jsonl file, since that rate is a result in itself.

  python -m extract.extractor --meetings ES2004c                 # 4 conditions, 1 run each
  python -m extract.extractor --clean-runs 3                     # all meetings; 3 CLEAN runs
  python -m extract.extractor --series ES2004 --conditions clean farfield

  python -m extract.extractor --revalidate                       # re-check quotes, no API

Out: data/insights/{meeting}.{condition}.r{run}.jsonl, .rejected.jsonl, and .raw.json (the
model's output as returned, so quote checking can change without paying for new calls).
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from pydantic import BaseModel, ValidationError

from core.config import EXTRACT_MODEL, INSIGHTS, SERIES, Condition, meetings
from core.jsonl import write_jsonl
from core.llm import Budget, BudgetExceeded, client
from core.transcript import Transcript, load_transcript
from extract.quotes import locate
from extract.schema import Insight, InsightType, Quote

STAGES = {"a": "project kick-off", "b": "functional design", "c": "conceptual design",
          "d": "detailed design"}

SYSTEM = """You extract insights from a meeting transcript for a system that writes them \
into the project's record automatically.

The four-person team is designing a new TV remote control. Speakers are labelled by role: \
PM = project manager, ME = marketing expert, UI = user interface designer, ID = industrial \
designer. The transcript may come from speech recognition, so words and speaker labels can \
be wrong.

Extract four kinds of insight:
- decision: something the group settled on. Not a proposal, preference or open option.
- action_item: a task someone will do after this point. owner = the role who will do it \
("team" if everyone, null if nobody is named). When a speaker says "I will ...", the owner \
is that speaker. deadline = as stated, else null.
- cost_figure: a stated number about cost, price, budget, or a sales or profit target. \
value = the figure with its unit as said, e.g. "12.50 euro".
- open_risk: an unresolved problem, concern or constraint that threatens the design.

Rules:
- Extract only what the transcript says. Do not fill gaps from general knowledge.
- Give each insight 1-3 supporting quotes. A quote is copied exactly from one transcript \
line (4-30 words) and cites that line's number.
- owner and deadline only on action_item; value only on cost_figure; otherwise null.
- One insight per distinct fact; merge repeats and keep the clearest quotes.
- confidence: 0-100, how likely the insight is correct, including who it is attributed to, \
given the transcript quality.
- If there is nothing of a kind, extract none of that kind."""


class _Quote(BaseModel):
    line: int
    text: str


class _Insight(BaseModel):
    type: InsightType
    summary: str
    owner: Literal["PM", "ME", "UI", "ID", "team"] | None
    deadline: str | None
    value: str | None
    confidence: int
    quotes: list[_Quote]


class _Extraction(BaseModel):
    insights: list[_Insight]


def render(t: Transcript) -> str:
    """One numbered line per turn: L12 [03:41] PM: text"""
    return "\n".join(f"L{i} [{int(turn.start // 60):02d}:{int(turn.start % 60):02d}] "
                     f"{turn.speaker}: {turn.text}" for i, turn in enumerate(t.turns))


def to_insights(raw: _Extraction, t: Transcript, run: int) -> tuple[list[Insight], list[dict]]:
    kept, rejected = [], []
    for n, item in enumerate(raw.insights):
        evidence = []
        for q in item.quotes:
            hit = locate(t, q.line, q.text)
            if hit:
                turn, words, score = hit
                evidence.append(Quote(text=" ".join(w.text for w in words), speaker=turn.speaker,
                                      start=words[0].start, end=words[-1].end,
                                      match_score=round(score, 3)))
        reason = None
        if not evidence:
            reason = "unsupported"  # no quote found in the transcript
        elif item.type == InsightType.COST_FIGURE and not item.value:
            reason = "no_value"
        if reason is None:
            action = item.type == InsightType.ACTION_ITEM
            try:
                kept.append(Insight(
                    id=f"{t.meeting_id}.{t.condition}.r{run}.{n:03d}", meeting_id=t.meeting_id,
                    condition=t.condition, type=item.type, summary=item.summary,
                    owner=item.owner if action else None,
                    deadline=item.deadline if action else None,
                    value=item.value if item.type == InsightType.COST_FIGURE else None,
                    evidence=evidence, model_confidence=item.confidence, run=run))
                continue
            except ValidationError as e:
                reason = f"invalid: {e.errors()[0]['msg']}"
        rejected.append({"reason": reason, "run": run, **item.model_dump(mode="json")})
    return kept, rejected


def extract(mid: str, cond: Condition, run: int, budget: Budget) -> dict:
    budget.check()
    t = load_transcript(mid, cond)
    user = f"Meeting {'abcd'.index(mid[-1]) + 1} of 4 ({STAGES[mid[-1]]}).\n\nTranscript:\n{render(t)}"
    t0 = time.time()
    resp = client.messages.parse(
        model=EXTRACT_MODEL, max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=_Extraction, output_config={"effort": "medium"})
    cost = budget.charge(EXTRACT_MODEL, resp.usage, f"extract:{mid}.{cond}.r{run}",
                         time.time() - t0)
    if resp.stop_reason != "end_turn" or resp.parsed_output is None:
        raise RuntimeError(f"{mid} {cond} r{run}: stop_reason={resp.stop_reason}")

    raw_path = INSIGHTS / f"{mid}.{cond}.r{run}.raw.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(resp.parsed_output.model_dump_json(), encoding="utf-8")
    kept, rejected = validate(mid, cond, run)
    return {"job": f"{mid} {cond} r{run}", "kept": kept, "rejected": rejected,
            "usd": cost, "seconds": time.time() - t0}


def validate(mid: str, cond: Condition, run: int) -> tuple[int, int]:
    """Check the saved model output against the transcript; rerunnable without API calls."""
    stem = f"{mid}.{cond}.r{run}"
    raw = _Extraction.model_validate_json((INSIGHTS / f"{stem}.raw.json").read_text(encoding="utf-8"))
    kept, rejected = to_insights(raw, load_transcript(mid, cond), run)
    write_jsonl(INSIGHTS / f"{stem}.jsonl", kept)
    write_jsonl(INSIGHTS / f"{stem}.rejected.jsonl", rejected)
    return len(kept), len(rejected)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--series", nargs="+", default=SERIES)
    p.add_argument("--meetings", nargs="+", help="overrides --series")
    p.add_argument("--conditions", nargs="+", default=[str(c) for c in Condition],
                   choices=[str(c) for c in Condition])
    p.add_argument("--clean-runs", type=int, default=1, help="repeat runs on CLEAN")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true", help="redo finished jobs")
    p.add_argument("--revalidate", action="store_true",
                   help="re-check saved model output against transcripts; no API calls")
    args = p.parse_args()

    jobs = [(mid, Condition(c), r) for mid in (args.meetings or meetings(args.series))
            for c in args.conditions
            for r in range(args.clean_runs if c == Condition.CLEAN else 1)]
    if args.revalidate:
        for j in jobs:
            if (INSIGHTS / f"{j[0]}.{j[1]}.r{j[2]}.raw.json").exists():
                print(f"{j[0]} {j[1]} r{j[2]}: %d kept, %d rejected" % validate(*j))
        return
    todo = [j for j in jobs if args.force or not (INSIGHTS / f"{j[0]}.{j[1]}.r{j[2]}.jsonl").exists()]
    print(f"{len(jobs) - len(todo)} of {len(jobs)} done; running {len(todo)} with {EXTRACT_MODEL}.")

    budget = Budget()
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(extract, *j, budget): j for j in todo}
        for f in as_completed(futures):
            try:
                r = f.result()
                print(f"{r['job']}: {r['kept']} kept, {r['rejected']} rejected, "
                      f"${r['usd']:.4f}, {r['seconds']:.0f}s (total ${budget.spent:.3f})", flush=True)
            except BudgetExceeded as e:
                print(f"Stopped: {e}")
                pool.shutdown(cancel_futures=True)
                break
            except Exception as e:  # one failed job should not sink the batch
                print(f"FAILED {futures[f]}: {e!r}", flush=True)
    print(f"Spent ${budget.spent:.3f} this run (cap ${budget.max_usd:.2f}).")


if __name__ == "__main__":
    main()
