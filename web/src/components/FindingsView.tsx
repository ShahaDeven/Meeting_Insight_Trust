import { useState } from "react";
import type { FindingsData } from "../types";
import { TYPE_LABEL, pct } from "../types";

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
  const D = f.risk.deploy;
  const H = D.asr_headline;
  const cc = f.risk.catch_curve;
  const L = f.ladder;
  const sign = (x: number, d = 3) => `${x >= 0 ? "+" : ""}${x.toFixed(d)}`;
  const pts = (x: number) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(0)}`;
  const crit = H.critical_at_20;
  const failures: Record<string, string> = {
    owner: "Wrong owner", number: "Wrong figure or deadline", type: "Suggestion recorded as a decision",
    content: "Not what was said, or later reversed", crm_critical: "CRM-critical (owner, figure, decision or cost)",
  };
  const condName: Record<string, string> = {
    headset: "Headset ASR", farfield: "Room-mic ASR", clean: "Human transcript", speaker_swap: "Speaker swap",
  };
  const rejected = Object.values(D.rejected);
  return (
    <div className="findings" style={{ marginTop: 18 }}>
      <section className="finding">
        <div>
          <h2>On real speech recognition, the risk score earns its place on the expensive errors</h2>
          <p>
            These results use only headset and room-microphone transcripts ({H.n} insights, {pct(H.wrong_rate)} judged
            wrong), the input a meeting bot actually gets. Ranked overall, the trained score is no better than the
            extractor’s own confidence (AUROC {H.auroc.toFixed(2)} vs {H.auroc_base.toFixed(2)}; difference{" "}
            {sign(H.gain_vs_base.auroc_gain)}, 95% CI {sign(H.gain_vs_base.auroc_gain_lo)} to{" "}
            {sign(H.gain_vs_base.auroc_gain_hi)}).
          </p>
          <p>
            Where it helps is the errors that cost most in a CRM. Reviewing the riskiest 20%, it catches{" "}
            {pct(crit.risk)} of wrong owners, wrong figures, wrong decisions and wrong cost figures, against{" "}
            {pct(crit.base)} for the extractor’s confidence ({pts(crit.gain)} points, 95% CI {pts(crit.gain_lo)} to{" "}
            {pts(crit.gain_hi)}). Recognizer confidence on the quoted words is the weakest signal of all
            (AUROC {H.auroc_quote_conf.toFixed(2)}).
          </p>
          <table className="plain" style={{ marginTop: 8 }}>
            <thead>
              <tr><th>Review the riskiest 20%, ranked by</th><th className="num">Wrong caught</th>
                <th className="num">Of reviewed, wrong</th><th className="num">Left in auto-writes</th></tr>
            </thead>
            <tbody>
              {([["Risk score", H.budget20], ["Extractor’s own confidence", H.budget20_base],
                 ["Recognizer confidence", H.budget20_quote_conf]] as const).map(([name, m]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td className="num">{pct(m.recall_wrong)}</td>
                  <td className="num">{pct(m.precision_review)}</td>
                  <td className="num">{pct(m.auto_error, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="fine" style={{ marginTop: 8 }}>
            Every score is for a meeting series the model never saw (leave-one-series-out); the model (logistic
            regression) was fixed in advance; intervals resample whole recording series; only signals a live product
            has at write time are used. Against {f.risk.human_n} human-audited insights the ranking holds (AUROC{" "}
            {f.risk.human_auroc.logistic.toFixed(2)} vs {f.risk.human_auroc.base_model_conf.toFixed(2)} vs{" "}
            {f.risk.human_auroc.base_quote_conf.toFixed(2)}). The human transcript and speaker-swap runs are
            experimental controls and are kept out of these numbers: they flatter the score (AUROC{" "}
            {D.by_condition.find((c) => c.condition === "clean")?.auroc.toFixed(2)} on clean transcripts).
          </p>
        </div>
        <CatchCurve curve={cc} policy={0.2} />
      </section>

      <section className="finding">
        <div>
          <h2>An explicit write policy: auto-write, review or reject</h2>
          <p>
            An insight is rejected if no quote in the transcript backs it; held for review if its risk times the cost of
            a wrong write of its type is at least one review; and written automatically otherwise. The costs are a stated
            assumption, priced in reviews: decision {D.costs.decision}, action item {D.costs.action_item}, cost figure{" "}
            {D.costs.cost_figure}, open risk {D.costs.open_risk}.
          </p>
          <p>
            On ASR output this reviews {pct(H.policy.review_rate)} of insights, catches {pct(H.policy.recall_wrong)} of the
            wrong ones and leaves {pct(H.policy.auto_error, 1)} wrong among automatic writes (from {pct(H.wrong_rate, 1)}).
            It is strongest on owners; open risks are never held, because their stated cost is low.
          </p>
          <p className="fine">
            The risk is the model’s out-of-fold probability. It is not post-hoc calibrated; on held-out ASR series it
            tracks the observed error rate but runs low at the bottom (predicted {pct(D.asr_reliability[0].predicted)},
            observed {pct(D.asr_reliability[0].observed)}). Rejected at extraction for lack of a quote:{" "}
            {rejected.reduce((a, r) => a + r.rejected, 0)} of {rejected.reduce((a, r) => a + r.of, 0)} insights. Quote
            matching does not yet check that a real quote supports the claim’s meaning.
          </p>
        </div>
        <div>
          <table className="plain">
            <thead><tr><th>Insight type (ASR)</th><th className="num">n</th><th className="num">Wrong</th>
              <th className="num">Reviewed</th><th className="num">Wrong caught</th><th className="num">Left in auto</th></tr></thead>
            <tbody>
              {D.asr_by_type.map((t) => (
                <tr key={t.type}>
                  <td>{TYPE_LABEL[t.type]}</td><td className="num">{t.n}</td><td className="num">{pct(t.wrong_rate)}</td>
                  <td className="num">{pct(t.policy_review_rate)}</td><td className="num">{pct(t.policy_recall)}</td>
                  <td className="num">{pct(t.policy_auto_error, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="plain" style={{ marginTop: 16 }}>
            <thead><tr><th>Kind of error (ASR)</th><th className="num">n</th><th className="num">Policy catches</th>
              <th className="num">Risk top 20%</th><th className="num">Extractor top 20%</th></tr></thead>
            <tbody>
              {D.asr_by_failure.map((r) => (
                <tr key={r.failure}>
                  <td>{failures[r.failure] ?? r.failure}</td><td className="num">{r.wrong_insights}</td>
                  <td className="num">{pct(r.caught_policy)}</td><td className="num">{pct(r["caught_logistic@20"])}</td>
                  <td className="num">{pct(r["caught_base_model_conf@20"])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="plain" style={{ marginTop: 16 }}>
            <thead><tr><th>Transcript</th><th>Role</th><th className="num">AUROC</th><th className="num">Extractor conf.</th></tr></thead>
            <tbody>
              {D.by_condition.map((c) => (
                <tr key={c.condition}>
                  <td>{condName[c.condition]}</td><td>{c.role === "deployment" ? "Deployment" : "Control"}</td>
                  <td className="num">{c.auroc.toFixed(2)}</td><td className="num">{c.auroc_base.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
            Exploratory. Wrong = judged by a strict LLM reviewer reading the human transcript; it flags more than
            a human does (see below), and under a human reading the microphone effect shrinks to roughly +2 points.
            Speaker mix-ups were injected as whole-turn relabels at each meeting’s measured far-field dose
            (within ±0.5 points): a dose-matched synthetic control, not a replica of real diarization errors.
            The shares split rates, not exclusive causes; mishearing and mix-ups can hit the same insight.
            Intervals resample whole recording series.
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
