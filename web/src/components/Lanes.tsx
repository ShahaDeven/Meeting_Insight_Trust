import type { CondData, Insight, InsightType, Lane, Target } from "../types";
import { TYPE_LABEL, prettySlot } from "../types";

const FAILURE: Record<string, string> = {
  content: "not what was said, or later reversed",
  type: "wrong kind (e.g. a suggestion recorded as a decision)",
  owner: "wrong owner",
  number: "wrong figure or deadline",
  none: "",
};

function Facts({ i }: { i: Insight }) {
  const parts = [
    i.type === "action_item" ? `Owner: ${i.owner === "team" ? "whole team" : i.owner ?? "not named"}` : null,
    i.deadline ? `Due: ${i.deadline}` : null,
    i.value ? `Figure: ${i.value}` : null,
  ].filter(Boolean);
  return parts.length ? <span className="facts">{parts.join("; ")}</span> : null;
}

function Risk({ value, threshold, lane }: { value: number; threshold: number; lane: Lane }) {
  const scale = (v: number) => `${Math.min(100, (v / 0.7) * 100)}%`;
  return (
    <span className="risk" title={`Estimated chance this insight is wrong: ${(value * 100).toFixed(0)}%. Held for review at ${(threshold * 100).toFixed(0)}% or above.`}>
      Risk {(value * 100).toFixed(0)}%
      <span className="bar" aria-hidden="true">
        <i style={{ width: scale(value), background: lane === "review" ? "var(--review)" : "var(--auto)" }} />
        <span className="tick" style={{ left: scale(threshold) }} />
      </span>
    </span>
  );
}

function Lands({ i, onGo }: { i: Insight; onGo: (t: Target) => void }) {
  const status = i.lane === "review" ? "pending approval" : "written";
  const links: { label: string; target: Target }[] = [
    { label: `Meeting notes (${status})`, target: { view: "destinations", dest: "record", part: i.meeting, focus: i.id } },
  ];
  if (i.destinations.includes("tasks"))
    links.push({ label: `Tasks (${status})`, target: { view: "destinations", dest: "tasks", part: i.meeting, focus: i.id } });
  if (i.destinations.includes("calendar"))
    links.push({ label: "Calendar follow-up", target: { view: "destinations", dest: "calendar", part: i.meeting, focus: i.id } });
  if (i.field)
    links.push({ label: `Record field: ${prettySlot(i.field)}`,
                 target: { view: "destinations", dest: "record", part: i.meeting, focus: `field:${i.field}` } });
  return (
    <div className="lands">
      <span className="lands-label">Lands in</span>
      {links.map((l) => (
        <button key={l.label} className="go" onClick={() => onGo(l.target)}>{l.label}</button>
      ))}
    </div>
  );
}

function Item({ i, active, onPlay, onGo }: { i: Insight; active: boolean; onPlay: (id: string, t: number) => void;
                                             onGo: (t: Target) => void }) {
  const line = `${Math.round(i.threshold * 100)}%`;
  return (
    <li className={`insight${active ? " active" : ""}`}>
      <div className="row1">
        <span className="kind">{TYPE_LABEL[i.type]}</span>
        <Risk value={i.risk} threshold={i.threshold} lane={i.lane} />
      </div>
      <p className="summary">{i.summary}</p>
      <Facts i={i} />
      <p className="lane-why">
        {i.lane === "review"
          ? `Held: risk ${Math.round(i.risk * 100)}% is at or above the ${line} review line for ${TYPE_LABEL[i.type].toLowerCase()}s.`
          : `Written: risk ${Math.round(i.risk * 100)}% is below the ${line} review line for ${TYPE_LABEL[i.type].toLowerCase()}s.`}
      </p>
      {i.quotes.map((q, k) => (
        <blockquote className="quote" key={k}>
          <button className="play" onClick={() => onPlay(i.id, q.start)} aria-label={`Play quote at ${q.at}`}>
            <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 1l7 4-7 4z" fill="currentColor" /></svg>
            {q.at}
          </button>
          “{q.text}”
        </blockquote>
      ))}
      {i.why.length > 0 && (
        <p className="why-head">
          {i.lane === "review" ? "What pushed the risk up" : "What kept the risk down"}
          <span> (↑ raises the risk, ↓ lowers it)</span>
        </p>
      )}
      {i.why.length > 0 && (
        <ul className="why" aria-label={i.lane === "review" ? "Why it was held" : "Why it was written"}>
          {i.why.map((d, k) => (
            <li key={k}>
              <span className={`dir ${d.raises_risk ? "up" : "down"}`} aria-hidden="true">{d.raises_risk ? "↑" : "↓"}</span>
              <span>{d.text}<span className="visually-hidden">{d.raises_risk ? " (raises risk)" : " (lowers risk)"}</span></span>
            </li>
          ))}
        </ul>
      )}
      <Lands i={i} onGo={onGo} />
      <details className="check-reviewer">
        <summary>What an independent reviewer said</summary>
        <span className={`verdict ${i.reviewer.verdict}`}>
          {i.reviewer.verdict === "wrong" ? `Wrong: ${FAILURE[i.reviewer.failure]}` : i.reviewer.verdict === "correct" ? "Correct" : "Unsure"}
        </span>{" "}
        {i.reviewer.reason}
        <br />
        <span style={{ color: "var(--ink-3)" }}>
          A strict LLM reviewer reading the human transcript. It agreed with a blind human audit 66% of the time.
        </span>
      </details>
    </li>
  );
}

