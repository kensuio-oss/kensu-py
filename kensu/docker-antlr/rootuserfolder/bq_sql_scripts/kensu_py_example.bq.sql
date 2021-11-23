SELECT DATE_KEY, "ARG" AS COUNTRY_KEY, s.STORE_KEY, CHAIN_TYPE_DESC,
      CARD_FLAG, sum(TOTAL) AS CA 
FROM `psyched-freedom-306508.cf.ARG-stores` AS s
INNER JOIN `psyched-freedom-306508.cf.ARG-tickets` AS t
ON s.STORE_KEY = t.STORE_KEY
WHERE DATE_KEY = "2021-05-23"
GROUP BY DATE_KEY, s.STORE_KEY, CHAIN_TYPE_DESC, CARD_FLAG