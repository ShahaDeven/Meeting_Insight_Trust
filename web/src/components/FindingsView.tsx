import { useState } from "react";
import type { FindingsData } from "../types";
import { pct } from "../types";

const SERIES = [
  { key: "logistic", label: "Risk score", color: "var(--series-1)" },
  { key: "base_model_conf", label: "Extractor's own confidence", color: "var(--series-2)" },
  { key: "base_quote_conf", label: "Recognizer confidence on the quote", color: "var(--series-3)" },
] as const;

function CatchCurve({ curve, policy }: { curve: FindingsData["risk"]["catch_curve"]; policy: number }) {
  const [hover, setHover] = useState<number>();
  const W = 560, H = 330, L = 44, R = 16, T = 12, B = 40;
  const pw = W - L - R, ph = H - T - B;
  const n = curve.logistic.length; // budgets 0..100 step 2
  const x = (i: number) => L + (i / (n - 1)) * pw;
  const y = (v: number) => T + (1 - v) * ph;
  const path = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const pi = Math.round(policy * (n - 1));
  // Direct labels sit beside each curve's point at the policy line (where the curves are
  // furthest apart), nudged to keep at least 14px between them.
  const marks = SERIES.map((s) => ({ ...s, v: curve[s.key][pi], ly: y(curve[s.key][pi]) }))
    .sort((a, b) => a.ly - b.ly);
  marks.forEach((m, k) => { if (k && m.ly - marks[k - 1].ly < 14) m.ly = marks[k - 1].ly + 14; });

  return (
    <div className="chart-wrap">
      <div className="legend" style={{ marginTop: 0 }}>
        {SERIES.map((s) => <span key={s.key}><i className="swatch" style={{ background: s.color, height: 3 }} />{s.label}</span>)}
        <span><i className="swatch" style={{ borderTop: "2px dashed var(--ink-3)", height: 0, borderRadius: 0 }} />Random order</span>
      </div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label="Share of wrong insights caught as more insights are sent to review, riskiest first, for three ways of ranking them"
           onMouseMove={(e) => {
             const box = e.currentTarget.getBoundingClientRect();
             const px = ((e.clientX - box.left) / box.width) * W;
             const i = Math.round(((px - L) / pw) * (n - 1));
             setHover(i >= 0 && i < n ? i : undefined);
           }}
           onMouseLeave={() => setHover(undefined)}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line className="grid" x1={L} x2={L + pw} y1={y(t)} y2={y(t)} />
            <text x={L - 8} y={y(t) + 4} textAnchor="end">{pct(t)}</text>
            <text x={L + t * pw} y={H - B + 18} textAnchor="middle">{pct(t)}</text>
          </g>
        ))}
        <text x={L + pw / 2} y={H - 4} textAnchor="middle">Insights sent to review, riskiest first</text>
        <line x1={x(0)} y1={y(0)} x2={x(n - 1)} y2={y(1)} stroke="var(--ink-3)" strokeDasharray="4 4" strokeWidth={1.5} />
        <line x1={x(pi)} x2={x(pi)} y1={T} y2={T + ph} stroke="var(--ink)" strokeDasharray="2 3" />
        <text className="lbl" x={x(pi) + 4} y={T + 10}>Policy: review {pct(policy)}</text>
        {SERIES.map((s) => (
          <path key={s.key} d={path(curve[s.key])} fill="none" stroke={s.color} strokeWidth={2} />
        ))}
        {marks.map((m) => (
          <g key={m.key}>
            <circle cx={x(pi)} cy={y(m.v)} r={4.5} fill={m.color} stroke="var(--panel)" strokeWidth={2}>
              <title>{`${m.label}: ${pct(m.v)} of wrong insights caught at ${pct(policy)} review`}</title>
            </circle>
            <text className="lbl" x={x(pi) + 10} y={m.ly + 4}>{pct(m.v)} {m.label.toLowerCase()}</text>
          </g>
        ))}
        {hover !== undefined && (
          <line x1={x(hover)} x2={x(hover)} y1={T} y2={T + ph} stroke="var(--ink-2)" strokeWidth={1} />
        )}
      </svg>
      {hover !== undefined && (
        <div className="tip" style={{ left: `${(x(hover) / W) * 100}%`, top: 40 }}>
          Review {pct(hover / (n - 1))}: {SERIES.map((s) => `${s.label.split(" ")[0]} ${pct(curve[s.key][hover])}`).join(", ")}
        </div>
      )}
    </div>
  );
}

