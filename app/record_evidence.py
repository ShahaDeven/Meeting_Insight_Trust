"""Recover the quotes behind changes the review gate already auto-wrote.

The gate checked each written change against a transcript quote, but runs made before
2026-10-26 did not save that quote. This replays only the verifier on those exact changes (the
records themselves are not touched) and saves {series}.{cond}.{meeting}.evidence.json next to
them. A change whose quote is not re-found is kept, marked as such, never dropped.

  python -m app.record_evidence --series TS3003 --conditions farfield clean
"""

import argparse
import json
import time

from core.config import Condition
from core.llm import Budget, client
from core.transcript import load_transcript
from extract.extractor import EXTRACT_MODEL, STAGES, render
from extract.memory_strategies import MEMORY, VERIFY_SYSTEM, Record, _changes, _Checks
from extract.quotes import locate

GATED = MEMORY / "gated_resummarize"


def recover(series: str, cond: str, budget: Budget) -> None:
    prev = []
    for part in "abcd":
        path = GATED / f"{series}.{cond}.{part}.json"
        record = Record.model_validate_json(path.read_text(encoding="utf-8")).slots
        out = path.with_suffix(".evidence.json")
        changes = _changes(prev, record)  # queued changes never reached the record
        if out.exists() or not changes:
            if not out.exists():
                out.write_text("[]", encoding="utf-8")
            prev = record
            continue
        t = load_transcript(f"{series}{part}", cond)
        listing = "\n".join(
            f"{n}. {name}: " + (f'"{old}" -> ' if old else "new: ")
            + (f'"{slot.value}"' if slot else "REMOVED") for n, (name, old, slot) in enumerate(changes, 1))
        budget.check()
        t0 = time.time()
        resp = client.messages.parse(
            model=EXTRACT_MODEL, max_tokens=16000, system=VERIFY_SYSTEM,
            messages=[{"role": "user", "content": f"Proposed changes:\n{listing}\n\n"
                                                  f"Transcript ({STAGES[part]}):\n{render(t)}"}],
            output_format=_Checks, output_config={"effort": "medium"})
        budget.charge(EXTRACT_MODEL, resp.usage, f"evidence:{series}{part}.{cond}", time.time() - t0)
        checks = {c.change: c for c in resp.parsed_output.checks}
        rows = []
        for n, (name, old, slot) in enumerate(changes, 1):
            c = checks.get(n)
            hit = locate(t, c.line, c.quote) if c and c.quote and c.line is not None else None
            row = {"slot": name, "old": old, "new": slot.value if slot else None}
            if hit:
                turn, words, _ = hit
                row |= {"quote": " ".join(w.text for w in words), "speaker": turn.speaker,
                        "start": words[0].start}
            else:
                row["quote"] = None  # written by the original run; its quote was not re-found
            rows.append(row)
        out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"{series}{part} {cond}: {len(rows)} written changes, "
              f"{sum(r['quote'] is not None for r in rows)} with a re-found quote", flush=True)
        prev = record
    print(f"Spent ${budget.spent:.3f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--series", default="TS3003")
    p.add_argument("--conditions", nargs="+", default=["farfield", "clean"])
    a = p.parse_args()
    budget = Budget()
    for cond in a.conditions:
        recover(a.series, str(Condition(cond)), budget)
