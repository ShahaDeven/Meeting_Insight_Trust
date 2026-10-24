"""Score memory records after meeting d against the human-verified state tables.

For each gold slot the matcher sees its full history (a-d) and the strategy's final record,
and says whether the record holds the fact with its final value (correct), an earlier value
from its history (stale), a value that was never true (wrong), or not at all (missing).
Comparing two short value lists is far more mechanical than judging a transcript, but matcher
verdicts are still printed for spot-checking.

  python -m evals.memory_score
Out: data/results/memory_matches.jsonl, data/results/memory_scores.csv
"""

import json
import time
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from core.config import DATA, JUDGE_MODEL, PRIMARY_SERIES, RESULTS, Condition
from core.jsonl import write_jsonl
from core.llm import Budget, client
from extract.memory_strategies import MEMORY, STRATEGIES, Record

GOLD = DATA / "gold" / "state_final.json"

SYSTEM = """You compare a project record against a verified answer key.

The answer key lists fact slots with their history: the value after each of meetings a-d \
(blank = not raised yet). For each key slot, find the record row that covers the same fact \
(names may differ; match on meaning) and classify:
- correct: the record holds the fact with its value after meeting d (same meaning; wording \
and extra detail may differ).
- stale: the record holds the fact but with an earlier value from its history (e.g. a decision \
since changed, a task still "open" that is "done" by d).
- wrong: the record holds the fact with a value that never appears in its history.
- missing: no record row covers the fact.
Give the matched record row name, or null if missing. One short reason each."""


class _Match(BaseModel):
    key: int
    status: Literal["correct", "stale", "wrong", "missing"]
    record_row: str | None
    reason: str


class _Matches(BaseModel):
    matches: list[_Match]


def score_record(series: str, gold: list[dict], record: Record, tag: str, budget: Budget) -> list[dict]:
    key = "\n".join(
        f"{n}. {g['slot']} [{g['category']}] | "
        + " | ".join(f"after {m}: {g['after'][m] or ''}" for m in "abcd")
        for n, g in enumerate(gold, 1))
    rec = "\n".join(f"- {s.slot} [{s.category}]: {s.value}" for s in record.slots)
    budget.check()
    t0 = time.time()
    resp = client.messages.parse(
        model=JUDGE_MODEL, max_tokens=16000, system=SYSTEM,
        messages=[{"role": "user", "content": f"Answer key:\n{key}\n\nRecord after meeting d:\n{rec}"}],
        output_format=_Matches, output_config={"effort": "high"})
    budget.charge(JUDGE_MODEL, resp.usage, f"memscore:{tag}", time.time() - t0)
    if resp.stop_reason != "end_turn" or resp.parsed_output is None:
        raise RuntimeError(f"{tag}: stop_reason={resp.stop_reason}")
    by_key = {m.key: m for m in resp.parsed_output.matches}
    return [{"slot": g["slot"], "category": g["category"],
             "changed": len({g["after"][m] for m in "bcd" if g["after"][m]}) > 1,
             **(by_key[n].model_dump(exclude={"key"}) if n in by_key else
                {"status": "missing", "record_row": None, "reason": "matcher gave no verdict"})}
            for n, g in enumerate(gold, 1)]


def main() -> None:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    budget, rows = Budget(), []
    for strategy in STRATEGIES:
        for series in PRIMARY_SERIES:
            g = [s for s in gold[series] if s["after"]["d"]]
            for cond in Condition:
                path = MEMORY / strategy / f"{series}.{cond}.d.json"
                record = Record.model_validate_json(path.read_text(encoding="utf-8"))
                matches = score_record(series, g, record, f"{strategy}.{series}.{cond}", budget)
                matched = {m["record_row"].lower() for m in matches if m["record_row"]}
                extra = sum(s.slot.lower() not in matched for s in record.slots)
                for m in matches:
                    rows.append({"strategy": strategy, "series": series, "condition": str(cond),
                                 "record_slots": len(record.slots), "extra_slots": extra, **m})
                print(f"{strategy:15s} {series} {cond!s:12s} " + " ".join(
                    f"{k}={sum(m['status'] == k for m in matches)}"
                    for k in ("correct", "stale", "wrong", "missing"))
                    + f" extra={extra} (total ${budget.spent:.3f})", flush=True)
    write_jsonl(RESULTS / "memory_matches.jsonl", rows)
    df = pd.DataFrame(rows)
    table = (df.groupby(["strategy", "condition"]).status.value_counts(normalize=True)
             .unstack(fill_value=0).reindex(columns=["correct", "stale", "wrong", "missing"]))
    table.to_csv(RESULTS / "memory_scores.csv")
    print("\nShare of the 100 verified facts after meeting d:")
    print(table.map(lambda x: f"{x:.0%}").to_string())
    changed = df[df.changed]
    print("\nOnly facts that changed between meetings b-d:")
    print(changed.groupby(["strategy", "condition"]).status.value_counts(normalize=True)
          .unstack(fill_value=0).reindex(columns=["correct", "stale", "wrong", "missing"])
          .map(lambda x: f"{x:.0%}").to_string())
    print(f"\nSpent ${budget.spent:.3f}.")


if __name__ == "__main__":
    main()
