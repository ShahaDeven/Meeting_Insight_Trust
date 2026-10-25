import { memo, useEffect, useMemo, useRef } from "react";
import type { CondData, Lane, Turn } from "../types";
import { ROLE_LABEL, clock } from "../types";

interface Span { start: number; end: number; lane: Lane; id: string }

interface TurnProps {
  turn: Turn;
  now: boolean;
  spans: Span[];
  showErrors: boolean;
  onSeek: (t: number) => void;
}

const TurnRow = memo(function TurnRow({ turn, now, spans, showErrors, onSeek }: TurnProps) {
  return (
    <div className={`turn${now ? " now" : ""}`} data-start={turn.start}>
      <div className="who">
        {ROLE_LABEL[turn.speaker] ?? turn.speaker}
        <br />
        <button onClick={() => onSeek(turn.start)} aria-label={`Play from ${clock(turn.start)}`}>{clock(turn.start)}</button>
      </div>
      <p className="words" style={{ margin: 0 }}>
        {turn.words.map(([text, start, conf, err], i) => {
          const q = spans.find((s) => start >= s.start && start <= s.end);
          const cls = ["w", conf !== null && conf < 0.5 ? "low" : "", showErrors && err ? "err" : "",
                       q ? `q-${q.lane}` : ""].filter(Boolean).join(" ");
          return (
            <span key={i}>
              <span className={cls} onClick={() => onSeek(start)}
                    title={conf !== null ? `Recognizer confidence ${(conf * 100).toFixed(0)}%` : undefined}>
                {text}
              </span>{" "}
            </span>
          );
        })}
      </p>
    </div>
  );
});

interface Props {
  data: CondData;
  time: number;
  following: boolean;
  showErrors: boolean;
  setShowErrors: (v: boolean) => void;
  isAsr: boolean;
  active?: string;
  onSeek: (t: number) => void;
}

export default function Transcript({ data, time, following, showErrors, setShowErrors, isAsr, active, onSeek }: Props) {
  const box = useRef<HTMLDivElement>(null);
  // Per-turn quote spans, computed once so memoised rows skip re-rendering during playback.
  const spansByTurn = useMemo<Span[][]>(() => {
    const spans = data.insights.flatMap((i) =>
      i.quotes.map((q) => ({ start: q.start, end: q.end, lane: i.lane, id: i.id })));
    return data.turns.map((t) => spans.filter((s) => s.end >= t.start && s.start <= t.end));
  }, [data]);
  const nowIdx = useMemo(() => {
    let idx = -1;
    data.turns.forEach((t, i) => { if (t.start <= time) idx = i; });
    return idx;
  }, [data, time]);

  const scrollTo = (idx: number) => {
    const el = box.current?.children[idx] as HTMLElement | undefined;
    if (el && box.current) box.current.scrollTop = el.offsetTop - box.current.offsetTop - 80;
  };
  useEffect(() => { if (following && nowIdx >= 0) scrollTo(nowIdx); }, [nowIdx, following]);
  useEffect(() => {
    const ins = data.insights.find((i) => i.id === active);
    if (!ins) return;
    const t = ins.quotes[0].start;
    scrollTo(data.turns.findIndex((turn) => turn.end >= t));
  }, [active, data]);

  const low = data.turns.reduce((n, t) => n + t.words.filter((w) => w[2] !== null && w[2] < 0.5).length, 0);

  return (
    <section className="panel" aria-labelledby="tr-title">
      <div className="panel-head">
        <h2 id="tr-title">Transcript</h2>
        <span className="meta">
          {isAsr ? `Speech recognition from ${data.microphone}; ${low} words below 50% confidence` : "Human transcript (AMI), true speakers"}
        </span>
        {isAsr && (
          <label className="check">
            <input type="checkbox" checked={showErrors} onChange={(e) => setShowErrors(e.target.checked)} />
            Mark words that differ from the human transcript
          </label>
        )}
      </div>
      <div className="transcript" ref={box}>
        {data.turns.map((turn, i) => (
          <TurnRow key={i} turn={turn} now={i === nowIdx}
                   spans={spansByTurn[i]}
                   showErrors={showErrors} onSeek={onSeek} />
        ))}
      </div>
    </section>
  );
}
