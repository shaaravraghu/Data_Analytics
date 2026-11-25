"""Part 4: predict which currently-active players will lapse in the next 14 days.

DEFINITION (justified from data, see out/p4_gap_return.csv):
  Snapshot date T. "Currently active" = >= 1 active day in [T-6, T].
  Label churn14 = 1 if NO active day in [T+1, T+14].
  Why 14 days: the median gap between a player's active days is 3 days and
  the 90th percentile is 14 -- so a 14-day silence is unusual (top 10% of
  gaps) but still matches the horizon live-ops can act on. A 7-day rule
  would flag normal behaviour (25% of gaps exceed 8 days). Caveat that goes
  in the write-up: this is a LAPSE, not permanent churn -- 86% of players
  who go 14 days silent come back within 45 days.

SPLIT: out-of-time. Train on snapshots whose labels finish before the first
test snapshot (T <= 2026-03-22, labels end <= 04-05); test on T = 04-05 and
04-12 (labels end 04-26). A random split would leak: the same player
appears in adjacent weekly snapshots with nearly identical features.

MODEL: standardised logistic regression (interpretable coefficients).
"""
import pathlib, duckdb, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"; FIG = OUT / "figs"; FIG.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(ROOT / "game.duckdb"), read_only=True)

TRAIN_T = pd.date_range("2026-02-01", "2026-03-22", freq="7D")
TEST_T = pd.to_datetime(["2026-04-05", "2026-04-12"])

FEATURE_SQL = """
WITH pop AS (               -- currently active as of T
  SELECT DISTINCT device_id FROM active_day WHERE dt BETWEEN DATE '{T}' - 6 AND DATE '{T}'
),
hist AS (SELECT a.* FROM active_day a JOIN pop USING (device_id) WHERE a.dt <= DATE '{T}'),
f_act AS (
  SELECT device_id,
         DATE '{T}' - max(dt)                                            AS days_since_last,
         count(*) FILTER (WHERE dt > DATE '{T}' - 7)                     AS active_7,
         count(*) FILTER (WHERE dt > DATE '{T}' - 28)                    AS active_28,
         coalesce(sum(session_count) FILTER (WHERE dt > DATE '{T}' - 7), 0)    AS sessions_7,
         coalesce(sum(playtime_minutes) FILTER (WHERE dt > DATE '{T}' - 7), 0) AS playtime_7,
         max(player_level)                                                AS level,
         max(player_level) - coalesce(max(player_level) FILTER (WHERE dt <= DATE '{T}' - 14),
                                      min(player_level))                  AS level_gain_14
  FROM hist GROUP BY 1
),
f_pay AS (
  SELECT device_id, count(*) FILTER (WHERE dt > DATE '{T}' - 28) AS purchases_28,
         count(*) AS purchases_window
  FROM purchase_clean WHERE NOT is_refund AND dt <= DATE '{T}' GROUP BY 1
),
f_ad AS (   -- per available day, so the 03-05/06 outage does not read as zero
  SELECT device_id, count(*) FILTER (WHERE status = 'completed') /
         (7 - (SELECT count(*) FROM ad_outage_days o WHERE o.dt BETWEEN DATE '{T}' - 6 AND DATE '{T}'))::DOUBLE AS ads_per_day_7
  FROM ad_view_clean WHERE dt BETWEEN DATE '{T}' - 6 AND DATE '{T}' AND dt NOT IN (SELECT dt FROM ad_outage_days) GROUP BY 1
),
f_spend AS (
  SELECT device_id, count(*) AS spend_events_7 FROM raw_currency_spend
  WHERE event_ts::DATE BETWEEN DATE '{T}' - 6 AND DATE '{T}' GROUP BY 1
),
lab AS (
  SELECT DISTINCT device_id FROM active_day WHERE dt BETWEEN DATE '{T}' + 1 AND DATE '{T}' + 14
)
SELECT DATE '{T}' AS snapshot, p.device_id,
       least(DATE '{T}' - p.install_date, 365) AS tenure_days,
       p.country_tier, p.platform = 'iOS' AS ios, p.acquisition_channel,
       f.* EXCLUDE (device_id),
       coalesce(fp.purchases_28, 0) AS purchases_28, (coalesce(fp.purchases_window, 0) > 0) AS payer,
       coalesce(fa.ads_per_day_7, 0) AS ads_per_day_7, coalesce(fs.spend_events_7, 0) AS spend_events_7,
       (lab.device_id IS NULL)::INT AS churn14
FROM pop JOIN player p USING (device_id) JOIN f_act f USING (device_id)
LEFT JOIN f_pay fp USING (device_id) LEFT JOIN f_ad fa USING (device_id)
LEFT JOIN f_spend fs USING (device_id) LEFT JOIN lab USING (device_id)
"""

NUM = ["tenure_days", "days_since_last", "active_7", "active_28", "sessions_7", "playtime_7", "level",
       "level_gain_14", "purchases_28", "ads_per_day_7", "spend_events_7"]
CAT = ["ios", "payer", "tier_2", "tier_3", "tier_4", "ch_paid_social", "ch_paid_video"]


def build(dates):
    df = pd.concat([con.sql(FEATURE_SQL.format(T=d.date())).df() for d in dates], ignore_index=True)
    for t in (2, 3, 4):
        df[f"tier_{t}"] = (df.country_tier == t).astype(int)
    for ch in ("paid_social", "paid_video"):
        df[f"ch_{ch}"] = (df.acquisition_channel == ch).astype(int)
    df[["ios", "payer"]] = df[["ios", "payer"]].astype(int)
    df["log_playtime_7"] = np.log1p(df.playtime_7)
    # Players whose only recent "activity" is a purchase have no player_day row -> no level.
    df["level"] = df.level.fillna(df.level.median())
    df["level_gain_14"] = df.level_gain_14.fillna(0)
    return df


