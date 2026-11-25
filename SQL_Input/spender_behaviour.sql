-- Revenue Concentration

WITH pr AS (
  SELECT device_id, sum(usd_amount) AS rev FROM purchase_clean GROUP BY 1 HAVING sum(usd_amount) > 0
), ranked AS (
  SELECT rev, row_number() OVER (ORDER BY rev DESC) AS rk, count(*) OVER () AS n,
         sum(rev) OVER () AS tot FROM pr
), everyone AS (
  SELECT coalesce(pr.rev, 0) AS rev FROM player p LEFT JOIN pr USING (device_id)
), ranked_all AS (
  SELECT rev, row_number() OVER (ORDER BY rev DESC) AS rk, count(*) OVER () AS n,
         sum(rev) OVER () AS tot FROM everyone
)

SELECT 'payers only' AS population, max(n) AS n_ranked,
       round(sum(CASE WHEN rk <= ceil(n*0.01) THEN rev END)/max(tot), 3) AS top1_share,
       round(sum(CASE WHEN rk <= ceil(n*0.10) THEN rev END)/max(tot), 3) AS top10_share,
       round(sum(CASE WHEN rk <= ceil(n*0.50) THEN rev END)/max(tot), 3) AS top50_share

FROM ranked

UNION ALL

SELECT 'all players', max(n),
       round(sum(CASE WHEN rk <= ceil(n*0.01) THEN rev END)/max(tot), 3),
       round(sum(CASE WHEN rk <= ceil(n*0.10) THEN rev END)/max(tot), 3),
       round(sum(CASE WHEN rk <= ceil(n*0.50) THEN rev END)/max(tot), 3)

FROM ranked_all;





-- Time to First Purchase

WITH base AS (
  SELECT device_id, install_date, first_purchase_date,
         first_purchase_date - install_date AS days_to_fp
  FROM player WHERE in_window_install AND install_date <= DATE '2026-03-31'
)

SELECT CASE WHEN days_to_fp IS NULL OR days_to_fp > 30 THEN '9 never within 30d'
            WHEN days_to_fp = 0  THEN '1 day 0'
            WHEN days_to_fp <= 1 THEN '2 day 1'
            WHEN days_to_fp <= 3 THEN '3 day 2-3'
            WHEN days_to_fp <= 7 THEN '4 day 4-7'
            WHEN days_to_fp <= 14 THEN '5 day 8-14'
            ELSE '6 day 15-30' END AS bucket,
       count(*) AS players,
       round(count(*) / sum(count(*)) OVER (), 4) AS share_of_installs

FROM base GROUP BY 1 ORDER BY 1;




-- Repeat Purchase Gap

WITH p AS (
  SELECT device_id, event_ts,
         lag(event_ts) OVER (PARTITION BY device_id ORDER BY event_ts) AS prev_ts
  FROM purchase_clean WHERE NOT is_refund
), g AS (SELECT date_diff('minute', prev_ts, event_ts) / 1440.0 AS gap_days FROM p WHERE prev_ts IS NOT NULL)

SELECT count(*) AS gaps,
       round(quantile_cont(gap_days, 0.10), 2) AS p10_days,
       round(quantile_cont(gap_days, 0.25), 2) AS p25_days,
       round(median(gap_days), 2)              AS median_days,
       round(quantile_cont(gap_days, 0.75), 2) AS p75_days,
       round(quantile_cont(gap_days, 0.90), 2) AS p90_days,
       round(avg((gap_days < 1)::INT), 3)      AS share_within_1day

FROM g;




