"""Train and evaluate the risk score that splits insights into auto-write vs review.

Leave-one-series-out CV (6 folds): every prediction is for a team the model never saw.
Two models (logistic regression; small XGBoost with sigmoid calibration) against single-signal
baselines: the extractor's own confidence, and recognizer confidence on the quote.

Main metric: share of wrong insights caught when the riskiest X% go to human review, and the
error rate left among auto-written insights. Labels are judge v2 verdicts (a strict reviewer,
66% agreement with a blind human; see CLAUDE.md). The score is also checked against the
human-labelled insights (adjudicated dev set + final audit).

  python -m risk.train
Out: data/results/risk_scores.csv, risk_eval.csv, risk_calibration.csv, report/risk_*.png
"""

import json
import random

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from core.config import REPORT, RESULTS
from evals.audit_final import KEY as FINAL_KEY, SHEET as FINAL_SHEET, FIRST_COL, derive
from evals.audit_sheet import DEV

BUDGETS = (0.10, 0.20, 0.30)


def feature_columns(df: pd.DataFrame) -> list[str]:
    skip = {"insight_id", "meeting", "series", "condition", "run", "wrong", "failure"}
    return [c for c in df.columns if c not in skip]


def models() -> dict:
    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5)),
        "xgboost": CalibratedClassifierCV(
            XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8,
                          colsample_bytree=0.8, eval_metric="logloss", verbosity=0),
            method="sigmoid", cv=3),
    }


