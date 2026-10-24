"""Project memory across a 4-meeting series: re-summarize vs evidence ledger.

re_summarize     After each meeting the model rewrites the whole project record from the
                 previous record plus the new meeting's transcript (how auto-updating CRM
                 fields typically work).
evidence_ledger  After each meeting the model may only add / update / retire a slot by citing
                 one of that meeting's quote-backed insights (extract.extractor output). The
                 code rejects any change without a valid citation, so a slot with no new
                 evidence keeps its value: the ledger abstains instead of guessing.

Same model, prompt style and slot conventions for both; they differ only in what may change
the record. Scored against the human-verified state tables by evals.memory_score.

  python -m extract.memory_strategies                 # primary series, all conditions
Out: data/memory/{strategy}/{series}.{condition}.{meeting}.json
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from pydantic import BaseModel

from core.config import DATA, EXTRACT_MODEL, INSIGHTS, PRIMARY_SERIES, Condition
from core.jsonl import read_jsonl
from core.llm import Budget, BudgetExceeded, client
from core.transcript import load_transcript
from extract.extractor import STAGES, render
from extract.schema import Insight, InsightType

MEMORY = DATA / "memory"
STRATEGIES = ("re_summarize", "evidence_ledger")

SLOTS = """The project record holds one row per fact slot about a team (PM project manager, ME \
marketing expert, UI user interface designer, ID industrial designer) designing a TV remote:
- decision slots: one per design dimension the group explicitly agreed (e.g. power source, case \
material, target group). A suggestion only answered by "yeah" is not a decision.
- cost_figure slots: one per figure (selling price, production cost limit, profit target, ...).
- action_item slots: one per assigned task. Value "OWNER: task (open)", later "(done)".
- open_risk slots: one per unresolved concern; later "resolved: how" if settled.
Values must reflect the latest state: update a slot when the team changes it, mark it \
"dropped" if abandoned. Keep the 20-40 slots that matter most."""


class Slot(BaseModel):
    slot: str
    category: InsightType
    value: str


class Record(BaseModel):
    slots: list[Slot]


class _Op(BaseModel):
    action: Literal["add", "update", "retire"]
    slot: str
    category: InsightType
    value: str | None
    insight: int  # number of the supporting insight in this meeting's list


class _Ops(BaseModel):
    ops: list[_Op]


RESUMMARIZE_SYSTEM = f"""You maintain a project record across a series of meetings.

{SLOTS}

You get the record as it stood after the previous meeting and the transcript of the new \
meeting (it may come from speech recognition, so words and speaker labels can be wrong). \
Return the complete updated record."""

LEDGER_SYSTEM = f"""You maintain an evidence-backed project record across a series of meetings.

{SLOTS}

