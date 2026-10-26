import { useMemo } from "react";
import type { CondData, MeetingData } from "../types";
import { ROLES, ROLE_LABEL, TYPE_LABEL, clock } from "../types";

const W = 1000;
const LEFT = 96;
const PLOT = W - LEFT - 8;
const ROW = { pins: 18, conf: 40, lanes: 66 };
const LANE_H = 12;
const H = ROW.lanes + ROLES.length * (LANE_H + 4) + 20;

/** Low recognizer confidence darkens toward amber; a human transcript has no confidence. */
function confFill(c: number | null): string {
  if (c === null) return "transparent";
  const t = Math.min(1, Math.max(0, (0.9 - c) / 0.2)); // 90%+ blank, 70% or less full
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${mix(26, 191)},${mix(31, 131)},${mix(39, 32)})`;  // panel -> amber
}

interface Props {
  meeting: MeetingData;
  data: CondData;
  time: number;
  active?: string;
  onSeek: (t: number) => void;
  onPin: (id: string, t: number) => void;
}

export default function Ribbon({ meeting, data, time, active, onSeek, onPin }: Props) {
  const dur = meeting.duration;
  const x = (t: number) => LEFT + (t / dur) * PLOT;
  const ticks = useMemo(() => Array.from({ length: Math.floor(dur / 300) + 1 }, (_, i) => i * 300), [dur]);
  const held = data.insights.filter((i) => i.lane === "review").length;

  const clickPlot = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    if (px >= LEFT) onSeek(((px - LEFT) / PLOT) * dur);
  };

  return (
    <section className="ribbon" aria-labelledby="ribbon-title">
      <div className="ribbon-head">
        <h2 id="ribbon-title">
          Meeting {meeting.meeting}, {meeting.stage} ({Math.round(dur / 60)} min): {data.insights.length} insights,{" "}
          {held} held for review
        </h2>
        <span className="meta">Click anywhere to listen from that moment</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} onClick={clickPlot} role="img"
           aria-label={`Timeline of ${data.insights.length} insights across the meeting, with recognizer confidence and who was speaking`}>
        <text className="lane-label" x={0} y={ROW.pins + 4}>Insights</text>
        <text className="lane-label" x={0} y={ROW.conf + 9}>Recognizer</text>
        {data.confidence.length ? (
          data.confidence.map((c, i) => (
            <rect key={i} x={x(i * 10)} y={ROW.conf} width={Math.max(0.5, x(10) - LEFT)} height={14} fill={confFill(c)} />
          ))
        ) : (
          <text className="axis" x={LEFT} y={ROW.conf + 10}>Human transcript: no recognizer confidence</text>
        )}
        {ROLES.map((role, r) => {
          const y = ROW.lanes + r * (LANE_H + 4);
          return (
            <g key={role}>
              <text className="lane-label" x={0} y={y + 10}>{ROLE_LABEL[role]}</text>
              <line x1={LEFT} x2={W - 8} y1={y + LANE_H / 2} y2={y + LANE_H / 2} stroke="var(--rule)" />
              {data.turns.filter((t) => t.speaker === role).map((t, i) => (
                <rect key={i} x={x(t.start)} y={y + 2} width={Math.max(1, x(t.end) - x(t.start))} height={LANE_H - 4}
                      rx={1.5} fill="var(--ink-2)" opacity={0.55} />
              ))}
            </g>
          );
        })}
        {ticks.map((t) => (
          <text key={t} className="axis" x={x(t)} y={H - 4} textAnchor="middle">{clock(t)}</text>
        ))}
        <line x1={x(time)} x2={x(time)} y1={8} y2={H - 16} stroke="var(--ink)" strokeWidth={1.5} />
        {data.insights.map((ins) => {
          const t = ins.quotes[0].start;
          const cx = x(t);
          const isActive = ins.id === active;
          const label = `${TYPE_LABEL[ins.type]} at ${clock(t)}, risk ${ins.risk.toFixed(2)}, ${ins.lane === "review" ? "held for review" : "auto-write"}: ${ins.summary}`;
          return (
            <g key={ins.id} role="button" tabIndex={0} aria-label={label}
               onClick={(e) => { e.stopPropagation(); onPin(ins.id, t); }}
               onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPin(ins.id, t); } }}
               style={{ cursor: "pointer" }}>
              <title>{label}</title>
              <rect x={cx - 8} y={ROW.pins - 10} width={16} height={20} fill="transparent" />
              {ins.lane === "review" ? (
                <rect x={cx - 5.5} y={ROW.pins - 5.5} width={11} height={11} transform={`rotate(45 ${cx} ${ROW.pins})`}
                      className="pin-review" stroke={isActive ? "var(--ink)" : "var(--panel)"} strokeWidth={2} />
              ) : (
                <circle cx={cx} cy={ROW.pins} r={5.5} className="pin-auto"
                        stroke={isActive ? "var(--ink)" : "var(--panel)"} strokeWidth={2} />
              )}
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="5" className="pin-auto" /></svg>Auto-write</span>
        <span><svg width="12" height="12" aria-hidden="true"><rect x="2.5" y="2.5" width="7" height="7" transform="rotate(45 6 6)" className="pin-review" /></svg>Held for review</span>
        {data.confidence.length > 0 && (
          <span><i className="swatch" style={{ background: "linear-gradient(90deg, #262a2f, #bf8320)" }} />Recognizer less sure</span>
        )}
      </div>
    </section>
  );
}