def cross_val(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df[["insight_id", "meeting", "series", "condition", "wrong"]].copy()
    out["base_model_conf"] = -df.model_confidence     # higher score = riskier
    out["base_quote_conf"] = -df.quote_conf_min
    for name in models():
        out[name] = np.nan
    for s in sorted(df.series.unique()):
        train, test = df.series != s, df.series == s
        for name, m in models().items():
            m.fit(df.loc[train, cols], df.loc[train, "wrong"])
            out.loc[test, name] = m.predict_proba(df.loc[test, cols])[:, 1]
    return out


def caught(y: np.ndarray, score: np.ndarray, budget: float) -> tuple[float, float]:
    """(share of wrong caught in the riskiest `budget`, error rate among the rest)."""
    order = np.argsort(-score, kind="stable")
    k = int(round(budget * len(y)))
    review, auto = y[order[:k]], y[order[k:]]
    return review.sum() / max(y.sum(), 1), auto.mean() if len(auto) else 0.0


def evaluate(scores: pd.DataFrame, n_boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    rng = random.Random(seed)
    meetings = sorted(scores.meeting.unique())
    by_meeting = {m: g for m, g in scores.groupby("meeting")}
    rows = []
    for col in ["base_model_conf", "base_quote_conf", "logistic", "xgboost"]:
        for subset, d in [("all", scores), ("asr_only", scores[scores.condition.isin(["headset", "farfield"])])]:
            y, s = d.wrong.to_numpy(), d[col].to_numpy()
            row = {"score": col, "subset": subset, "n": len(d), "auroc": roc_auc_score(y, s)}
            for b in BUDGETS:
                row[f"caught@{int(b * 100)}"], row[f"auto_err@{int(b * 100)}"] = caught(y, s, b)
            if subset == "all":
                boots = []
                for _ in range(n_boot):
                    g = pd.concat([by_meeting[rng.choice(meetings)] for _ in meetings])
                    if g.wrong.nunique() == 2:
                        boots.append(roc_auc_score(g.wrong, g[col]))
                boots.sort()
                row["auroc_lo"], row["auroc_hi"] = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]
            rows.append(row)
    return pd.DataFrame(rows)


def calibration(scores: pd.DataFrame, col: str, bins: int = 8) -> pd.DataFrame:
    d = scores[[col, "wrong"]].copy()
    d["bin"] = pd.qcut(d[col], q=bins, duplicates="drop")
    return d.groupby("bin", observed=True).agg(predicted=(col, "mean"), observed=("wrong", "mean"),
                                               n=("wrong", "size")).reset_index(drop=True)


def human_check(scores: pd.DataFrame) -> pd.DataFrame:
    """AUROC of each score against the human labels (adjudicated dev set + final audit)."""
    human = {i: v["mark"] for i, v in json.loads(DEV.read_text(encoding="utf-8")).items()}
    from openpyxl import load_workbook
    key = json.loads(FINAL_KEY.read_text(encoding="utf-8"))
    ws = load_workbook(FINAL_SHEET, read_only=True)["Audit"]
    rows = {r[0]: r for r in ws.iter_rows(min_row=2, max_row=len(key) + 1,
                                          max_col=FIRST_COL + 4, values_only=True)}
    for k in key:
        human[k["insight_id"]] = derive(list(rows[k["row"]][FIRST_COL - 1:FIRST_COL + 3]))
    d = scores[scores.insight_id.isin(human)].copy()
    d["human_wrong"] = d.insight_id.map(lambda i: int(human[i] == "wrong"))
    d = d[d.insight_id.map(lambda i: human[i] in ("correct", "wrong"))]
    return pd.DataFrame([{"score": c, "n": len(d), "human_wrong": int(d.human_wrong.sum()),
                          "auroc_vs_human": roc_auc_score(d.human_wrong, d[c])}
                         for c in ["base_model_conf", "base_quote_conf", "logistic", "xgboost"]])


def plots(scores: pd.DataFrame, cal: pd.DataFrame, best: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    REPORT.mkdir(parents=True, exist_ok=True)
    y = scores.wrong.to_numpy()
    xs = np.linspace(0, 1, 101)
    fig, ax = plt.subplots(figsize=(6, 4))
    for col, label in [(best, f"risk model ({best})"), ("base_model_conf", "extractor confidence"),
                       ("base_quote_conf", "ASR confidence on quote")]:
        ax.plot(xs * 100, [caught(y, scores[col].to_numpy(), b)[0] * 100 for b in xs], label=label)
    ax.plot([0, 100], [0, 100], ":", color="grey", label="random")
    ax.set(xlabel="% of insights sent to human review (riskiest first)",
           ylabel="% of wrong insights caught", title="Review budget vs wrong writes caught")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORT / "risk_catch_curve.png", dpi=150)
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot([0, 1], [0, 1], ":", color="grey")
    ax.plot(cal.predicted, cal.observed, "o-")
    ax.set(xlabel="predicted risk", ylabel="observed wrong rate", title=f"Calibration ({best})")
    fig.tight_layout()
    fig.savefig(REPORT / "risk_calibration.png", dpi=150)


def main() -> None:
    df = pd.read_csv(RESULTS / "risk_features.csv")
    cols = feature_columns(df)
    scores = cross_val(df, cols)
    scores.to_csv(RESULTS / "risk_scores.csv", index=False)
    ev = evaluate(scores)
    ev.to_csv(RESULTS / "risk_eval.csv", index=False)
    best = max(["logistic", "xgboost"], key=lambda c: ev.query("score == @c and subset == 'all'").auroc.item())
    cal = calibration(scores, best)
    cal.to_csv(RESULTS / "risk_calibration.csv", index=False)
    hc = human_check(scores)
    hc.to_csv(RESULTS / "risk_human_check.csv", index=False)
    plots(scores, cal, best)

    pd.set_option("display.width", 200)
    fmt = {c: "{:.0%}".format for c in ev.columns if c.startswith(("caught", "auto_err"))}
    print(f"{len(df)} insights, {df.wrong.mean():.1%} wrong; {len(cols)} features; "
          f"leave-one-series-out CV.\n")
    print(ev.to_string(index=False, formatters=fmt | {"auroc": "{:.3f}".format,
                                                      "auroc_lo": "{:.3f}".format, "auroc_hi": "{:.3f}".format}))
    print(f"\nCalibration ({best}):\n{cal.round(3).to_string(index=False)}")
    print(f"\nAgainst human labels:\n{hc.round(3).to_string(index=False)}")
    lr = models()["logistic"].fit(df[cols], df.wrong)
    coef = pd.Series(lr[-1].coef_[0], index=cols).sort_values()
    print(f"\nLogistic coefficients (standardized; + = riskier):\n{coef.round(2).to_string()}")


if __name__ == "__main__":
    main()
