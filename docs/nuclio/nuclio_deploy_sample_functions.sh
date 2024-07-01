./nuctl-1.13.4-darwin-arm64 deploy ingest-raw-events -f ingest_raw_events.yaml \
  --volume "$KSU_CONF_FILE:/opt/nuclio/kensu.ini"

./nuctl-1.13.4-darwin-arm64 deploy process-events -f process_events.yaml \
  --volume "$KSU_CONF_FILE:/opt/nuclio/kensu.ini"
