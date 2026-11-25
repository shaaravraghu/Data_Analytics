WITH coh AS (
  SELECT device_id, install_date, install_week FROM player WHERE in_window_install
), m AS (SELECT unnest([1, 7, 14, 30]) AS n),
cell AS (
  SELECT c.install_week, m.n,
         count(*)                                   AS cohort_size,
         max(c.install_date) + m.n <= win_end()     AS fully_observed,
         avg((a.device_id IS NOT NULL)::INT)        AS retention
  FROM coh c CROSS JOIN m
  LEFT JOIN active_day a ON a.device_id = c.device_id AND a.dt = c.install_date + m.n
  GROUP BY c.install_week, m.n
)

SELECT install_week,
       max(cohort_size) AS installs,
       round(max(CASE WHEN n = 1  AND fully_observed THEN retention END), 3) AS d1,
       round(max(CASE WHEN n = 7  AND fully_observed THEN retention END), 3) AS d7,
       round(max(CASE WHEN n = 14 AND fully_observed THEN retention END), 3) AS d14,
       round(max(CASE WHEN n = 30 AND fully_observed THEN retention END), 3) AS d30

FROM cell GROUP BY install_week ORDER BY install_week;
