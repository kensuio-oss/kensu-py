./nuctl-1.13.4-darwin-arm64 deploy hello -f hello.yaml \
  --volume "$KSU_CONF_FILE:/opt/nuclio/kensu.ini"
