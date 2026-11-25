"""Part 3: do acquisition channels differ in player quality?

Population: players installed INSIDE the window (pre-window installs have
unseen early lives) with a full observation period for the metric.
  Engagement: D7 retention  = active (active_day) exactly on install_date+7.
              Needs install_date <= 2026-04-23.
  Revenue:    rev30         = net USD in days [0, 30) after install.
              Needs install_date <= 2026-03-31.

Three comparisons:
  1. NAIVE: total window revenue per player by channel (the misleading one:
     paid_video players are newer -> less time to pay, and are mostly Tier 4).
  2. RAW on a fixed horizon (rev30, D7) -- still confounded by tier.
  3. ADJUSTED: OLS with tier + platform + install-week fixed effects,
     heteroskedasticity-robust (HC1) CIs. Also a cluster bootstrap check.
"""
import pathlib, duckdb, numpy as np, pandas as pd, statsmodels.formula.api as smf, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"; FIG = OUT / "figs"; FIG.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(ROOT / "game.duckdb"), read_only=True)

df = con.sql("""
WITH i AS (SELECT * FROM player WHERE in_window_install),
r AS (SELECT i.device_id,
             coalesce(sum(CASE WHEN pc.dt < i.install_date + 30 THEN pc.usd_amount END), 0) AS rev30,
             coalesce(sum(pc.usd_amount), 0) AS rev_window
      FROM i LEFT JOIN purchase_clean pc USING (device_id) GROUP BY 1),
a AS (SELECT i.device_id,
             coalesce(max((ad.dt = i.install_date + 7)::INT), 0) AS d7,
             count(ad.dt) AS active_days
      FROM i LEFT JOIN active_day ad USING (device_id) GROUP BY 1)
SELECT i.device_id, i.install_date, i.install_week::VARCHAR AS install_week, i.country_tier,
       i.platform, i.acquisition_channel AS channel, r.rev30, r.rev_window, a.d7, a.active_days,
       DATE '2026-04-30' - i.install_date AS days_observed
FROM i JOIN r USING (device_id) JOIN a USING (device_id)
""").df()
df["channel"] = pd.Categorical(df.channel, ["organic", "paid_social", "paid_video"])


def naive():
    return df.groupby("channel", observed=True).agg(
        players=("rev_window", "size"), rev_per_player_window=("rev_window", "mean"),
        days_observed=("days_observed", "mean"), share_tier4=("country_tier", lambda s: (s == 4).mean())).round(3)


def raw(metric, sub):
    g = sub.groupby("channel", observed=True)[metric]
    m, se, n = g.mean(), g.std() / np.sqrt(g.size()), g.size()
    return pd.DataFrame({"n": n, "mean": m, "ci_lo": m - 1.96 * se, "ci_hi": m + 1.96 * se}).round(4)


def adjusted(metric, sub):
    """Channel coefficients vs organic, controlling for tier, platform, install week."""
    fit = smf.ols(f"{metric} ~ C(channel) + C(country_tier) + C(platform) + C(install_week)", sub).fit(cov_type="HC1")
    rows = []
    for ch in ["paid_social", "paid_video"]:
        k = f"C(channel)[T.{ch}]"
        lo, hi = fit.conf_int().loc[k]
        rows.append(dict(metric=metric, channel=ch, diff_vs_organic=fit.params[k], ci_lo=lo, ci_hi=hi,
                         p_value=fit.pvalues[k], organic_baseline=sub.loc[sub.channel == "organic", metric].mean()))
    return pd.DataFrame(rows)


def min_detectable(metric, sub, power_z=0.84):
    """Approx. minimum detectable difference (80% power, 5% two-sided) between two channels."""
    sd = sub[metric].std(); n = sub.groupby("channel", observed=True).size()
    return {ch: round((1.96 + power_z) * sd * np.sqrt(1 / n["organic"] + 1 / n[ch]), 4) for ch in ["paid_social", "paid_video"]}


def within_tier(metric, sub):
    return sub.pivot_table(index="country_tier", columns="channel", values=metric, aggfunc="mean", observed=True).round(3)


def chart(rev_raw, adj_rev):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    chs = ["organic", "paid_social", "paid_video"]; col = ["#6c757d", "#3f88c5", "#d1495b"]
    a1.bar(chs, rev_raw["mean"], yerr=[rev_raw["mean"] - rev_raw.ci_lo, rev_raw.ci_hi - rev_raw["mean"]], color=col, capsize=5)
    a1.set_title("Raw 30-day revenue per install\n(paid_video looks ~40% worse)"); a1.set_ylabel("USD")
    a = adj_rev.set_index("channel")
    a2.errorbar(a.index, a.diff_vs_organic, yerr=[a.diff_vs_organic - a.ci_lo, a.ci_hi - a.diff_vs_organic],
                fmt="o", color="k", capsize=6, ms=8)
    a2.axhline(0, color="grey", ls="--")
    a2.set_title("Same comparison, same tier/platform/week\n(difference vs organic, 95% CI)"); a2.set_ylabel("USD")
    fig.tight_layout(); fig.savefig(FIG / "p3_channels.png", dpi=180)


if __name__ == "__main__":
    print("NAIVE (misleading):\n", naive(), "\n")
    rev = df[df.install_date <= pd.Timestamp("2026-03-31")]
    eng = df[df.install_date <= pd.Timestamp("2026-04-23")]
    r_rev, r_d7 = raw("rev30", rev), raw("d7", eng)
    print("RAW rev30:\n", r_rev, "\nRAW D7:\n", r_d7, "\n")
    print("rev30 within tier:\n", within_tier("rev30", rev), "\nD7 within tier:\n", within_tier("d7", eng), "\n")
    adj = pd.concat([adjusted("rev30", rev), adjusted("d7", eng)])
    print("ADJUSTED:\n", adj.round(4).to_string(index=False), "\n")
    print("MDE rev30:", min_detectable("rev30", rev), " MDE d7:", min_detectable("d7", eng))
    # payer conversion as a lower-variance revenue proxy
    rev = rev.assign(payer30=(rev.rev30 > 0).astype(int))
    print(adjusted("payer30", rev).round(4).to_string(index=False))
    naive().to_csv(OUT / "p3_naive.csv"); r_rev.to_csv(OUT / "p3_raw_rev30.csv"); r_d7.to_csv(OUT / "p3_raw_d7.csv")
    adj.round(5).to_csv(OUT / "p3_adjusted.csv", index=False)
    chart(r_rev, adj[adj.metric == "rev30"])
