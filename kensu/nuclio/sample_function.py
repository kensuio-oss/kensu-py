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


@track_kensu()
def handler_confluent(context, event):
    event_data = event.body

    if random.random() > 0.5:
        random_topic = "output_topic1"
    else:
        random_topic = "output_topic2"

    # https://github.com/confluentinc/confluent-kafka-python
    import socket
    conf = {'bootstrap.servers': 'host.docker.internal:9094',
            'client.id': socket.gethostname()}

    # only the import needs to be changed and pass kensu_set_nuclio_context at least for now
    # use this instead of: from confluent_kafka import Producer
    from kensu.nuclio.confluent_kafka import Producer
    producer = Producer(conf)
    producer.kensu_set_nuclio_context(context)

    output_data = [
        {
            'string1': 'string',
            'float1': 666.5,
            'int1': 222
        },
        {
            'string1': None,
            'float2': 111.2,
            'int1': None
        }
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

# Examples of manual reporting of output info:
# there might be multiple targets in same handler invocation
# kensu_add_kafka_output(context,
#                        topic=random_topic,
#                        cluster_name='kafka',
#                        schema={"field1": "str", "field2": "int"},
#                        output_data={"o_int": 1, "o_str_null": None, "o_str": "abc"}
#                        )
# kensu_add_kafka_output(context,
#                        topic='c',
#                        cluster_name='kafka2')