-- =====================================================================
-- 01_clean.sql  —  cleaning layer. Every analysis query reads views/tables, never raw_*. Each fix below is a data-quality issue documented in DATA_QUALITY.md.
-- =====================================================================

-- Window of the extract

CREATE OR REPLACE MACRO win_start() AS DATE '2026-01-01';
CREATE OR REPLACE MACRO win_end()   AS DATE '2026-04-30';

-- ---------------------------------------------------------------------
-- player: one row per device.
--  * original_device_id is NOT used to merge players: in half the links the "original" installed AFTER the device it is supposed to precede,  countries/channels differ, and both devices keep playing in parallel.The link is unreliable, so every device_id is treated as a player.
--  * 16,000 players installed before the window (left-truncated): we never see their early life, so they are excluded from anything that is measured "since install" (retention, time-to-first-purchase, channel quality, LTV).
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE player AS

SELECT device_id, original_device_id, install_date, platform, country,
       country_tier, acquisition_channel, first_purchase_date,
       install_date >= win_start()                    AS in_window_install,
       date_trunc('week', install_date)::DATE         AS install_week

FROM raw_player_profile;

-- ---------------------------------------------------------------------
-- purchase_clean
--  * 122 purchase_ids appear twice (same device/pack/amount, logged hours apart) -> resent events. Keep the earliest row per purchase_id.
--  * 228 negative rows are refunds of an earlier purchase (own id). Kept, flagged is_refund. "Gross revenue" = positive rows only; "net" subtracts refunds.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE purchase_clean AS

SELECT * EXCLUDE (rn), usd_amount < 0 AS is_refund, event_ts::DATE AS dt

FROM (
  SELECT *, row_number() OVER (PARTITION BY purchase_id ORDER BY event_ts) rn
  FROM raw_purchase
) WHERE rn = 1;

-- ---------------------------------------------------------------------
-- active_day: one row per (device, active date).
--  * activity_date is an int YYYYMMDD -> cast to DATE.
--  * ~17% of purchases happen on a date with no player_day row for that device (uniform over hour and month, so not a timezone artefact): player_day is missing rows. A player who bought something was active, so active days = player_day UNION purchase days. Without this the payer share has payers in the numerator who are missing from the denominator.
-- ---------------------------------------------------------------------

CREATE OR REPLACE TABLE active_day AS

WITH pd AS (
  SELECT device_id, strptime(activity_date::VARCHAR, '%Y%m%d')::DATE AS dt,
         player_level, session_count, playtime_minutes, app_version, TRUE AS in_player_day
  FROM raw_player_day
), pu AS (
  SELECT DISTINCT device_id, dt FROM purchase_clean WHERE NOT is_refund
)

SELECT coalesce(pd.device_id, pu.device_id) AS device_id,
       coalesce(pd.dt, pu.dt)               AS dt,
       pd.player_level, pd.session_count, pd.playtime_minutes, pd.app_version,
       coalesce(pd.in_player_day, FALSE)    AS in_player_day

FROM pd FULL OUTER JOIN pu ON pd.device_id = pu.device_id AND pd.dt = pu.dt;

-- ---------------------------------------------------------------------
-- ad_view_clean
--  * No true duplicates: 185 rows share (device, ts, status) but differ in placement/count -- late events are clamped to 23:59:56 local. Kept as separate events.
--  * ad_view timestamps run 14:00 -> 07:59 next day while every other table runs 06:00 -> 23:59, and 7,732 rows fall on 2026-05-01 (outside the window). The ad SDK clock is 8 h ahead; subtract 8h so ad days line up with player days.
--  * After the shift, 2026-03-05 and 2026-03-06 have zero ad rows while player_day is normal on those days -> ad logging outage. Those two days are excluded from ad-rate calculations, not treated as zero.
-- ---------------------------------------------------------------------


CREATE OR REPLACE TABLE ad_view_clean AS

SELECT DISTINCT device_id, event_ts - INTERVAL 8 HOUR AS event_ts,
       (event_ts - INTERVAL 8 HOUR)::DATE AS dt,
       status, placement, reward_type, reward_amount, ad_daily_count, ad_daily_cap
FROM raw_ad_view;

CREATE OR REPLACE TABLE ad_outage_days AS

SELECT d::DATE AS dt FROM range(DATE '2026-03-05', DATE '2026-03-07', INTERVAL 1 DAY) t(d);
