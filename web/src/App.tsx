import { useCallback, useEffect, useRef, useState } from "react";
import type { Cond, Decision, FindingsData, MeetingData, MeetingPart, MemoryData, SeriesData, Target } from "./types";
import { clock } from "./types";
import Ribbon from "./components/Ribbon";
import Transcript from "./components/Transcript";
import Lanes from "./components/Lanes";
import Destinations from "./components/Destinations";
import WriteLog from "./components/WriteLog";
import MemoryView from "./components/MemoryView";
import FindingsView from "./components/FindingsView";

type View = "review" | "destinations" | "log" | "memory" | "findings";
type Dest = "record" | "tasks" | "calendar";

const VIEWS: { id: View; label: string }[] = [
  { id: "review", label: "Meeting review" },
  { id: "destinations", label: "Destinations" },
  { id: "log", label: "Write log" },
  { id: "memory", label: "Memory study" },
  { id: "findings", label: "What we measured" },
];
const SERIES_VIEWS: View[] = ["review", "destinations", "log"];

async function load<T>(name: string): Promise<T> {
  const r = await fetch(`./data/${name}.json`);
  if (!r.ok) throw new Error(`Could not load ${name}.json (${r.status}).`);
  return r.json() as Promise<T>;
}

export default function App() {
  const [series, setSeries] = useState<SeriesData>();
  const [memory, setMemory] = useState<MemoryData>();
  const [findings, setFindings] = useState<FindingsData>();
  const [meetings, setMeetings] = useState<Partial<Record<MeetingPart, MeetingData>>>({});
  const [error, setError] = useState<string>();
  // The view lives in the URL hash, so a link can open straight onto it (#destinations, #log ...).
  const [view, setViewState] = useState<View>(() => {
    const h = window.location.hash.slice(1).split("/")[0];
    return VIEWS.some((v) => v.id === h) ? (h as View) : "review";
  });
  const setView = (v: View) => {
    setViewState(v);
    window.history.replaceState(null, "", v === "review" ? window.location.pathname : `#${v}`);
  };
  const [part, setPart] = useState<MeetingPart>("c");
  const [cond, setCond] = useState<Cond>("farfield");
  const [dest, setDest] = useState<Dest>(() => {
    const sub = window.location.hash.slice(1).split("/")[1];
    return sub === "tasks" || sub === "calendar" ? sub : "record";
  });
  const [focus, setFocus] = useState<string>();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [active, setActive] = useState<string>();
  const [showErrors, setShowErrors] = useState(false);
  const [audioMissing, setAudioMissing] = useState(false);
  const pendingSeek = useRef<number | null>(null);
  const audio = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    Promise.all([load<SeriesData>("series"), load<MemoryData>("memory"), load<FindingsData>("findings")])
      .then(([s, m, f]) => {
        // The type assertion in load() checks nothing at runtime, so catch data from an older
        // export here instead of letting a view crash on a missing field.
        const stale = [
          !f?.risk?.deploy?.asr_headline && "findings.json has no risk.deploy",
          !s?.conditions?.farfield?.fields && "series.json is missing",
        ].filter(Boolean);
        if (stale.length) throw new Error(`The console data is from an older export (${stale.join("; ")}).`);
        setSeries(s); setMemory(m); setFindings(f);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!series || meetings[part]) return;
    const id = series.meetings.find((m) => m.part === part)!.id;
    load<MeetingData>(`meetings/${id}`)
      .then((m) => setMeetings((prev) => ({ ...prev, [part]: m })))
      .catch((e: Error) => setError(e.message));
  }, [series, part, meetings]);

  const seek = useCallback((t: number, play = true) => {
    const el = audio.current;
    setTime(Math.max(0, t));
    if (!el || el.error) return;  // no audio in this build: still move the transcript and timeline
    el.currentTime = Math.max(0, t);
    if (play) el.play().catch(() => setAudioMissing(true));
  }, []);

  const go = (t: Target) => {
    if (t.part && t.part !== part) {
      audio.current?.pause();
      setPart(t.part);
      setTime(0);
    }
    if (t.dest) setDest(t.dest);
    setFocus(t.focus);
    if (t.view === "review") {
      setActive(t.focus);
      if (t.at !== undefined) {
        // Play once the (possibly different) meeting's audio is ready.
        if (!t.part || t.part === part) seek(t.at);
        else pendingSeek.current = t.at;
      }
    }
    setView(t.view);
    window.scrollTo({ top: 0 });
  };

  const decide = (id: string, d: Decision | undefined) =>
    setDecisions((prev) => {
      const next = { ...prev };
      if (d) next[id] = d; else delete next[id];
      return next;
    });

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

  const switchPart = (p: MeetingPart) => {
    audio.current?.pause();
    setPart(p);
    setTime(0);
    setActive(undefined);
  };

  if (error) {
    return <main><p role="alert">The console data failed to load: {error} Run <code>python -m app.export</code> and rebuild.</p></main>;
  }
  if (!series || !memory || !findings) return <main><p>Loading the series…</p></main>;

  const meeting = meetings[part];
  const data = meeting?.conditions[cond];
  const nowTurn = data ? [...data.turns].reverse().find((t) => t.start <= time) : undefined;
  const stage = series.meetings.find((m) => m.part === part)!.stage;

  return (
    <>
      <header className="top">
        <div>
          <h1>Which meeting insights are safe to write to the CRM?</h1>
          <p>
            Four real product-design meetings by one team, transcribed from a room microphone. Every extracted
            insight gets a risk score. When a wrong write would cost more than a person checking it, the insight
            waits for review; insights with no supporting quote are rejected; the rest are written automatically.
          </p>
          <p className="scope">
            Offline evaluation on 24 public AMI meetings, not a production system. Results are exploratory;
            the method and limits are under “What we measured”.
          </p>
        </div>
        {SERIES_VIEWS.includes(view) && (
          <div className="header-controls">
            {view === "review" && (
              <div>
                <span className="control-label" id="mtg-label">Meeting ({series.series})</span>
                <div className="segmented" role="group" aria-labelledby="mtg-label">
                  {series.meetings.map((m) => (
                    <button key={m.part} aria-pressed={part === m.part} onClick={() => switchPart(m.part)}
                            title={`${m.stage}, ${Math.round(m.duration / 60)} min`}>
                      {m.part}: {m.stage}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div>
              <span className="control-label" id="rec-label">Recording</span>
              <div className="segmented" role="group" aria-labelledby="rec-label">
                <button aria-pressed={cond === "farfield"} onClick={() => switchCond("farfield")}>Room microphone</button>
                <button aria-pressed={cond === "clean"} onClick={() => switchCond("clean")}>Headsets + human transcript</button>
              </div>
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
        {data && (
          <audio
            ref={audio}
            src={data.audio}
            preload="metadata"
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onError={() => setAudioMissing(true)}
            onLoadedMetadata={() => {
              setAudioMissing(false);
              if (pendingSeek.current !== null) {
                const at = pendingSeek.current;
                pendingSeek.current = null;
                seek(at);
              }
            }}
          />
        )}

        {view === "review" && (!meeting || !data ? <p>Loading meeting {part}…</p> : (
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
                costs={series.policy.costs}
                active={active}
                onPlay={(id, t) => { setActive(id); seek(t); }}
                onGo={go}
              />
            </div>
            <div className="player" aria-label="Audio player">
              <button
                aria-label={playing ? "Pause" : "Play"}
                disabled={audioMissing}
                onClick={() => (playing ? audio.current?.pause() : void audio.current?.play().catch(() => setAudioMissing(true)))}
              >
                {playing ? (
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="2" y="1" width="3" height="10" fill="currentColor" /><rect x="7" y="1" width="3" height="10" fill="currentColor" /></svg>
                ) : (
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1l8 5-8 5z" fill="currentColor" /></svg>
                )}
              </button>
              <span className="time">Meeting {part}, {clock(time)} / {clock(meeting.duration)}</span>
              <span className="now-line">
                {audioMissing ? "Audio is not included in this build. Run python -m app.export (needs ffmpeg) to add it."
                  : nowTurn ? `${nowTurn.speaker}: ${nowTurn.words.map((w) => w[0]).join(" ")}` : `${stage}: ${data.transcript} from ${data.microphone}`}
              </span>
            </div>
          </>
        ))}
        {view === "destinations" && (
          <Destinations series={series} cond={cond} part={part} setPart={setPart} dest={dest} setDest={setDest}
                        focus={focus} decisions={decisions} decide={decide} onGo={go} />
        )}
        {view === "log" && <WriteLog series={series} cond={cond} decisions={decisions} onGo={go} />}
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
