import { useState } from "react";
import type { Cond, FindingsData, MeetingPart, MemoryData, Status, Strategy } from "../types";
import { TYPE_LABEL } from "../types";
import MemoryBars from "./MemoryBars";

const STRATEGY: Record<Strategy, { label: string; about: string }> = {
  re_summarize: {
    label: "Re-summarize",
    about: "After each meeting the model rewrites the whole record from the old record plus the new transcript.",
  },
  evidence_ledger: {
    label: "Evidence ledger",
    about: "A fact may change only when one of the meeting's quote-backed insights supports it; otherwise it keeps its old value.",
  },
  gated_resummarize: {
    label: "Re-summarize with review gate",
    about: "Re-summarize proposes; a change is written only if a quote from the meeting backs it. Unbacked changes wait for a person.",
  },
};
const PARTS: MeetingPart[] = ["a", "b", "c", "d"];
const pretty = (s: string) => { const t = s.replace(/_/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
const STATUS_TEXT: Record<Status, string> = {
  correct: "Current", stale: "Out of date", wrong: "Never true", missing: "Missing",
};

export default function MemoryView({ memory, findings }: { memory: MemoryData; findings: FindingsData }) {
  const [strategy, setStrategy] = useState<Strategy>("gated_resummarize");
  const [cond, setCond] = useState<Cond>("farfield");
  const run = memory.strategies[strategy][cond];
  const finalRecord = new Map(run.records.d.map((s) => [s.slot.toLowerCase(), s.value]));
  const counts = memory.gold.reduce<Record<Status, number>>((acc, g) => {
    const st = run.scored[g.slot]?.status ?? "missing";
    acc[st] += 1;
    return acc;
  }, { correct: 0, stale: 0, wrong: 0, missing: 0 });
  const queued = PARTS.flatMap((p) => (run.review[p] ?? []).map((q) => ({ ...q, meeting: p })));

  return (
    <>
      <p className="section-intro">
        A meeting assistant that keeps a project record (like CRM fields) has to hold the latest value
        of every fact across meetings. This is series {memory.series}: four meetings of the same team.
        The answer key is a human-verified record of what was true after each meeting.
      </p>

      <div className="finding" style={{ marginBottom: 20 }}>
        <div>
          <h2>Quote-only updating freezes the record</h2>
          <p>
            Share of 100 verified facts each strategy holds correctly after the fourth meeting, across
            three meeting series. Refusing any change without a quote leaves a quarter of the facts out of
            date: people rarely say “that task is done” in a quotable sentence.
          </p>
          <p>
            Re-summarizing stays current. Adding a review gate (unquoted changes wait for a person) costs about
            two reviews per meeting and gives similar accuracy, with somewhat fewer never-true values on the
            noisier recordings.
          </p>
          <p className="fine">
            Scored by an LLM matcher against the human-verified key; spot-checked, not human-audited.
            Three series is a small sample: treat differences of a few points as noise.
          </p>
        </div>
        <MemoryBars rows={findings.memory} />
      </div>

      <div className="toolbar">
        <div>
          <span className="control-label" id="strat-label">Strategy</span>
          <div className="segmented" role="group" aria-labelledby="strat-label">
            {(Object.keys(STRATEGY) as Strategy[]).map((s) => (
              <button key={s} aria-pressed={strategy === s} onClick={() => setStrategy(s)}>{STRATEGY[s].label}</button>
            ))}
          </div>
        </div>
        <div>
          <span className="control-label" id="mrec-label">Recording</span>
          <div className="segmented" role="group" aria-labelledby="mrec-label">
            <button aria-pressed={cond === "farfield"} onClick={() => setCond("farfield")}>Room microphone</button>
            <button aria-pressed={cond === "clean"} onClick={() => setCond("clean")}>Human transcript</button>
          </div>
        </div>
      </div>
      <p className="section-intro" style={{ marginTop: 0 }}>{STRATEGY[strategy].about}</p>

      <div className="memory-grid">
        <section className="panel" aria-labelledby="facts-title">
          <div className="panel-head">
            <h2 id="facts-title">Answer key vs the record after meeting d</h2>
            <span className="meta">
              {counts.correct} current, {counts.stale} out of date, {counts.wrong} never true, {counts.missing} missing
              (of {memory.gold.length})
            </span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="facts">
              <thead>
                <tr>
                  <th scope="col">Fact</th>
                  {PARTS.map((p) => <th scope="col" key={p}>After {p}: {memory.stages[p]}</th>)}
                  <th scope="col">Record after d</th>
                </tr>
              </thead>
              <tbody>
                {memory.gold.map((g) => {
                  const sc = run.scored[g.slot];
                  const status: Status = sc?.status ?? "missing";
                  const value = sc?.record_row ? finalRecord.get(sc.record_row.toLowerCase()) : undefined;
                  return (
                    <tr key={g.slot}>
                      <td className="slot">{pretty(g.slot)}<br /><span style={{ fontWeight: 400, color: "var(--ink-3)" }}>{TYPE_LABEL[g.category]}</span></td>
                      {PARTS.map((p, k) => {
                        const v = g.after[p];
                        const changed = k > 0 && v && g.after[PARTS[k - 1]] && v !== g.after[PARTS[k - 1]];
                        return <td key={p} className={changed ? "changed" : undefined}>{v ?? <span style={{ color: "var(--ink-3)" }}>not raised</span>}</td>;
                      })}
                      <td>
                        <span className={`status ${status}`}><i aria-hidden="true" />{STATUS_TEXT[status]}</span>
                        {value && <div className="record-value" title={value}>{value}</div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="panel" aria-labelledby="queue-title">
          <div className="panel-head"><h2 id="queue-title">Waiting for a person</h2></div>
          {strategy === "gated_resummarize" ? (
            <div className="queue">
              <p style={{ margin: "10px 0 0", color: "var(--ink-2)", fontSize: 13 }}>
                {queued.length} proposed changes across four meetings had no supporting quote, so they
                were held instead of written.
              </p>
              {PARTS.map((p) => {
                const items = run.review[p] ?? [];
                return items.length ? (
                  <div key={p}>
                    <h3>After meeting {p}</h3>
                    <ul>
                      {items.map((q, k) => (
                        <li key={k}><strong>{pretty(q.slot)}</strong>: {q.old ? `“${q.old}” → ` : "new: "}{q.new ? `“${q.new}”` : "removed"}</li>
                      ))}
                    </ul>
                  </div>
                ) : null;
              })}
            </div>
          ) : (
            <p className="queue" style={{ color: "var(--ink-2)", fontSize: 13, paddingTop: 12 }}>
              This strategy has no review step: every change it makes is written straight to the record.
            </p>
          )}
        </aside>
      </div>
    </>
  );
}
