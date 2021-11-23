-- Declare a variable to hold names as an array.
DECLARE top_names ARRAY<STRING>;

-- Build an array of the top 100 names from the year 2017.
SET top_names = (
  SELECT ARRAY_AGG(name ORDER BY number DESC LIMIT 100)
  FROM `bigquery-public-data`.usa_names.usa_1910_current
  WHERE year = 2017
);

-- Which names appear as words in Shakespeare's plays?
SELECT
  name AS shakespeare_name
FROM UNNEST(top_names) AS name
WHERE name IN (
  SELECT word
  FROM `bigquery-public-data`.samples.shakespeare
);