def gap_table():
    return con.sql("""
      WITH g AS (SELECT device_id, dt, lead(dt) OVER (PARTITION BY device_id ORDER BY dt) - dt AS gap FROM active_day)
      SELECT k AS silent_more_than_days, count(*) AS cases,
             round(avg(CASE WHEN gap IS NOT NULL AND gap <= 45 THEN 1 ELSE 0 END), 3) AS returned_within_45d
      FROM g, (SELECT unnest([3, 7, 14, 21, 28]) k) WHERE dt <= DATE '2026-03-16' AND (gap IS NULL OR gap > k)
      GROUP BY k ORDER BY k""").df()


def threshold_table(y, p, value_retained=(1, 3, 5), cost=0.25, uplift=0.10):
    """Expected profit of targeting everyone above each threshold.
    profit = uplift * V * (#true churners targeted) - cost * (#targeted).
    `uplift` = share of targeted would-be-churners the offer actually saves (unknown -> assumption)."""
    rows = []
    for thr in np.arange(0.1, 0.9, 0.05):
        sel = p >= thr; tp = (sel & (y == 1)).sum(); n = sel.sum()
        row = dict(threshold=round(thr, 2), targeted=int(n), share_targeted=round(n / len(y), 3),
                   precision=round(tp / n, 3) if n else np.nan, recall=round(tp / (y == 1).sum(), 3),
                   wasted_offers=int(n - tp))
        for V in value_retained:
            row[f"profit_V{V}"] = round(uplift * V * tp - cost * n, 1)
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    gap = gap_table(); print(gap.to_string(index=False)); gap.to_csv(OUT / "p4_gap_return.csv", index=False)
    tr, te = build(TRAIN_T), build(TEST_T)
    X = NUM[:5] + ["log_playtime_7"] + NUM[6:] + CAT
    print(f"train rows {len(tr):,} churn rate {tr.churn14.mean():.3f} | test rows {len(te):,} churn rate {te.churn14.mean():.3f}")

    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
    model.fit(tr[X], tr.churn14)
    p = model.predict_proba(te[X])[:, 1]; y = te.churn14.values

    # Baseline: a single rule live-ops could use without a model.
    base = -te.active_28.values
    metrics = dict(test_base_rate=y.mean(), roc_auc=roc_auc_score(y, p), pr_auc=average_precision_score(y, p),
                   brier=brier_score_loss(y, p), baseline_rule_auc_active28=roc_auc_score(y, base),
                   baseline_rule_auc_days_since_last=roc_auc_score(y, te.days_since_last))
    print({k: round(v, 4) for k, v in metrics.items()})
    coefs = pd.Series(model[-1].coef_[0], index=X).sort_values()
    print("standardised coefficients (log-odds per 1 SD):\n", coefs.round(3).to_string())

    te = te.assign(p=p)
    te["decile"] = pd.qcut(te.p.rank(method="first"), 10, labels=range(1, 11))
    dec = te.groupby("decile", observed=True).agg(n=("p", "size"), mean_pred=("p", "mean"), actual=("churn14", "mean")).round(3)
    print(dec.to_string())

    seg = []
    for name, mask in {"tenure<14d": te.tenure_days < 14, "tenure 14-60d": te.tenure_days.between(14, 60),
                       "tenure>60d": te.tenure_days > 60, "payers": te.payer == 1, "non-payers": te.payer == 0,
                       "tier1": te.country_tier == 1, "tier4": te.country_tier == 4,
                       "active 1 of last 7d": te.active_7 == 1, "active 3+ of last 7d": te.active_7 >= 3}.items():
        s = te[mask]
        seg.append(dict(segment=name, n=len(s), churn_rate=round(s.churn14.mean(), 3),
                        auc=round(roc_auc_score(s.churn14, s.p), 3) if s.churn14.nunique() > 1 else np.nan))
    seg = pd.DataFrame(seg); print(seg.to_string(index=False))

    thr = threshold_table(y, p); print(thr.to_string(index=False))

    pd.Series(metrics).to_csv(OUT / "p4_metrics.csv"); coefs.to_csv(OUT / "p4_coefficients.csv")
    dec.to_csv(OUT / "p4_deciles.csv"); seg.to_csv(OUT / "p4_segments.csv", index=False)
    thr.to_csv(OUT / "p4_thresholds.csv", index=False)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    a1.bar(dec.index.astype(int), dec.actual, color="#3f88c5", label="actual churn rate")
    a1.plot(dec.index.astype(int), dec.mean_pred, "ko-", label="predicted")
    a1.axhline(y.mean(), color="grey", ls="--", label=f"base rate {y.mean():.0%}")
    a1.set_xlabel("risk decile (10 = highest)"); a1.set_title("Out-of-time test: churn by risk decile"); a1.legend(fontsize=8)
    a2.plot(thr.share_targeted, thr.precision, "o-", color="#d1495b")
    for _, r in thr.iloc[::3].iterrows():
        a2.annotate(f"p≥{r.threshold:.2f}", (r.share_targeted, r.precision), fontsize=7, xytext=(4, 4), textcoords="offset points")
    a2.set_xlabel("share of active players targeted"); a2.set_ylabel("precision (offers reaching real lapsers)")
    a2.set_title("Targeting trade-off"); a2.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(FIG / "p4_churn.png", dpi=180)
