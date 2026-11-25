-- Ad Share by Cap Value

WITH pdays AS (
  SELECT device_id, dt, max(ad_daily_cap) AS cap, max(ad_daily_count) AS max_count,
         sum((status = 'completed')::INT) AS completed
  FROM ad_view_clean WHERE dt NOT IN (SELECT dt FROM ad_outage_days)
  GROUP BY ALL
)

SELECT cap, count(*) AS ad_player_days,
       round(avg((max_count >= cap)::INT), 3) AS share_hit_cap,
       round(avg(completed), 2)               AS avg_completed_views

FROM pdays GROUP BY cap

UNION ALL

SELECT NULL, count(*), round(avg((max_count >= cap)::INT), 3), round(avg(completed), 2) FROM pdays

ORDER BY cap NULLS LAST;





-- Daily Ad Views

WITH v AS (
  SELECT dt, count(*) AS ad_events, sum((status = 'completed')::INT) AS completed_views,
         count(DISTINCT device_id) AS ad_watchers
  FROM ad_view_clean GROUP BY dt
), d AS (SELECT dt, count(DISTINCT device_id) AS dau FROM active_day GROUP BY dt)

SELECT d.dt, d.dau, coalesce(v.ad_events, 0) AS ad_events,
       coalesce(v.completed_views, 0) AS completed_views,
       round(coalesce(v.completed_views, 0) / d.dau, 3) AS completed_per_dau,
       round(coalesce(v.ad_watchers, 0) / d.dau, 3) AS watcher_share

FROM d LEFT JOIN v USING (dt) ORDER BY d.dt;
