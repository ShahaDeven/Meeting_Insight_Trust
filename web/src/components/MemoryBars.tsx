import { useState } from "react";
import type { FindingsData, Status, Strategy } from "../types";
import { pct } from "../types";

const ORDER: Status[] = ["correct", "stale", "wrong", "missing"];
const FILL: Record<Status, string> = {
  correct: "var(--auto)", stale: "var(--review)", wrong: "var(--fault)", missing: "#c9cfd6",
};
const LABEL: Record<Status, string> = {
  correct: "Current", stale: "Out of date", wrong: "Never true", missing: "Missing",
};
const STRATEGIES: { id: Strategy; label: string }[] = [
  { id: "evidence_ledger", label: "Evidence ledger" },
  { id: "re_summarize", label: "Re-summarize" },
  { id: "gated_resummarize", label: "Re-summarize with review gate" },
];
const CONDS = [{ id: "clean", label: "Human transcript" }, { id: "farfield", label: "Room mic" }];

const W = 560, LEFT = 128, BAR = 16, GAP = 6, HEADER = 26;
const PLOT = W - LEFT - 12;

export default function MemoryBars({ rows }: { rows: FindingsData["memory"] }) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string }>();
  const groupH = HEADER + CONDS.length * (BAR + GAP);
  const H = 22 + STRATEGIES.length * groupH;

  return (
    <div className="chart-wrap">
      <div className="legend" style={{ marginTop: 0 }}>
        {ORDER.map((s) => <span key={s}><i className="swatch" style={{ background: FILL[s] }} />{LABEL[s]}</span>)}
      </div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="Share of verified facts current, out of date, never true or missing after the fourth meeting, by strategy and recording">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line className="grid" x1={LEFT + t * PLOT} x2={LEFT + t * PLOT} y1={16} y2={H} />
            <text x={LEFT + t * PLOT} y={11} textAnchor="middle">{pct(t)}</text>
          </g>
        ))}
        {STRATEGIES.map((s, gi) => {
          const g0 = 22 + gi * groupH;
          return (
            <g key={s.id}>
              <text className="lbl" x={0} y={g0 + 16} style={{ fontWeight: 600, fill: "var(--ink)" }}>{s.label}</text>
              {CONDS.map((c, ci) => {
                const row = rows.find((r) => r.strategy === s.id && r.condition === c.id);
                if (!row) return null;
                const top = g0 + HEADER + ci * (BAR + GAP);
                let x = LEFT;
                return (
                  <g key={c.id}>
                    <text x={LEFT - 8} y={top + BAR - 4} textAnchor="end">{c.label}</text>
                    {ORDER.map((st) => {
                      const w = row[st] * PLOT;
                      const x0 = x;
                      x += w;
                      if (w <= 0) return null;
                      return (
                        <rect key={st} x={x0} y={top} width={Math.max(0, w - 2)} height={BAR}
                              rx={st === "correct" ? 3 : 0} fill={FILL[st]}
                              onMouseMove={(e) => {
                                const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                                setTip({ x: e.clientX - box.left, y: e.clientY - box.top + 28,
                                         text: `${s.label}, ${c.label.toLowerCase()}: ${LABEL[st].toLowerCase()} ${pct(row[st])}` });
                              }}
                              onMouseLeave={() => setTip(undefined)} />
                      );
                    })}
                    <text x={LEFT + row.correct * PLOT - 7} y={top + BAR - 4} textAnchor="end"
                          style={{ fill: "#fff", fontWeight: 600, fontSize: 12 }}>{pct(row.correct)}</text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      {tip && <div className="tip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div>}
    </div>
  );
}