interface Props {
  insights: Insight[];
  rejected: CondData["rejected"];
  costs: Record<InsightType, number>;
  active?: string;
  onPlay: (id: string, t: number) => void;
  onGo: (t: Target) => void;
}

export default function Lanes({ insights, rejected, costs, active, onPlay, onGo }: Props) {
  const lanes: { lane: Lane; title: string; note: string }[] = [
    { lane: "review", title: "Held for review", note: "Expected cost of a wrong write is higher than a person checking it" },
    { lane: "auto", title: "Written automatically", note: "Low risk for its type: goes straight to the record" },
  ];
  const policy = (Object.keys(costs) as InsightType[])
    .map((t) => `${TYPE_LABEL[t].toLowerCase()} at ${Math.round(100 / costs[t])}%`).join(", ");
  return (
    <section className="panel" aria-label="Insights by write decision">
      <details className="how-to-read">
        <summary>How to read these cards</summary>
        <ul>
          <li><strong>Risk</strong> is the model’s estimate of the chance the insight is wrong, learned from meetings it
            never saw.</li>
          <li>The small tick on the risk bar is the <strong>review line</strong> for that kind of insight. It is lower for
            costly mistakes: a wrong action item or cost figure is held at a lower risk than a wrong open risk.</li>
          <li>Above the line, the insight is <strong>held for review</strong>; below it, it is <strong>written
            automatically</strong>. With no supporting quote at all, it is <strong>rejected</strong>.</li>
          <li>The ↑ and ↓ lines are the biggest reasons the risk came out where it did, each with its own number.</li>
          <li><strong>Lands in</strong> shows where the write goes: meeting notes, tasks, the calendar or a record field.</li>
          <li>“What an independent reviewer said” is a separate check against the human transcript, for comparison.</li>
        </ul>
      </details>
      {lanes.map(({ lane, title, note }) => {
        const items = insights.filter((i) => i.lane === lane).sort((a, b) => b.risk - a.risk);
        return (
          <div className={`lane ${lane}`} key={lane}>
            <div className="lane-title">
              <h3>{title} <span className="count">({items.length})</span></h3>
              <p>{note}</p>
            </div>
            {items.length ? (
              <ul>{items.map((i) => <Item key={i.id} i={i} active={i.id === active} onPlay={onPlay} onGo={onGo} />)}</ul>
            ) : (
              <p style={{ padding: "0 16px 14px", margin: 0, color: "var(--ink-3)" }}>Nothing in this meeting crossed the review threshold.</p>
            )}
          </div>
        );
      })}
      <div className="lane rejected">
        <div className="lane-title">
          <h3>Rejected <span className="count">({rejected.length})</span></h3>
          <p>No quote in the transcript backs these, so they are never written</p>
        </div>
        {rejected.length ? (
          <ul>
            {rejected.map((r, k) => (
              <li className="insight" key={k}>
                <span className="kind">{TYPE_LABEL[r.type]}</span>
                <p className="summary">{r.summary}</p>
                <span className="facts">Cited “{r.quotes[0] ?? ""}”, which is not in the transcript</span>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ padding: "0 16px 14px", margin: 0, color: "var(--ink-3)" }}>
            Every insight from this recording was tied to a real quote.
          </p>
        )}
      </div>
      <p className="policy-note">Review thresholds by type: {policy}. They follow from a stated cost: a wrong
        action item is priced at {costs.action_item} reviews, a wrong cost figure at {costs.cost_figure}.</p>
    </section>
  );
}