function Ladder({ ladder }: { ladder: FindingsData["ladder"] }) {
  const rows = [
    { key: "clean", label: "Human transcript" },
    { key: "speaker_swap", label: "Speakers mixed up" },
    { key: "headset", label: "Headset mics" },
    { key: "farfield", label: "Room mic" },
  ];
  const W = 560, H = 230, L = 132, R = 40, T = 10, ROW = 44;
  const max = 0.25;
  const x = (v: number) => L + (v / max) * (W - L - R);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
         aria-label="Share of insights a strict reviewer judged wrong, for each transcript, with 95% confidence intervals">
      {[0, 0.05, 0.1, 0.15, 0.2, 0.25].map((t) => (
        <g key={t}>
          <line className="grid" x1={x(t)} x2={x(t)} y1={T} y2={T + rows.length * ROW} />
          <text x={x(t)} y={T + rows.length * ROW + 16} textAnchor="middle">{pct(t)}</text>
        </g>
      ))}
      {rows.map((r, i) => {
        const e = ladder[r.key];
        const cy = T + i * ROW + ROW / 2;
        return (
          <g key={r.key}>
            <title>{`${r.label}: ${pct(e.value, 1)} judged wrong (95% CI ${pct(e.ci_low, 1)} to ${pct(e.ci_high, 1)})`}</title>
            <text className="lbl" x={L - 10} y={cy + 4} textAnchor="end">{r.label}</text>
            <rect x={L} y={cy - 8} width={Math.max(0, x(e.value) - L)} height={16} rx={3} fill="var(--series-1)" />
            <line x1={x(e.ci_low)} x2={x(e.ci_high)} y1={cy} y2={cy} stroke="var(--ink)" strokeWidth={1.5} />
            <line x1={x(e.ci_low)} x2={x(e.ci_low)} y1={cy - 5} y2={cy + 5} stroke="var(--ink)" strokeWidth={1.5} />
            <line x1={x(e.ci_high)} x2={x(e.ci_high)} y1={cy - 5} y2={cy + 5} stroke="var(--ink)" strokeWidth={1.5} />
            <text className="lbl" x={x(e.ci_high) + 6} y={cy + 4}>{pct(e.value, 1)}</text>
          </g>
        );
      })}
      <text x={L + (W - L - R) / 2} y={H - 2} textAnchor="middle">Insights judged wrong by a strict reviewer</text>
    </svg>
  );
}

