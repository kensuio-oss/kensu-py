#!/bin/bash

KAFKA_BIN_DIR="/opt/bitnami/kafka/bin"
BROKER_LIST="localhost:9092"
TOPIC="raw_events"

JSON_MESSAGES=(
'{"a_str": "lala"}'
'{"a_int": 123}'
'{"a_float": null }'
'{"a_float": 111.123 }'
'{"a_int": 123}'
'{"a_float": null }'
'{"a_float": 166.123 }'
'{"a_str": "lala"}'
'{"a_int": 111}'
'{"a_float": null }'
'{"a_float": 144.123 }'
'{"a_float": 123.123 }'
'{"a_int": 132}'
'{"a_float": null }'
)

for message in "${JSON_MESSAGES[@]}"; do
    echo "$message" | "${KAFKA_BIN_DIR}/kafka-console-producer.sh" --broker-list "$BROKER_LIST" --topic "$TOPIC"
    echo "$message sent"
    sleep 10
done
