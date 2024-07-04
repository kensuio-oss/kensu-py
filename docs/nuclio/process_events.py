import json
import random
from kensu.nuclio.agent import track_kensu


def kafka_delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
        print('Message delivery failed: {}'.format(err))
    else:
        print('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))


def normalize_kafka_cluster_name(kafka_name: str):
    """normalize kafka cluster name for:
     - inputs (only nuclio kafka name available)
     - outputs (only bootstrap.servers available)"""
    kafka_bootstrap_server = 'host.docker.internal:9094'
    kafka_cluster_name = 'kafka-local' # as in ingest_raw_events.yaml
    if kafka_bootstrap_server in kafka_name:
        return kafka_name.replace(kafka_bootstrap_server, kafka_cluster_name)
    return kafka_name


@track_kensu(
    process_name="process-ingested-events",
)
def handler_confluent(context, event):
    event_data = event.body

    if random.random() > 0.5:
        random_topic = "processed_events3"
    else:
        random_topic = "processed_events4"

    # https://github.com/confluentinc/confluent-kafka-python
    import socket
    conf = {'bootstrap.servers': 'host.docker.internal:9094',
            'client.id': socket.gethostname()}

    # only the import needs to be changed and pass kensu_set_nuclio_context at least for now
    # use this instead of: from confluent_kafka import Producer
    from kensu.nuclio.confluent_kafka import Producer
    producer = Producer(conf)

    output_data = [
        {
            'string1': 'string' if (random.random() < 0.8) else None,
            'float1': 123.5+random.random()*20,
            'int1': round(55+random.random()*10)
        },
    ]
    output_data = [json.dumps(j) for j in output_data]
    for data in output_data:
        # Trigger any available delivery report callbacks from previous produce() calls
        producer.poll(0)

        # Asynchronously produce a message. The delivery report callback will
        # be triggered from the call to poll() above, or flush() below, when the
        # message has been successfully delivered or failed permanently.
        producer.produce(random_topic, data.encode('utf-8'), callback=kafka_delivery_report)

    # Wait for any outstanding messages to be delivered and delivery report
    # callbacks to be triggered.
    producer.flush()

    return context.Response(
        body=f"Hello, from nuclio to topic {random_topic}",
        headers={},
        content_type="text/plain",
        status_code=200,
    )
