export type Cond = "clean" | "farfield";
export type Lane = "auto" | "review";
export type InsightType = "decision" | "action_item" | "cost_figure" | "open_risk";

/** [text, start, recognizer confidence (null for human words), 1 if it differs from the human transcript] */
export type WordTuple = [string, number, number | null, 0 | 1];

export interface Turn {
  speaker: string;
  start: number;
  end: number;
  words: WordTuple[];
}

export interface Quote {
  text: string;
  speaker: string;
  start: number;
  end: number;
  at: string;
}

export interface Driver {
  text: string;
  raises_risk: boolean;
  weight: number;
}

export interface Insight {
  id: string;
  type: InsightType;
  summary: string;
  owner: string | null;
  value: string | null;
  deadline: string | null;
  risk: number;
  lane: Lane;
  threshold: number;
  extractor_confidence: number;
  quotes: Quote[];
  why: Driver[];
  reviewer: { verdict: "correct" | "wrong" | "unsure"; failure: string; reason: string };
  meeting: MeetingPart;
  destinations: Destination[];
  due: Due;
  field: string | null;
}

export type Destination = "notes" | "tasks" | "calendar";
export type Due = { kind: "none" } | { kind: "after" } | { kind: "meeting"; part: MeetingPart }
  | { kind: "text"; text: string };

export interface CondData {
  audio: string;
  microphone: string;
  transcript: string;
  turns: Turn[];
  confidence: (number | null)[];
  insights: Insight[];
  rejected: { type: InsightType; summary: string; reason: string; quotes: string[] }[];
}

export interface MeetingData {
  meeting: string;
  part: MeetingPart;
  series: string;
  stage: string;
  duration: number;
  conditions: Record<Cond, CondData>;
}

export interface FieldWrite {
  slot: string; old: string | null; new: string | null;
  quote: string | null; speaker?: string; start?: number; at: string | null;
}
export interface FieldHold { slot: string; old: string | null; new: string | null; verifier_said: string }
export interface Note {
  id: string; type: InsightType; summary: string; owner: string | null; value: string | null;
  deadline: string | null; lane: Lane; risk: number; threshold: number; field: string | null; quote: Quote;
}
export interface Task {
  id: string; meeting: MeetingPart; task: string; owner: string | null; deadline: string | null;
  due: Due; lane: Lane; risk: number; threshold: number; quote: Quote;
}
export interface SeriesData {
  series: string;
  date: string;
  meetings: { part: MeetingPart; id: string; stage: string; duration: number }[];
  policy: { costs: Record<InsightType, number>; thresholds: Record<InsightType, number> };
  conditions: Record<Cond, {
    fields: Record<MeetingPart, { slots: Slot[]; written: FieldWrite[]; held: FieldHold[] }>;
    notes: Record<MeetingPart, Note[]>;
    tasks: Task[];
  }>;
}

/** A reviewer's call on a held write. Simulated: it changes this page only. */
export type Decision = { action: "approved" | "rejected" } | { action: "edited"; value: string };

/** Where a link should take the reader. */
export interface Target {
  view: "review" | "destinations" | "log";
  part?: MeetingPart;
  dest?: "record" | "tasks" | "calendar";
  focus?: string;      // an insight id, or "field:<slot>"
  at?: number;         // play the meeting from this second
}

export type Status = "correct" | "stale" | "wrong" | "missing";
export type Strategy = "re_summarize" | "evidence_ledger" | "gated_resummarize";
export type MeetingPart = "a" | "b" | "c" | "d";

export interface Slot {
  slot: string;
  category: InsightType;
  value: string;
}

export interface QueueItem {
  slot: string;
  old: string | null;
  new: string | null;
  verifier_said: string;
}

export interface MemoryData {
  series: string;
  stages: Record<MeetingPart, string>;
  gold: { slot: string; category: InsightType; after: Record<MeetingPart, string | null> }[];
  strategies: Record<Strategy, Record<Cond, {
    records: Record<MeetingPart, Slot[]>;
    review: Partial<Record<MeetingPart, QueueItem[]>>;
    scored: Record<string, { status: Status; record_row: string | null; reason: string }>;
  }>>;
}

export interface Estimate {
  value: number;
  ci_low: number;
  ci_high: number;
}

export interface FindingsData {
  corpus: { meetings: number; series: number; verified_series: number; hours_per_mic: number;
            wer: Record<string, number>; insights: number };
  ladder: Record<string, Estimate>;
  risk: {
    catch_curve: Record<"logistic" | "base_model_conf" | "base_quote_conf", number[]>;
    deploy: DeployEval;
    human_auroc: Record<string, number>;
    human_n: number;
  };
  memory: { strategy: Strategy; condition: string; correct: number; stale: number; wrong: number; missing: number }[];
  audits: { name: string; rows: number; agreement: number; kappa?: number; ci?: number[]; note: string }[];
  cost: { llm_usd: number; gpu_usd: number; by_stage: Record<string, number> };
}

export interface Confusion {
  review_rate: number; recall_wrong: number; precision_review: number;
  false_positive_rate: number; auto_error: number;
}

export interface DeployEval {
  costs: Record<InsightType, number>;
  asr_headline: {
    n: number; wrong_rate: number; auroc: number; auroc_base: number; auroc_quote_conf: number;
    budget20: Confusion; budget20_base: Confusion; budget20_quote_conf: Confusion; policy: Confusion;
    gain_vs_base: { auroc_gain: number; auroc_gain_lo: number; auroc_gain_hi: number;
                    caught20_gain: number; caught20_gain_lo: number; caught20_gain_hi: number };
    critical_at_20: { risk: number; base: number; gain: number; gain_lo: number; gain_hi: number };
  };
  by_condition: { condition: string; role: string; n: number; wrong_rate: number; auroc: number;
                  auroc_base: number; recall_at_20: number; recall_at_20_base: number }[];
  asr_by_type: { type: InsightType; n: number; wrong_rate: number; policy_review_rate: number;
                 policy_recall: number; policy_auto_error: number }[];
  asr_by_failure: { failure: string; wrong_insights: number; caught_policy: number;
                    "caught_logistic@20": number; "caught_base_model_conf@20": number }[];
  rejected: Record<string, { rejected: number; of: number }>;
  asr_reliability: { predicted: number; observed: number; n: number }[];
}

export const TYPE_LABEL: Record<InsightType, string> = {
  decision: "Decision",
  action_item: "Action item",
  cost_figure: "Cost figure",
  open_risk: "Open risk",
};

export const ROLE_LABEL: Record<string, string> = {
  PM: "Project manager",
  ME: "Marketing",
  UI: "Interface design",
  ID: "Industrial design",
};

export const ROLES = ["PM", "ME", "UI", "ID"] as const;

export function clock(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function prettySlot(s: string): string {
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function dueText(d: Due, stages: Record<string, string>): string {
  if (d.kind === "meeting") return `Meeting ${d.part} (${stages[d.part]})`;
  if (d.kind === "after") return "After the series";
  if (d.kind === "text") return d.text;
  return "No deadline";
}
