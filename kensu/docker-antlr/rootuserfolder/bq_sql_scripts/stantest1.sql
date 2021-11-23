SELECT
  CAST(DATETIME(usage_start_time, "America/Los_Angeles") AS DATE) AS usage_date,
  sku.id AS sku_id,
  sku.description AS sku_description,
  usage.unit AS unit,
  IFNULL(system_labels.value, "N/A") AS machine_spec,
  SUM(usage.amount) AS usage_amount,
  SUM(cost) AS cost
FROM `PROJECT.DATASET.TABLE`
LEFT JOIN UNNEST(system_labels) AS system_labels
  ON system_labels.key = "compute.googleapis.com/machine_spec"
WHERE
  service.description = "Compute Engine"
GROUP BY 1,2,3,4,5
ORDER BY 1,2,3,4,5 DESC
