"""Part 2(a): ARPDAU is falling -- what broke?
Run after run_part1.py (needs game.duckdb with cleaned tables).

Answer in one line: nothing broke. A paid_video campaign that started the
week of 2026-02-23 bought mostly Tier-4 (and Tier-3) players. Tier-4 share of
active days jumps from 18% to 46%. ARPDAU *within every tier* rose 2-11%, but
the blended average is dragged down by the mix shift (Simpson's paradox).
"""
import pathlib, duckdb, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"; FIG = OUT / "figs"; FIG.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(ROOT / "game.duckdb"), read_only=True)

# Player-day level frame for the two periods.
# first30 = 2026-01-01..01-30, last30 = 2026-04-01..04-30 (30 days each).
PD = con.sql("""
WITH per AS (
  SELECT device_id, dt,
         CASE WHEN dt BETWEEN DATE '2026-01-01' AND DATE '2026-01-30' THEN 'first30'
              WHEN dt BETWEEN DATE '2026-04-01' AND DATE '2026-04-30' THEN 'last30' END AS per
  FROM active_day
), r AS (
  SELECT device_id, dt, sum(usd_amount) AS rev FROM purchase_clean WHERE NOT is_refund GROUP BY ALL
)
SELECT per.per, coalesce(r.rev, 0) AS rev, p.country_tier, p.acquisition_channel, p.platform
FROM per LEFT JOIN r USING (device_id, dt) JOIN player p USING (device_id)
WHERE per.per IS NOT NULL
""").df()


def by_tier():
    g = PD.groupby(["country_tier", "per"]).agg(days=("rev", "size"), rev=("rev", "sum")).reset_index()
    g["arpdau"] = g.rev / g.days
    g["mix"] = g.days / g.groupby("per").days.transform("sum")
    return g.pivot(index="country_tier", columns="per", values=["mix", "arpdau", "days", "rev"])


def decomposition(t):
    """Shift-share: change = within-tier (rate) effect + mix effect."""
    m0, m1 = t["mix"]["first30"], t["mix"]["last30"]
    a0, a1 = t["arpdau"]["first30"], t["arpdau"]["last30"]
    overall0, overall1 = (m0 * a0).sum(), (m1 * a1).sum()
    rate_effect = (m0 * (a1 - a0)).sum()          # tiers' own ARPDAU changes, at old mix
    mix_effect = ((m1 - m0) * a1).sum()           # moving weight toward low-ARPDAU tiers
    return dict(arpdau_first30=overall0, arpdau_last30=overall1,
                pct_change=overall1 / overall0 - 1,
                rate_effect=rate_effect, mix_effect=mix_effect,
                last30_at_first30_mix=(m0 * a1).sum(),
                pct_change_mix_held=(m0 * a1).sum() / overall0 - 1,
                revenue_first30=PD.loc[PD.per == "first30", "rev"].sum(),
                revenue_last30=PD.loc[PD.per == "last30", "rev"].sum())


def weekly_chart():
    w = con.sql("""
      WITH d AS (SELECT date_trunc('week', a.dt) wk, p.country_tier, count(*) AS n_days
                 FROM active_day a JOIN player p USING (device_id) GROUP BY 1, 2),
      r AS (SELECT date_trunc('week', pc.dt) wk, p.country_tier, sum(pc.usd_amount) AS rev
            FROM purchase_clean pc JOIN player p USING (device_id) WHERE NOT is_refund GROUP BY 1, 2)
      SELECT d.wk, d.country_tier, d.n_days AS days, coalesce(r.rev, 0) AS rev
      FROM d LEFT JOIN r USING (wk, country_tier) ORDER BY 1, 2""").df()
    w = w[(w.wk >= "2026-01-05") & (w.wk <= "2026-04-20")]   # full weeks only
    tot = w.groupby("wk")[["days", "rev"]].sum(); tot["arpdau"] = tot.rev / tot.days
    w["arpdau"] = w.rev / w.days
    w["share"] = w.days / w.groupby("wk").days.transform("sum")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.2))
    colors = {1: "#1b4f8a", 2: "#3f88c5", 3: "#f2a541", 4: "#d1495b"}
    for t, g in w.groupby("country_tier"):
        ax1.plot(g.wk, g.arpdau, color=colors[t], lw=2, label=f"Tier {t}")
    ax1.plot(tot.index, tot.arpdau, color="black", lw=3, ls="--", label="All players (blended)")
    ax1.set_title("ARPDAU by week: every tier flat/up, blend falls")
    ax1.set_ylabel("USD per daily active player"); ax1.legend(fontsize=8); ax1.grid(alpha=.3)
    piv = w.pivot(index="wk", columns="country_tier", values="share")
    ax2.stackplot(piv.index, *[piv[t] for t in piv.columns], colors=[colors[t] for t in piv.columns],
                  labels=[f"Tier {t}" for t in piv.columns])
    ax2.axvline(pd.Timestamp("2026-02-23"), color="k", ls=":"); ax2.text(pd.Timestamp("2026-02-25"), .93, "paid_video\nramp starts", fontsize=8)
    ax2.set_title("Share of active player-days by tier"); ax2.set_ylim(0, 1); ax2.legend(fontsize=8, loc="lower left")
    for ax in (ax1, ax2):
        ax.tick_params(axis="x", rotation=30)
    fig.tight_layout(); fig.savefig(FIG / "p2_arpdau_mix.png", dpi=180)
    return tot


def payback_by_tier_channel():
    """30-day revenue per install (installs with a full 30 days observed).
    This is the maximum CPI at which a 30-day payback is achieved."""
    return con.sql("""
      WITH i AS (SELECT * FROM player WHERE in_window_install AND install_date <= DATE '2026-03-31'),
      r AS (SELECT i.device_id, coalesce(sum(CASE WHEN NOT pc.is_refund AND pc.dt < i.install_date + 30
                                                THEN pc.usd_amount END), 0) rev30
            FROM i LEFT JOIN purchase_clean pc USING (device_id) GROUP BY 1)
      SELECT country_tier, acquisition_channel, count(*) installs, round(avg(rev30), 2) rev30_per_install
      FROM i JOIN r USING (device_id) GROUP BY 1, 2 ORDER BY 1, 2""").df()


if __name__ == "__main__":
    t = by_tier()
    print(t.round(4).to_string())
    d = decomposition(t)
    for k, v in d.items():
        print(f"{k:28s} {v:,.4f}")
    weekly_chart()
    pb = payback_by_tier_channel(); print(pb.to_string(index=False))
    t.round(4).to_csv(OUT / "p2_by_tier.csv"); pb.to_csv(OUT / "p2_rev30_per_install.csv", index=False)
    pd.Series(d).to_csv(OUT / "p2_decomposition.csv")
