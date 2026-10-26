"""Deployment-relevant evaluation and the explicit write policy.

A meeting bot sees speech-recognition output, so the PRIMARY evaluation uses only the headset
and far-field ASR conditions. The human transcript (clean) and the synthetic speaker swap are
experimental controls and are reported separately, never pooled into the headline.

Write policy (reproducible, stated before looking at outcomes):
  reject      the extractor could not tie the insight to a quote in the transcript
              (extract.extractor drops these; counted here)
  review      expected cost of auto-writing exceeds one human review:
              risk x COST[type] >= 1, i.e. risk >= 1 / COST[type]
  auto-write  everything else
COST is the price of one wrong CRM write in units of one human review. Owners, deadlines and
figures are what a CRM write gets wrong expensively, so action items and cost figures cost most.
The risk is the logistic model's out-of-fold probability. It is NOT post-hoc calibrated; its
reliability on held-out series is checked below and the policy depends on it being roughly right.

  python -m risk.policy
Out: data/results/deploy_eval.json, data/results/write_policy.csv
"""

import json
from glob import glob

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from core.config import INSIGHTS, RESULTS
from risk.train import PRIMARY, caught, paired_gain

ASR = ["headset", "farfield"]
CONTROLS = ["clean", "speaker_swap"]
COST = {"decision": 5, "action_item": 6, "cost_figure": 8, "open_risk": 2}
BUDGET = 0.20
BASE = "base_model_conf"


def load() -> pd.DataFrame:
    s = pd.read_csv(RESULTS / "risk_scores.csv")
    f = pd.read_csv(RESULTS / "risk_features.csv")
    types = [c for c in f.columns if c.startswith("type_")]
    f["type"] = f[types].idxmax(axis=1).str.removeprefix("type_")
    d = s.merge(f[["insight_id", "type", "failure"]], on="insight_id")
    # CRM-critical errors: a wrong owner or figure, or a wrong decision / cost figure.
    d["critical"] = (d.wrong == 1) & (d.failure.isin(["owner", "number"])
                                      | d.type.isin(["decision", "cost_figure"]))
    return d


