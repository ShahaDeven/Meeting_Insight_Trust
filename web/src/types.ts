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
  extractor_confidence: number;
  quotes: Quote[];
  why: Driver[];
  reviewer: { verdict: "correct" | "wrong" | "unsure"; failure: string; reason: string };
}

export interface CondData {
  audio: string;
  microphone: string;
  transcript: string;
  turns: Turn[];
  confidence: (number | null)[];
  insights: Insight[];
}

export interface MeetingData {
  meeting: string;
  series: string;
  stage: string;
  duration: number;
  policy: { review_share: number; threshold: number };
  conditions: Record<Cond, CondData>;
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
    table: { score: string; auroc: number; auroc_lo: number; auroc_hi: number;
             "caught@20": number; "auto_err@20": number; "caught@30": number; "auto_err@30": number }[];
    human_auroc: Record<string, number>;
    base_wrong_rate: number;
  };
  memory: { strategy: Strategy; condition: string; correct: number; stale: number; wrong: number; missing: number }[];
  audits: { name: string; rows: number; agreement: number; kappa?: number; ci?: number[]; note: string }[];
  cost: { llm_usd: number; gpu_usd: number; by_stage: Record<string, number> };
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
