import { useMemo, useState } from "react";
import type { Cond, Decision, MeetingPart, SeriesData, Target } from "../types";
import { TYPE_LABEL, prettySlot } from "../types";
import { StatusChip } from "./Destinations";

type Status = "written" | "waiting" | "approved" | "rejected";
interface Row {
  id: string;
  part: MeetingPart;
  start: number | null;
  at: string | null;
  writer: "Record updater" | "Notes writer";
  destination: "Project record" | "Meeting notes" | "Tasks" | "Calendar";
  item: string;
  before: string | null;
  after: string | null;
  lane: "auto" | "review" | "written" | "held";
  reason: string;
  open: Target;
}

function status(r: Row, d?: Decision): Status {
  if (d?.action === "rejected") return "rejected";
  if (d) return "approved";
  return r.lane === "auto" || r.lane === "written" ? "written" : "waiting";
}

export default function WriteLog({ series, cond, decisions, onGo }: {
  series: SeriesData; cond: Cond; decisions: Record<string, Decision>; onGo: (t: Target) => void;
}) {
  const [st, setSt] = useState<Status | "all">("all");
  const [dest, setDest] = useState<Row["destination"] | "all">("all");
  const data = series.conditions[cond];

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    for (const m of series.meetings) {
      const p = m.part;
      const f = data.fields[p];
      for (const w of f.written) {
        out.push({ id: `field:${cond}:${p}:${w.slot}`, part: p, start: w.start ?? null, at: w.at,
                   writer: "Record updater", destination: "Project record", item: prettySlot(w.slot),
                   before: w.old, after: w.new, lane: "written",
                   reason: w.quote ? `Backed by a quote from meeting ${p}` : "Written by the gate; quote not re-found",
                   open: { view: "destinations", dest: "record", part: p, focus: `field:${w.slot}` } });
      }
      for (const h of f.held) {
        const id = `hold:${cond}:${p}:${h.slot}`;
        out.push({ id, part: p, start: null, at: null, writer: "Record updater", destination: "Project record",
                   item: prettySlot(h.slot), before: h.old, after: h.new, lane: "held",
                   reason: `No quote from meeting ${p} backs it (${h.verifier_said})`,
                   open: { view: "destinations", dest: "record", part: p, focus: id } });
      }
      for (const n of data.notes[p]) {
        const why = n.lane === "review"
          ? `Risk ${Math.round(n.risk * 100)}% at or above the ${Math.round(n.threshold * 100)}% line`
          : `Risk ${Math.round(n.risk * 100)}% below the ${Math.round(n.threshold * 100)}% line`;
        out.push({ id: n.id, part: p, start: n.quote.start, at: n.quote.at, writer: "Notes writer",
                   destination: "Meeting notes", item: TYPE_LABEL[n.type], before: null, after: n.summary,
                   lane: n.lane, reason: why, open: { view: "destinations", dest: "record", part: p, focus: n.id } });
      }
    }
    for (const t of data.tasks) {
      const why = `Action item: risk ${Math.round(t.risk * 100)}% vs ${Math.round(t.threshold * 100)}% line`;
      out.push({ id: t.id, part: t.meeting, start: t.quote.start, at: t.quote.at, writer: "Notes writer",
                 destination: "Tasks", item: t.owner ?? "No owner", before: null, after: t.task, lane: t.lane,
                 reason: why, open: { view: "destinations", dest: "tasks", part: t.meeting, focus: t.id } });
      if (t.due.kind === "meeting" || t.due.kind === "after") {
        out.push({ id: t.id, part: t.meeting, start: t.quote.start, at: t.quote.at, writer: "Notes writer",
                   destination: "Calendar", item: t.due.kind === "meeting" ? `Follow-up at meeting ${t.due.part}` : "After the series",
                   before: null, after: t.task, lane: t.lane, reason: why,
                   open: { view: "destinations", dest: "calendar", part: t.meeting, focus: t.id } });
      }
    }
    return out.sort((a, b) => a.part.localeCompare(b.part) || (a.start ?? 1e9) - (b.start ?? 1e9));
  }, [series, cond, data]);

  const shown = rows.filter((r) => (st === "all" || status(r, decisions[r.id]) === st) && (dest === "all" || r.destination === dest));
  const count = (s: Status) => rows.filter((r) => status(r, decisions[r.id]) === s).length;

  return (
    <>
      <p className="sim-banner">
        Every write the assistant made across the four meetings, in order. Two writers: the notes writer logs each
        insight (risk policy decides auto-write or review); the record updater keeps the current fields (each change
        needs a quote). Simulated: nothing reaches a real system.
      </p>
      <div className="toolbar">
        <div>
          <span className="control-label" id="st-label">Status</span>
          <div className="segmented" role="group" aria-labelledby="st-label">
            {([["all", `All (${rows.length})`], ["written", `Written (${count("written")})`],
               ["waiting", `Waiting (${count("waiting")})`], ["approved", `Approved (${count("approved")})`],
               ["rejected", `Rejected (${count("rejected")})`]] as const).map(([k, l]) => (
              <button key={k} aria-pressed={st === k} onClick={() => setSt(k)}>{l}</button>
            ))}
          </div>
        </div>
        <div>
          <label className="control-label" htmlFor="dest-filter">Destination</label>
          <select id="dest-filter" className="select" value={dest} onChange={(e) => setDest(e.target.value as Row["destination"] | "all")}>
            {["all", "Project record", "Meeting notes", "Tasks", "Calendar"].map((d) => (
              <option key={d} value={d}>{d === "all" ? "All destinations" : d}</option>
            ))}
          </select>
        </div>
      </div>
      <section className="panel">
        <div style={{ overflowX: "auto" }}>
          <table className="facts log">
            <thead>
              <tr><th>When</th><th>Writer</th><th>Destination</th><th>Change</th><th>Status and reason</th><th>Go to</th></tr>
            </thead>
            <tbody>
              {shown.map((r, k) => (
                <tr key={`${r.id}-${r.destination}-${k}`}>
                  <td className="when">Meeting {r.part}{r.at ? `, ${r.at}` : ""}</td>
                  <td>{r.writer}</td>
                  <td>{r.destination}<div className="muted">{r.item}</div></td>
                  <td className="change-cell">
                    {r.before && <div className="old">{r.before}</div>}
                    {r.before && <div className="arrow" aria-label="changes to">↓</div>}
                    <div>{decisions[r.id]?.action === "edited" ? (decisions[r.id] as { value: string }).value : r.after ?? "removed"}</div>
                  </td>
                  <td><StatusChip lane={r.lane} decision={decisions[r.id]} /><div className="muted">{r.reason}</div></td>
                  <td className="go-cell">
                    <button className="go" onClick={() => onGo(r.open)}>Open</button>
                    {r.start !== null && <button className="go" onClick={() => onGo({ view: "review", part: r.part, at: r.start! })}>▶ Source</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!shown.length && <p className="muted" style={{ padding: 16 }}>No writes match these filters.</p>}
        </div>
      </section>
    </>
  );
}
