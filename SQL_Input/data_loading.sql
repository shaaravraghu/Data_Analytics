-- Load raw CSVs as-is (all_varchar-free autodetect), keep raw_* untouched
CREATE OR REPLACE TABLE raw_player_profile AS SELECT * FROM read_csv_auto('csv/player_profile.csv', header=true);
CREATE OR REPLACE TABLE raw_player_day     AS SELECT * FROM read_csv_auto('csv/player_day.csv', header=true);
CREATE OR REPLACE TABLE raw_purchase       AS SELECT * FROM read_csv_auto('csv/purchase.csv', header=true);
CREATE OR REPLACE TABLE raw_currency_spend AS SELECT * FROM read_csv_auto('csv/currency_spend.csv', header=true);
CREATE OR REPLACE TABLE raw_ad_view        AS SELECT * FROM read_csv_auto('csv/ad_view.csv', header=true);
