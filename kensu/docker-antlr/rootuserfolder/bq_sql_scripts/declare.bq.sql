-- https://cloud.google.com/bigquery/docs/reference/standard-sql/scripting
DECLARE x INT64;
DECLARE d DATE DEFAULT CURRENT_DATE();
DECLARE x, y, z INT64 DEFAULT 0;
DECLARE item DEFAULT (SELECT item FROM dataset1.products LIMIT 1);