def confusion(y: np.ndarray, review: np.ndarray) -> dict:
    tp = int((review & (y == 1)).sum()); fp = int((review & (y == 0)).sum())
    fn = int((~review & (y == 1)).sum()); tn = int((~review & (y == 0)).sum())
    return {"review_rate": (tp + fp) / len(y), "recall_wrong": tp / max(tp + fn, 1),
            "precision_review": tp / max(tp + fp, 1), "false_positive_rate": fp / max(fp + tn, 1),
            "auto_error": fn / max(fn + tn, 1), "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def at_budget(d: pd.DataFrame, col: str, budget: float = BUDGET) -> dict:
    k = int(round(budget * len(d)))
    order = np.argsort(-d[col].to_numpy(), kind="stable")
    review = np.zeros(len(d), bool)
    review[order[:k]] = True
    return confusion(d.wrong.to_numpy(), review)


def policy_flags(d: pd.DataFrame) -> np.ndarray:
    return (d[PRIMARY] * d.type.map(COST) >= 1).to_numpy()


def by_group(d: pd.DataFrame, key: str) -> list[dict]:
    rows = []
    for g, sub in d.groupby(key):
        row = {key: g, "n": len(sub), "wrong_rate": sub.wrong.mean()}
        if sub.wrong.nunique() == 2:
            row |= {"auroc": roc_auc_score(sub.wrong, sub[PRIMARY]),
                    "auroc_base": roc_auc_score(sub.wrong, sub[BASE])}
        pol = confusion(sub.wrong.to_numpy(), policy_flags(sub))
        row |= {"policy_review_rate": pol["review_rate"], "policy_recall": pol["recall_wrong"],
                "policy_auto_error": pol["auto_error"]}
        rows.append(row)
    return rows


def failure_recall(d: pd.DataFrame) -> list[dict]:
    """Of the wrong insights of each failure kind, the share each rule sends to review."""
    flags = {"policy": policy_flags(d)}
    for col in (PRIMARY, BASE):
        k = int(round(BUDGET * len(d)))
        order = np.argsort(-d[col].to_numpy(), kind="stable")
        f = np.zeros(len(d), bool)
        f[order[:k]] = True
        flags[f"{col}@20"] = f
    rows = []
    groups = {k: (d.failure == k).to_numpy() & (d.wrong == 1).to_numpy()
              for k in ["content", "type", "owner", "number"]}
    groups["crm_critical"] = d.critical.to_numpy()
    for name, mask in groups.items():
        rows.append({"failure": name, "wrong_insights": int(mask.sum()),
                     **{f"caught_{k}": float(f[mask].mean()) if mask.sum() else None for k, f in flags.items()}})
    return rows


def critical_gain(d: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> dict:
    """Share of CRM-critical wrong insights caught at a 20% budget: risk minus extractor
    confidence, with a paired bootstrap over whole series."""
    import random

    def gain(sub: pd.DataFrame) -> tuple[float, float, float]:
        crit = sub.critical.to_numpy()
        if not crit.any():
            return np.nan, np.nan, np.nan
        out = []
        for col in (PRIMARY, BASE):
            k = int(round(BUDGET * len(sub)))
            order = np.argsort(-sub[col].to_numpy(), kind="stable")
            f = np.zeros(len(sub), bool)
            f[order[:k]] = True
            out.append(f[crit].mean())
        return out[0], out[1], out[0] - out[1]

    a, b, g = gain(d)
    series = sorted(d.series.unique())
    by = {s: x for s, x in d.groupby("series")}
    rng = random.Random(seed)
    boots = sorted(v for v in (gain(pd.concat([by[rng.choice(series)] for _ in series]))[2]
                               for _ in range(n_boot)) if not np.isnan(v))
    return {"risk": a, "base": b, "gain": g,
            "gain_lo": boots[int(0.025 * len(boots))], "gain_hi": boots[int(0.975 * len(boots))]}


def rejected_counts() -> dict:
    out = {}
    for c in ASR + CONTROLS:
        n_rej = sum(1 for p in glob(str(INSIGHTS / f"*.{c}.r*.rejected.jsonl")) for _ in open(p, encoding="utf-8"))
        n_kept = sum(1 for p in glob(str(INSIGHTS / f"*.{c}.r*.jsonl"))
                     if not p.endswith(".rejected.jsonl") for _ in open(p, encoding="utf-8"))
        out[c] = {"rejected": n_rej, "of": n_rej + n_kept}
    return out


def reliability(d: pd.DataFrame, bins: int = 6) -> list[dict]:
    t = d[[PRIMARY, "wrong"]].copy()
    t["bin"] = pd.qcut(t[PRIMARY], q=bins, duplicates="drop")
    g = t.groupby("bin", observed=True).agg(predicted=(PRIMARY, "mean"), observed=("wrong", "mean"),
                                            n=("wrong", "size"))
    return g.reset_index(drop=True).round(4).to_dict("records")


def main() -> None:
    d = load()
    asr = d[d.condition.isin(ASR)].reset_index(drop=True)

    headline = {
        "n": len(asr), "wrong_rate": asr.wrong.mean(),
        "auroc": roc_auc_score(asr.wrong, asr[PRIMARY]),
        "auroc_base": roc_auc_score(asr.wrong, asr[BASE]),
        "auroc_quote_conf": roc_auc_score(asr.wrong, asr.base_quote_conf),
        "budget20": at_budget(asr, PRIMARY), "budget20_base": at_budget(asr, BASE),
        "budget20_quote_conf": at_budget(asr, "base_quote_conf"),
        "policy": confusion(asr.wrong.to_numpy(), policy_flags(asr)),
        "gain_vs_base": paired_gain(asr),
        "critical_at_20": critical_gain(asr),
    }
    by_condition = []
    for c in ASR + CONTROLS:
        sub = d[d.condition == c]
        by_condition.append({"condition": c, "role": "deployment" if c in ASR else "control",
                             "n": len(sub), "wrong_rate": sub.wrong.mean(),
                             "auroc": roc_auc_score(sub.wrong, sub[PRIMARY]),
                             "auroc_base": roc_auc_score(sub.wrong, sub[BASE]),
                             "recall_at_20": at_budget(sub, PRIMARY)["recall_wrong"],
                             "recall_at_20_base": at_budget(sub, BASE)["recall_wrong"]})
    out = {"primary_model": PRIMARY, "costs": COST, "budget": BUDGET,
           "asr_headline": headline, "by_condition": by_condition,
           "asr_by_type": by_group(asr, "type"), "asr_by_failure": failure_recall(asr),
           "rejected": rejected_counts(), "asr_reliability": reliability(asr)}
    (RESULTS / "deploy_eval.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")

    decisions = d[["insight_id", "condition", "type", PRIMARY, "wrong", "failure"]].copy()
    decisions["threshold"] = 1 / decisions.type.map(COST)
    decisions["decision"] = np.where(policy_flags(d), "review", "auto-write")
    decisions["reason"] = np.where(
        decisions.decision == "review",
        "risk " + decisions[PRIMARY].round(2).astype(str) + " >= 1/" + decisions.type.map(COST).astype(str),
        "risk " + decisions[PRIMARY].round(2).astype(str) + " < 1/" + decisions.type.map(COST).astype(str))
    decisions.to_csv(RESULTS / "write_policy.csv", index=False)

    h = headline
    pf = lambda x: f"{x:.0%}"  # noqa: E731
    print(f"PRIMARY (headset + far-field ASR, n={h['n']}, {pf(h['wrong_rate'])} wrong)")
    print(f"  AUROC risk {h['auroc']:.3f} | extractor conf {h['auroc_base']:.3f} | ASR conf {h['auroc_quote_conf']:.3f}")
    g = h["gain_vs_base"]
    print(f"  paired gain vs extractor conf: AUROC {g['auroc_gain']:+.3f} [{g['auroc_gain_lo']:+.3f}, "
          f"{g['auroc_gain_hi']:+.3f}]; caught@20 {g['caught20_gain']:+.1%} [{g['caught20_gain_lo']:+.1%}, "
          f"{g['caught20_gain_hi']:+.1%}]")
    c = h["critical_at_20"]
    print(f"  CRM-critical caught @20%: risk {c['risk']:.0%} vs extractor conf {c['base']:.0%}, "
          f"gain {c['gain']:+.1%} [{c['gain_lo']:+.1%}, {c['gain_hi']:+.1%}]")
    for name, m in [("risk @20%", h["budget20"]), ("extractor conf @20%", h["budget20_base"]),
                    ("ASR conf @20%", h["budget20_quote_conf"]), ("cost policy", h["policy"])]:
        print(f"  {name:20s} review {pf(m['review_rate'])}  recall {pf(m['recall_wrong'])}  "
              f"precision {pf(m['precision_review'])}  FPR {pf(m['false_positive_rate'])}  "
              f"auto-error {m['auto_error']:.1%}")
    print("\nBy condition (controls are not deployment results):")
    print(pd.DataFrame(by_condition).round(3).to_string(index=False))
    print("\nASR by insight type (cost policy):")
    print(pd.DataFrame(out["asr_by_type"]).round(3).to_string(index=False))
    print("\nASR wrong insights caught, by failure kind:")
    print(pd.DataFrame(out["asr_by_failure"]).round(2).to_string(index=False))
    print(f"\nRejected (no quote found): {out['rejected']}")
    print(f"\nASR reliability (out-of-fold, not post-hoc calibrated):\n{pd.DataFrame(out['asr_reliability']).to_string(index=False)}")


if __name__ == "__main__":
    main()
