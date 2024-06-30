# How to use

- `pip install kensu` 
- Add `@track_kensu()` decorator to handler function
- If using confluent Kafka producer:
  * change your code to import a Kensu wrapper of `confluent_kafka` producer
    ```diff
    - from confluent_kafka import Producer
    + from kensu.nuclio.confluent_kafka import Producer
    ```
  * add `producer.kensu_set_nuclio_context(context)`

### Kensu configuration

Kensu agent configured in regular way, just make sure `KSU_CONF_FILE` environment variable is passed to nuclio function, 
and it points to a accessible Kensu config file (mounted volume).

#### configuring reporting interval

Lineage and data observability metrics about multiple nuclio events are aggregated and sent to Kensu only once per specified time period.

Set environment variable `KSU_NUCLIO_REPORTING_INTERVAL_SECONDS=123`.

# Limitations / Pecularities

- handling of NULLs
  * `.nullrows` metrics could `None/NULL` only when field is present in JSON, e.g. `{ "my_field": null }`
  * `NoneType` never reported as schema fields, we report these schema fields only when they are not None/NULL


# Run example nuclio function locally with kafka

### start Kafka in docker

```bash
docker-compose -f kafka-docker-compose.yml up -d
```
this will start Kafka in standalone mode (without Zookeeper), and Kafka UI at http://localhost:8080/


### run nuclio on M2 Mac

download `nuctl-1.13.4-darwin-arm64` from https://github.com/nuclio/nuclio/releases

create/modify kensu-conf.ini and run the following:
```bash
KSU_CONF_FILE=$(PWD)/kensu-conf.ini ./nuclio_deploy_sample_function.sh
```

this will build and start docker container with the sample nuclio job, 
passing through the Kensu config file to a sample nuclio function

P.S. only Python 3.8 seemed to work out of the box

### send some events to kafka

run `./produce_kafka_events.sh`.

this will exec the `_produce_kafka_events.sh` inside Kafka docker which will send some
sample events to the input topics to be consumed by nuclio functions