export default function FindingsView({ findings }: { findings: FindingsData }) {
  const f = findings;
  const tbl = Object.fromEntries(f.risk.table.map((r) => [r.score, r]));
  const cc = f.risk.catch_curve;
  const at = (k: keyof typeof cc) => cc[k][10];
  const L = f.ladder;
  return (
    <div className="findings" style={{ marginTop: 18 }}>
      <section className="finding">
        <div>
          <h2>Recognizer confidence can’t tell you which insights are wrong</h2>
          <p>
            Send the riskiest 20% of insights to a person and the risk score catches {pct(at("logistic"))} of
            the wrong ones. Ranking by the extractor’s own confidence catches {pct(at("base_model_conf"))};
            ranking by speech-recognition confidence on the quoted words catches {pct(at("base_quote_conf"))},
            barely better than random.
          </p>
          <p>
            The strongest signals are what kind of claim it is (action items without a named owner are riskiest)
            and how sure the extractor was, not how clean the audio sounded. Auto-written insights go from{" "}
            {pct(f.risk.base_wrong_rate, 1)} wrong to {pct(tbl.logistic["auto_err@20"], 0)}.
          </p>
          <table className="plain" style={{ marginTop: 8 }}>
            <thead><tr><th>Ranking</th><th className="num">AUROC (95% CI)</th><th className="num">vs human labels</th></tr></thead>
            <tbody>
              {SERIES.map((s) => (
                <tr key={s.key}>
                  <td>{s.label}</td>
                  <td className="num">{tbl[s.key].auroc.toFixed(2)} ({tbl[s.key].auroc_lo.toFixed(2)}–{tbl[s.key].auroc_hi.toFixed(2)})</td>
                  <td className="num">{f.risk.human_auroc[s.key].toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="fine" style={{ marginTop: 8 }}>
            {f.corpus.insights.toLocaleString()} insights from {f.corpus.meetings} meetings; every score is
            for a meeting series the model never saw (leave-one-series-out). Only signals a live product has
            at write time are used.
          </p>
        </div>
        <CatchCurve curve={cc} policy={0.2} />
      </section>

      <section className="finding">
        <div>
          <h2>Most wrong insights are the model’s mistake, not the microphone’s</h2>
          <p>
            The same meetings were run four ways, changing one thing at a time. Insights from the human
            transcript are already {pct(L.clean.value, 1)} wrong; mixing up speakers adds almost nothing; the
            room microphone adds about {((L.farfield.value - L.speaker_swap.value) * 100).toFixed(0)} points. So roughly{" "}
            {pct(L.farfield_share_model.value)} of room-mic errors would happen with a perfect transcript.
          </p>
          <p>
            The commonest error everywhere is a suggestion recorded as a decision. Errors from bad audio are
            mostly non-local: the insight’s own quote is usually heard fine, but something said elsewhere
            (a later reversal, a “maybe”) was lost.
          </p>
          <p className="fine">
            Wrong = judged by a strict LLM reviewer reading the human transcript. That reviewer flags more than a
            human does (see below); under a human reading the microphone effect shrinks to roughly +2 points.
          </p>
        </div>
        <Ladder ladder={L} />
      </section>

      <section className="finding">
        <div>
          <h2>Careful reviewers disagree about what counts as a decision</h2>
          <p>
            The reviewer behind these labels was checked against blind human audits three times. Every audit
            is reported, including the weak ones. Agreement is fair, not strong: the hard calls are whether a
            suggestion was really agreed and whether a fact was later reversed. Those calls are policy, and
            that policy is what should stay with people.
          </p>
          <p className="fine">
            One human rater. Before the final audit the rater was shown four rows where his marks contradicted
            the written rules, which may have nudged him toward the reviewer. The reviewer’s labels were
            hash-frozen before that audit.
          </p>
        </div>
        <table className="plain">
          <thead><tr><th>Audit</th><th className="num">Rows</th><th className="num">Agreement</th><th className="num">Kappa</th></tr></thead>
          <tbody>
            {f.audits.map((a) => (
              <tr key={a.name}>
                <td>{a.name}<br /><span style={{ color: "var(--ink-3)" }}>{a.note}</span></td>
                <td className="num">{a.rows}</td>
                <td className="num">{pct(a.agreement)}{a.ci ? ` (${pct(a.ci[0])}–${pct(a.ci[1])})` : ""}</td>
                <td className="num">{a.kappa?.toFixed(2) ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="finding">
        <div>
          <h2>What went in, and what it cost</h2>
          <p>
            {f.corpus.meetings} real meetings ({f.corpus.series} four-meeting series, {f.corpus.hours_per_mic} hours)
            from the AMI corpus, recorded on headsets and on one room microphone. Word error rate against the
            human transcript: headsets {pct(f.corpus.wer.headset)}, room mic {pct(f.corpus.wer.farfield)}.
            Speech recognition ran once on a rented GPU; everything else ran on a laptop.
          </p>
          <p className="fine">
            Not tested against any vendor’s product. AMI meetings are product-design sessions, not sales calls,
            and Whisper may have seen AMI in training, so its error rates here are, if anything, optimistic.
          </p>
        </div>
        <table className="plain">
          <tbody>
            <tr><td>Speech recognition + speaker labels (GPU)</td><td className="num">${f.cost.gpu_usd.toFixed(2)}</td></tr>
            <tr><td>Insight extraction</td><td className="num">${(f.cost.by_stage.extract ?? 0).toFixed(2)}</td></tr>
            <tr><td>Reviewer labels and audits</td><td className="num">${(f.cost.by_stage.judge ?? 0).toFixed(2)}</td></tr>
            <tr><td>Answer key drafting</td><td className="num">${(f.cost.by_stage.state ?? 0).toFixed(2)}</td></tr>
            <tr><td>Memory experiment and scoring</td><td className="num">${((f.cost.by_stage.memory ?? 0) + (f.cost.by_stage.memscore ?? 0)).toFixed(2)}</td></tr>
            <tr><th>Total</th><th className="num">${(f.cost.llm_usd + f.cost.gpu_usd).toFixed(2)}</th></tr>
          </tbody>
        </table>
      </section>
    </div>
  );
}
