"""Label every insight correct / wrong / unsure against what was really said.

The judge sees each insight's claim next to the AMI *human* transcript around its quotes
(true words, true speakers) plus the meeting's AMI summary. It is never told which
condition produced the insight, so verdicts cannot lean on the noise level. A human audits
a blind random sample (evals.audit_sheet) to measure how often the judge is right.

  python -m evals.judge                 # every insights file not yet judged
  python -m evals.judge --meetings ES2004c

Out: data/labels/{meeting}.{condition}.r{run}.judge.jsonl
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from pydantic import BaseModel

from core.config import DATA, INSIGHTS, JUDGE_MODEL
from core.jsonl import read_jsonl, write_jsonl
from core.llm import Budget, BudgetExceeded, client
from core.transcript import Transcript, load_transcript
from extract.schema import Insight
from pipeline.ami import load_summary

LABELS = DATA / "labels"
PAD = 20.0  # seconds of real transcript shown either side of each quote

# Policy set with Deven after the first audit (2026-10-21): decisions need explicit agreement,
# and a fact that this meeting later reverses or supersedes is a wrong (stale) write.
RULES = """An insight is CORRECT only if all four hold:
1. Said and still true: what was really said supports the claim (same meaning; wording may \
differ), AND the meeting summary does not show it reversed or superseded later in the same \
meeting. A stale fact is wrong. A recap of an earlier meeting's decision is fine if this \
meeting did not change it.
2. Right kind: a decision needs explicit agreement - stated as decided ("we decided", \
"let's go with", "so that's settled") or clearly accepted by the group. One person's \
suggestion answered only by "yeah" or "mm" is a proposal, not a decision. An action item is \
someone committing to a task; a cost figure is a stated number about cost, price, budget or \
targets; an open risk is a real unresolved concern.
3. Right person: an action item's owner is who actually committed (owner "team" means the \
group; "none named" is right only if nobody was given the task). Speaker labels in what was \
really said are the truth.
4. Details: numbers, units and deadlines match exactly what was said.
If any rule fails it is WRONG; name the first rule that fails: content (1), type (2), \
owner (3) or number (4). Use UNSURE only if the excerpt and summary cannot settle it.
Do not mark an insight wrong just because the excerpt is short: if the claim is supported \
and nothing in the excerpt or summary contradicts it, it is correct."""

SYSTEM = f"""You check insights that were extracted automatically from a meeting recording. \
For each one you get the claim and an excerpt of what was really said around its supporting \
quotes, from an accurate human transcript with correct speaker labels: PM = project manager, \
ME = marketing expert, UI = user interface designer, ID = industrial designer. The meeting's \
human-written summary is given as background.

{RULES}

Judge every item independently. Keep each reason to one short sentence."""


class _Verdict(BaseModel):
    item: int
    verdict: Literal["correct", "wrong", "unsure"]
    failure: Literal["none", "content", "type", "owner", "number"]
    reason: str


class _Verdicts(BaseModel):
    verdicts: list[_Verdict]


def stamp(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def truth_excerpt(clean: Transcript, insight: Insight, pad: float = PAD) -> str:
    """Human-transcript lines covering every quote of the insight, +-pad seconds."""
    windows = sorted((q.start - pad, q.end + pad) for q in insight.evidence)
    merged = [list(windows[0])]
    for s, e in windows[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    blocks = []
    for s, e in merged:
        lines = []
        for turn in clean.turns:
            words = [w for w in turn.words if s <= w.start <= e]
            if words:
                lines.append(f"[{stamp(words[0].start)}] {turn.speaker}: "
                             + " ".join(w.text for w in words))
        blocks.append("\n".join(lines) or "(nothing was said in this window)")
    return "\n...\n".join(blocks)


def summary_text(mid: str) -> str:
    return "\n".join(f"{section}: {' '.join(sents) or 'NA'}"
                     for section, sents in load_summary(mid).items())


def describe(i: Insight) -> str:
    fields = [f"Type: {i.type}"]
    if i.owner is not None or i.type == "action_item":
        fields.append(f"Owner: {i.owner or 'none named'}")
    if i.deadline:
        fields.append(f"Deadline: {i.deadline}")
    if i.value:
        fields.append(f"Value: {i.value}")
    return " | ".join(fields) + f"\nClaim: {i.summary}"


def judge_file(mid: str, stem: str, budget: Budget) -> dict:
    budget.check()
    insights = list(read_jsonl(INSIGHTS / f"{stem}.jsonl", Insight))
    out_path = LABELS / f"{stem}.judge.jsonl"
    if not insights:
        write_jsonl(out_path, [])
        return {"stem": stem, "n": 0, "usd": 0.0}
    clean = load_transcript(mid, "clean")
    summary = summary_text(mid)
    # Items are numbered, not given their ids: ids name the condition, which stays hidden.
    items = "\n\n".join(f"### Item {k}\n{describe(i)}\nWhat was really said:\n{truth_excerpt(clean, i)}"
                        for k, i in enumerate(insights, 1))
    t0 = time.time()
    resp = client.messages.parse(
        model=JUDGE_MODEL, max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content": f"Meeting summary:\n{summary}\n\nItems:\n\n{items}"}],
        output_format=_Verdicts, output_config={"effort": "high"})
    cost = budget.charge(JUDGE_MODEL, resp.usage, f"judge:{stem}", time.time() - t0)
    if resp.stop_reason != "end_turn" or resp.parsed_output is None:
        raise RuntimeError(f"{stem}: stop_reason={resp.stop_reason}")

    by_item = {v.item: v for v in resp.parsed_output.verdicts}
    rows = []
    for k, i in enumerate(insights, 1):
        v = by_item.get(k)
        rows.append({"insight_id": i.id, "meeting_id": mid, "condition": str(i.condition),
                     "run": i.run, "type": str(i.type),
                     "verdict": v.verdict if v else "unsure",
                     "failure": v.failure if v else "none",
                     "reason": v.reason if v else "judge returned no verdict"})
    write_jsonl(out_path, rows)
    return {"stem": stem, "n": len(rows), "missing": len(insights) - len(by_item.keys() & set(range(1, len(insights) + 1))),
            "wrong": sum(r["verdict"] == "wrong" for r in rows), "usd": cost}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--meetings", nargs="+")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    stems = sorted(f.name.removesuffix(".jsonl") for f in INSIGHTS.glob("*.r*.jsonl")
                   if not f.name.endswith(".rejected.jsonl"))
    if args.meetings:
        stems = [s for s in stems if s.split(".")[0] in args.meetings]
    todo = [s for s in stems if args.force or not (LABELS / f"{s}.judge.jsonl").exists()]
    print(f"{len(stems) - len(todo)} of {len(stems)} judged; running {len(todo)} with {JUDGE_MODEL}.")

    budget = Budget()
    with ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(judge_file, s.split(".")[0], s, budget): s for s in todo}
        for f in as_completed(futures):
            try:
                r = f.result()
                print(f"{r['stem']}: {r['n']} judged, {r.get('wrong', 0)} wrong, "
                      f"{r.get('missing', 0)} missing, ${r['usd']:.4f} (total ${budget.spent:.3f})",
                      flush=True)
            except BudgetExceeded as e:
                print(f"Stopped: {e}")
                pool.shutdown(cancel_futures=True)
                break
            except Exception as e:
                print(f"FAILED {futures[f]}: {e!r}", flush=True)
    print(f"Spent ${budget.spent:.3f} this run (cap ${budget.max_usd:.2f}).")


if __name__ == "__main__":
    main()
