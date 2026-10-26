import { useCallback, useEffect, useRef, useState } from "react";
import type { Cond, FindingsData, MeetingData, MemoryData } from "./types";
import { clock } from "./types";
import Ribbon from "./components/Ribbon";
import Transcript from "./components/Transcript";
import Lanes from "./components/Lanes";
import MemoryView from "./components/MemoryView";
import FindingsView from "./components/FindingsView";

type View = "review" | "memory" | "findings";

const VIEWS: { id: View; label: string }[] = [
  { id: "review", label: "Meeting review" },
  { id: "memory", label: "Project memory" },
  { id: "findings", label: "What we measured" },
];

async function load<T>(name: string): Promise<T> {
  const r = await fetch(`./data/${name}.json`);
  if (!r.ok) throw new Error(`Could not load ${name}.json (${r.status}).`);
  return r.json() as Promise<T>;
}

export default function App() {
  const [meeting, setMeeting] = useState<MeetingData>();
  const [memory, setMemory] = useState<MemoryData>();
  const [findings, setFindings] = useState<FindingsData>();
  const [error, setError] = useState<string>();
  // The view lives in the URL hash, so a link can open straight onto it (#memory, #findings).
  const [view, setViewState] = useState<View>(() => {
    const h = window.location.hash.slice(1);
    return VIEWS.some((v) => v.id === h) ? (h as View) : "review";
  });
  const setView = (v: View) => {
    setViewState(v);
    window.history.replaceState(null, "", v === "review" ? window.location.pathname : `#${v}`);
  };
  const [cond, setCond] = useState<Cond>("farfield");
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [active, setActive] = useState<string>();
  const [showErrors, setShowErrors] = useState(false);
  const audio = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    Promise.all([load<MeetingData>("meeting"), load<MemoryData>("memory"), load<FindingsData>("findings")])
      .then(([a, b, c]) => { setMeeting(a); setMemory(b); setFindings(c); })
      .catch((e: Error) => setError(e.message));
  }, []);

  const seek = useCallback((t: number, play = true) => {
    const el = audio.current;
    if (!el) return;
    el.currentTime = Math.max(0, t);
    setTime(el.currentTime);
    if (play) void el.play();
  }, []);

  const switchCond = (c: Cond) => {
    const el = audio.current;
    const at = el?.currentTime ?? 0;
    const wasPlaying = el ? !el.paused : false;
    setCond(c);
    setActive(undefined);
    // Keep the listener at the same moment of the meeting when the recording changes.
    requestAnimationFrame(() => {
      const next = audio.current;
      if (!next) return;
      next.currentTime = at;
      if (wasPlaying) void next.play();
    });
  };

  if (error) {
    return <main><p role="alert">The console data failed to load: {error} Run <code>python -m app.export</code> and rebuild.</p></main>;
  }
  if (!meeting || !memory || !findings) return <main><p>Loading the meeting…</p></main>;

  const data = meeting.conditions[cond];
  const nowTurn = [...data.turns].reverse().find((t) => t.start <= time);

  return (
    <>
      <header className="top">
        <div>
          <h1>Which meeting insights are safe to write to the CRM?</h1>
          <p>
            A real product-design meeting, transcribed from a room microphone. Every extracted
            insight gets a risk score. When a wrong write would cost more than a person checking it,
            the insight waits for review; insights with no supporting quote are rejected; the rest are
            written automatically.
          </p>
        </div>
        {view === "review" && (
          <div>
            <span className="control-label" id="rec-label">Recording</span>
            <div className="segmented" role="group" aria-labelledby="rec-label">
              <button aria-pressed={cond === "farfield"} onClick={() => switchCond("farfield")}>Room microphone</button>
              <button aria-pressed={cond === "clean"} onClick={() => switchCond("clean")}>Headsets + human transcript</button>
            </div>
          </div>
        )}
        <nav className="views" role="tablist" aria-label="Views">
          {VIEWS.map((v) => (
            <button key={v.id} role="tab" aria-selected={view === v.id} onClick={() => setView(v.id)}>
              {v.label}
            </button>
          ))}
        </nav>
      </header>

      <main>
        <audio
          ref={audio}
          src={data.audio}
          preload="metadata"
          onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
        />

        {view === "review" && (
          <>
            <Ribbon
              meeting={meeting}
              data={data}
              time={time}
              active={active}
              onSeek={(t) => seek(t)}
              onPin={(id, t) => { setActive(id); seek(t); }}
            />
            <div className="review-grid">
              <Transcript
                data={data}
                time={time}
                following={playing}
                showErrors={showErrors}
                setShowErrors={setShowErrors}
                isAsr={cond === "farfield"}
                active={active}
                onSeek={seek}
              />
              <Lanes
                insights={data.insights}
                rejected={data.rejected}
                costs={meeting.policy.costs}
                active={active}
                onPlay={(id, t) => { setActive(id); seek(t); }}
              />
            </div>
            <div className="player" aria-label="Audio player">
              <button
                aria-label={playing ? "Pause" : "Play"}
                onClick={() => (playing ? audio.current?.pause() : void audio.current?.play())}
              >
                {playing ? (
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="2" y="1" width="3" height="10" fill="currentColor" /><rect x="7" y="1" width="3" height="10" fill="currentColor" /></svg>
                ) : (
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1l8 5-8 5z" fill="currentColor" /></svg>
                )}
              </button>
              <span className="time">{clock(time)} / {clock(meeting.duration)}</span>
              <span className="now-line">
                {nowTurn ? `${nowTurn.speaker}: ${nowTurn.words.map((w) => w[0]).join(" ")}` : `${data.transcript} from ${data.microphone}`}
              </span>
            </div>
          </>
        )}
        {view === "memory" && <MemoryView memory={memory} findings={findings} />}
        {view === "findings" && <FindingsView findings={findings} />}
      </main>

      <footer>
        <p>
          Meeting audio, human transcripts and summaries: AMI Meeting Corpus (Carletta et al., 2005),
          CC BY 4.0. Speech recognition: Whisper large-v3; speaker labels: pyannote. Insights extracted
          with Claude Haiku. All results are precomputed; no meeting data leaves this page.
        </p>
        <p>Built by Deven Shah. The method, numbers and limits are under “What we measured”.</p>
      </footer>
    </>
  );
}
