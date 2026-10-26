import { useEffect, useState } from "react";
import type { Cond, Decision, Due, InsightType, MeetingPart, SeriesData, Target } from "../types";
import { ROLE_LABEL, TYPE_LABEL, dueText, prettySlot } from "../types";

type Dest = "record" | "tasks" | "calendar";
const PARTS: MeetingPart[] = ["a", "b", "c", "d"];
const GROUPS: { type: InsightType; title: string }[] = [
  { type: "decision", title: "Decisions" },
  { type: "cost_figure", title: "Budget" },
  { type: "action_item", title: "Next steps" },
  { type: "open_risk", title: "Risks" },
];

export function StatusChip({ lane, decision }: { lane: "auto" | "review" | "written" | "held"; decision?: Decision }) {
  if (decision?.action === "approved") return <span className="chip ok">Approved</span>;
  if (decision?.action === "edited") return <span className="chip ok">Edited and approved</span>;
  if (decision?.action === "rejected") return <span className="chip no">Rejected</span>;
  return lane === "auto" || lane === "written"
    ? <span className="chip auto">Written automatically</span>
    : <span className="chip wait">Waiting for approval</span>;
}

export function DecisionButtons({ id, value, decision, decide }: {
  id: string; value: string; decision?: Decision; decide: (id: string, d: Decision | undefined) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  if (decision) {
    return <button className="link" onClick={() => decide(id, undefined)}>Undo</button>;
  }
  if (editing) {
    return (
      <span className="edit-row">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Edited value" />
        <button className="act ok" onClick={() => { decide(id, { action: "edited", value: draft }); setEditing(false); }}>Save</button>
        <button className="link" onClick={() => setEditing(false)}>Cancel</button>
      </span>
    );
  }
  return (
    <span className="actions">
      <button className="act ok" onClick={() => decide(id, { action: "approved" })}>Approve</button>
      <button className="act" onClick={() => setEditing(true)}>Edit</button>
      <button className="act no" onClick={() => decide(id, { action: "rejected" })}>Reject</button>
    </span>
  );
}

function Source({ part, at, start, onGo, label }: {
  part: MeetingPart; at: string | null; start?: number; onGo: (t: Target) => void; label?: string;
}) {
  if (start === undefined || at === null) return <span className="src muted">No quote re-found</span>;
  return (
    <button className="src" onClick={() => onGo({ view: "review", part, at: start })}>
      ▶ {label ?? `Meeting ${part}, ${at}`}
    </button>
  );
}

const owner = (o: string | null) => (o === "team" ? "Whole team" : o ? `${o} (${ROLE_LABEL[o] ?? o})` : "Not named");

interface Props {
  series: SeriesData;
  cond: Cond;
  part: MeetingPart;
  setPart: (p: MeetingPart) => void;
  dest: Dest;
  setDest: (d: Dest) => void;
  focus?: string;
  decisions: Record<string, Decision>;
  decide: (id: string, d: Decision | undefined) => void;
  onGo: (t: Target) => void;
}

export default function Destinations({ series, cond, part, setPart, dest, setDest, focus, decisions, decide, onGo }: Props) {
  const data = series.conditions[cond];
  const stages = Object.fromEntries(series.meetings.map((m) => [m.part, m.stage]));

  useEffect(() => {
    if (!focus) return;
    const el = document.getElementById(`focus-${focus}`);
    el?.scrollIntoView({ block: "center" });
  }, [focus, dest, part]);

  const isFocus = (id: string) => (focus === id ? " focused" : "");

  return (
    <>
      <p className="sim-banner">
        Simulated destinations. This is what the meeting assistant would write; nothing is sent to any real system,
        and Approve, Edit and Reject change this page only.
      </p>
      <div className="toolbar">
        <div>
          <span className="control-label" id="dest-label">Destination</span>
          <div className="segmented" role="group" aria-labelledby="dest-label">
            {([["record", "Project record"], ["tasks", "Tasks"], ["calendar", "Calendar"]] as const).map(([d, l]) => (
              <button key={d} aria-pressed={dest === d} onClick={() => setDest(d)}>{l}</button>
            ))}
          </div>
        </div>
        {dest !== "calendar" && (
          <div>
            <span className="control-label" id="after-label">{dest === "record" ? "Record after meeting" : "Tasks created up to meeting"}</span>
            <div className="segmented" role="group" aria-labelledby="after-label">
              {PARTS.map((p) => (
                <button key={p} aria-pressed={part === p} onClick={() => setPart(p)}>{p}: {stages[p]}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      {dest === "record" && (() => {
        const f = data.fields[part];
        const updated = new Map(f.written.map((w) => [w.slot.toLowerCase(), w]));
        const notes = data.notes[part];
        return (
          <div className="dest-grid">
            <section className="panel" aria-labelledby="fields-title">
              <div className="panel-head">
                <h2 id="fields-title">Current fields after meeting {part}</h2>
                <span className="meta">
                  Kept up to date by re-summarizing; each change needs a quote from the meeting. {f.written.length} written,
                  {" "}{f.held.length} waiting.
                </span>
              </div>
              {f.held.length > 0 && (
                <div className="held-block">
                  <h3>Waiting for approval</h3>
                  <ul className="records">
                    {f.held.map((h) => {
                      const id = `hold:${cond}:${part}:${h.slot}`;
                      return (
                        <li key={id} id={`focus-${id}`} className={`record pending${isFocus(id)}`}>
                          <div className="record-head">
                            <strong>{prettySlot(h.slot)}</strong>
                            <StatusChip lane="held" decision={decisions[id]} />
                          </div>
                          <div className="change">
                            <span className="old">{h.old ?? "not set"}</span>
                            <span className="arrow" aria-label="changes to">→</span>
                            <span className="new">{decisions[id]?.action === "edited" ? (decisions[id] as { value: string }).value : h.new ?? "removed"}</span>
                          </div>
                          <p className="why-held">Held: no quote from meeting {part} backs this change ({h.verifier_said}).</p>
                          <DecisionButtons id={id} value={h.new ?? ""} decision={decisions[id]} decide={decide} />
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              {GROUPS.map((g) => {
                const slots = f.slots.filter((s) => s.category === g.type);
                if (!slots.length) return null;
                return (
                  <div key={g.type} className="field-group">
                    <h3>{g.title}</h3>
                    <ul className="records">
                      {slots.map((s) => {
                        const w = updated.get(s.slot.toLowerCase());
                        const id = `field:${s.slot}`;
                        return (
                          <li key={s.slot} id={`focus-${id}`} className={`record${w ? " changed" : ""}${isFocus(id)}`}>
                            <div className="record-head">
                              <strong>{prettySlot(s.slot)}</strong>
                              {w && <span className="chip auto">Updated in meeting {part}</span>}
                            </div>
                            <p className="value">{s.value}</p>
                            {w && (
                              <div className="history">
                                {w.old && <span className="old">Was: {w.old}</span>}
                                <span className="evidence">
                                  {w.quote ? <>Backed by {w.speaker}: “{w.quote}” </> : null}
                                  <Source part={part} at={w.at} start={w.start} onGo={onGo} />
                                </span>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </section>

            <section className="panel" aria-labelledby="notes-title">
              <div className="panel-head">
                <h2 id="notes-title">Meeting notes, meeting {part}</h2>
                <span className="meta">One entry per insight; the risk policy decides auto-write or review.</span>
              </div>
              {GROUPS.map((g) => {
                const items = notes.filter((n) => n.type === g.type);
                if (!items.length) return null;
                return (
                  <div key={g.type} className="field-group">
                    <h3>{g.title}</h3>
                    <ul className="records">
                      {items.map((n) => (
                        <li key={n.id} id={`focus-${n.id}`} className={`record${n.lane === "review" ? " pending" : ""}${isFocus(n.id)}`}>
                          <div className="record-head">
                            <span>{TYPE_LABEL[n.type]}{n.owner ? `, ${owner(n.owner)}` : ""}{n.value ? `, ${n.value}` : ""}</span>
                            <StatusChip lane={n.lane} decision={decisions[n.id]} />
                          </div>
                          <p className="value">{decisions[n.id]?.action === "edited" ? (decisions[n.id] as { value: string }).value : n.summary}</p>
                          <div className="history">
                            <span className="evidence">
                              Risk {Math.round(n.risk * 100)}% (review line {Math.round(n.threshold * 100)}%){" "}
                              <Source part={part} at={n.quote.at} start={n.quote.start} onGo={onGo} />
                              {n.field && (
                                <button className="link" onClick={() => onGo({ view: "destinations", dest: "record", part, focus: `field:${n.field}` })}>
                                  Field: {prettySlot(n.field)}
                                </button>
                              )}
                            </span>
                          </div>
                          {n.lane === "review" && <DecisionButtons id={n.id} value={n.summary} decision={decisions[n.id]} decide={decide} />}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </section>
          </div>
        );
      })()}

      {dest === "tasks" && (
        <section className="panel" aria-labelledby="tasks-title">
          <div className="panel-head">
            <h2 id="tasks-title">Tasks</h2>
            <span className="meta">Action items become tasks with an owner role and a due point; held ones wait for approval.</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="facts">
              <thead><tr><th>Owner</th><th>Task</th><th>Due</th><th>From</th><th>Status</th></tr></thead>
              <tbody>
                {data.tasks.filter((t) => t.meeting <= part).map((t) => (
                  <tr key={t.id} id={`focus-${t.id}`} className={isFocus(t.id).trim()}>
                    <td className="slot">{owner(t.owner)}</td>
                    <td>{decisions[t.id]?.action === "edited" ? (decisions[t.id] as { value: string }).value : t.task}</td>
                    <td>{dueText(t.due as Due, stages)}{t.deadline && t.due.kind !== "text" ? <div className="muted">said: “{t.deadline}”</div> : null}</td>
                    <td><Source part={t.meeting} at={t.quote.at} start={t.quote.start} onGo={onGo} /></td>
                    <td>
                      <StatusChip lane={t.lane} decision={decisions[t.id]} />
                      {t.lane === "review" && <div><DecisionButtons id={t.id} value={t.task} decision={decisions[t.id]} decide={decide} /></div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {dest === "calendar" && (
        <section className="panel" aria-labelledby="cal-title">
          <div className="panel-head">
            <h2 id="cal-title">{series.date}</h2>
            <span className="meta">All four meetings took place that day; the corpus does not record start times, so they are shown in order.</span>
          </div>
          <ol className="calendar">
            {series.meetings.map((m) => {
              const due = data.tasks.filter((t) => t.due.kind === "meeting" && t.due.part === m.part);
              return (
                <li key={m.part} className="cal-event">
                  <div className="cal-head">
                    <strong>Meeting {m.part}: {m.stage}</strong>
                    <span className="muted">{Math.round(m.duration / 60)} min</span>
                    <button className="link" onClick={() => onGo({ view: "review", part: m.part, at: 0 })}>Open meeting</button>
                  </div>
                  {due.length ? (
                    <ul className="records">
                      {due.map((t) => (
                        <li key={t.id} id={`focus-${t.id}`} className={`record${t.lane === "review" ? " pending" : ""}${isFocus(t.id)}`}>
                          <div className="record-head">
                            <span>Follow-up due: {owner(t.owner)}</span>
                            <StatusChip lane={t.lane} decision={decisions[t.id]} />
                          </div>
                          <p className="value">{t.task}</p>
                          <Source part={t.meeting} at={t.quote.at} start={t.quote.start} onGo={onGo} label={`Set in meeting ${t.meeting}, ${t.quote.at}`} />
                        </li>
                      ))}
                    </ul>
                  ) : <p className="muted cal-empty">No follow-ups due at this meeting.</p>}
                </li>
              );
            })}
            {(() => {
              const after = data.tasks.filter((t) => t.due.kind === "after");
              const loose = data.tasks.filter((t) => t.due.kind === "text");
              return (
                <li className="cal-event">
                  <div className="cal-head"><strong>After the series, or not tied to a meeting</strong></div>
                  {after.length || loose.length ? (
                    <ul className="records">
                      {after.map((t) => (
                        <li key={t.id} id={`focus-${t.id}`} className={`record${isFocus(t.id)}`}>
                          <div className="record-head"><span>{owner(t.owner)}</span><StatusChip lane={t.lane} decision={decisions[t.id]} /></div>
                          <p className="value">{t.task}</p>
                        </li>
                      ))}
                      {loose.map((t) => (
                        <li key={t.id} id={`focus-${t.id}`} className={`record${isFocus(t.id)}`}>
                          <div className="record-head"><span>Deadline without a date: “{t.deadline}”</span><StatusChip lane={t.lane} decision={decisions[t.id]} /></div>
                          <p className="value">{t.task}</p>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="muted cal-empty">Nothing scheduled after the last meeting.</p>}
                </li>
              );
            })()}
          </ol>
        </section>
      )}
    </>
  );
}