You get the record as it stood after the previous meeting and the numbered insights extracted \
from the new meeting, each backed by a quote. Return the changes as operations:
- add: a new slot, value set, citing the insight that establishes it.
- update: an existing slot (use its exact name) whose value this meeting changes.
- retire: an existing slot that this meeting drops or resolves (value says how).
Every operation must cite the number of one insight that supports it. If no insight supports a \
change, make no change: slots without new evidence keep their value."""


def _record_text(slots: list[Slot]) -> str:
    return "\n".join(f"- {s.slot} [{s.category}]: {s.value}" for s in slots) or "(empty)"


def _call(system: str, user: str, fmt, tag: str, budget: Budget):
    budget.check()
    t0 = time.time()
    resp = client.messages.parse(model=EXTRACT_MODEL, max_tokens=16000, system=system,
                                 messages=[{"role": "user", "content": user}],
                                 output_format=fmt, output_config={"effort": "medium"})
    budget.charge(EXTRACT_MODEL, resp.usage, tag, time.time() - t0)
    if resp.stop_reason != "end_turn" or resp.parsed_output is None:
        raise RuntimeError(f"{tag}: stop_reason={resp.stop_reason}")
    return resp.parsed_output


def re_summarize(prev: list[Slot], mid: str, cond: Condition, budget: Budget) -> tuple[list[Slot], dict]:
    t = load_transcript(mid, cond)
    user = (f"Record after the previous meeting:\n{_record_text(prev)}\n\n"
            f"New meeting: {STAGES[mid[-1]]}. Transcript:\n{render(t)}")
    rec = _call(RESUMMARIZE_SYSTEM, user, Record, f"memory:re_summarize:{mid}.{cond}", budget)
    return rec.slots, {}


def evidence_ledger(prev: list[Slot], mid: str, cond: Condition, budget: Budget) -> tuple[list[Slot], dict]:
    insights = list(read_jsonl(INSIGHTS / f"{mid}.{cond}.r0.jsonl", Insight))
    listing = "\n".join(
        f"{n}. [{i.type}] {i.summary}"
        + (f" (owner {i.owner})" if i.owner else "") + (f" (value {i.value})" if i.value else "")
        + f' - quote: "{i.evidence[0].text}"' for n, i in enumerate(insights, 1))
    user = (f"Record after the previous meeting:\n{_record_text(prev)}\n\n"
            f"Insights from the new meeting ({STAGES[mid[-1]]}):\n{listing or '(none)'}")
    ops = _call(LEDGER_SYSTEM, user, _Ops, f"memory:evidence_ledger:{mid}.{cond}", budget).ops
    return apply_ops(prev, ops, len(insights))


def apply_ops(prev: list[Slot], ops: list[_Op], n_insights: int) -> tuple[list[Slot], dict]:
    """The ledger's rule, enforced in code: no valid citation, no change."""
    slots = {s.slot.lower(): s for s in prev}
    applied = rejected = 0
    for op in ops:
        key = op.slot.lower()
        cited = 1 <= op.insight <= n_insights
        if not cited or not op.value or (op.action == "add") == (key in slots):
            rejected += 1  # no evidence, no value, add of an existing slot, or update of a missing one
            continue
        slots[key] = Slot(slot=slots[key].slot if key in slots else op.slot,
                          category=op.category, value=op.value)
        applied += 1
    return list(slots.values()), {"ops": len(ops), "applied": applied, "rejected": rejected}


def run_series(strategy: str, series: str, cond: Condition, budget: Budget) -> dict:
    step = re_summarize if strategy == "re_summarize" else evidence_ledger
    record: list[Slot] = []
    stats = []
    for part in "abcd":
        mid = f"{series}{part}"
        out = MEMORY / strategy / f"{series}.{cond}.{part}.json"
        if out.exists():
            record = Record.model_validate_json(out.read_text(encoding="utf-8")).slots
            continue  # resume: this meeting is already done
        record, info = step(record, mid, cond, budget)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(Record(slots=record).model_dump_json(indent=1), encoding="utf-8")
        stats.append({"meeting": part, "slots": len(record), **info})
    return {"job": f"{strategy} {series} {cond}", "steps": stats}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--series", nargs="+", default=PRIMARY_SERIES)
    p.add_argument("--strategies", nargs="+", default=list(STRATEGIES), choices=STRATEGIES)
    p.add_argument("--conditions", nargs="+", default=[str(c) for c in Condition])
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    jobs = [(s, ser, Condition(c)) for s in args.strategies for ser in args.series
            for c in args.conditions]
    budget = Budget()
    with ThreadPoolExecutor(args.workers) as pool:  # meetings within a series stay sequential
        futures = {pool.submit(run_series, *j, budget): j for j in jobs}
        for f in as_completed(futures):
            try:
                r = f.result()
                print(f"{r['job']}: " + "; ".join(
                    f"{s['meeting']}={s['slots']} slots"
                    + (f" ({s['applied']}/{s['ops']} ops applied)" if "ops" in s else "")
                    for s in r["steps"]) + f" (total ${budget.spent:.3f})", flush=True)
            except BudgetExceeded as e:
                print(f"Stopped: {e}")
                pool.shutdown(cancel_futures=True)
                break
            except Exception as e:
                print(f"FAILED {futures[f]}: {e!r}", flush=True)
    print(f"Spent ${budget.spent:.3f} this run (cap ${budget.max_usd:.2f}).")


if __name__ == "__main__":
    main()
