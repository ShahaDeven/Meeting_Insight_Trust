import type { Insight, Lane } from "../types";
import { TYPE_LABEL } from "../types";

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

function Item({ i, threshold, active, onPlay }: { i: Insight; threshold: number; active: boolean; onPlay: (id: string, t: number) => void }) {
  return (
    <li className={`insight${active ? " active" : ""}`}>
      <div className="row1">
        <span className="kind">{TYPE_LABEL[i.type]}</span>
        <Risk value={i.risk} threshold={threshold} lane={i.lane} />
      </div>
      <p className="summary">{i.summary}</p>
      <Facts i={i} />
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
        <ul className="why" aria-label={i.lane === "review" ? "Why it was held" : "Why it was written"}>
          {i.why.map((d, k) => (
            <li key={k}>
              <span className={`dir ${d.raises_risk ? "up" : "down"}`} aria-hidden="true">{d.raises_risk ? "↑" : "↓"}</span>
              <span>{d.text}<span className="visually-hidden">{d.raises_risk ? " (raises risk)" : " (lowers risk)"}</span></span>
            </li>
          ))}
        </ul>
      )}
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
  threshold: number;
  active?: string;
  onPlay: (id: string, t: number) => void;
}

export default function Lanes({ insights, threshold, active, onPlay }: Props) {
  const lanes: { lane: Lane; title: string; note: string }[] = [
    { lane: "review", title: "Held for review", note: "A person confirms these before they reach the CRM" },
    { lane: "auto", title: "Written automatically", note: "Low risk: goes straight to the record" },
  ];
  return (
    <section className="panel" aria-label="Insights by write decision">
      {lanes.map(({ lane, title, note }) => {
        const items = insights.filter((i) => i.lane === lane).sort((a, b) => b.risk - a.risk);
        return (
          <div className={`lane ${lane}`} key={lane}>
            <div className="lane-title">
              <h3>{title} <span className="count">({items.length})</span></h3>
              <p>{note}</p>
            </div>
            {items.length ? (
              <ul>{items.map((i) => <Item key={i.id} i={i} threshold={threshold} active={i.id === active} onPlay={onPlay} />)}</ul>
            ) : (
              <p style={{ padding: "0 16px 14px", margin: 0, color: "var(--ink-3)" }}>Nothing in this meeting crossed the review threshold.</p>
            )}
          </div>
        );
      })}
    </section>
  );
}
