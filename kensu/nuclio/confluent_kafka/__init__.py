import logging

from confluent_kafka import Producer as ConfluentProducer
from kensu.nuclio.agent import kensu_add_kafka_output


class Producer(ConfluentProducer):
    def produce(self, topic, value=None, *args, **kwargs):
        result = super().produce(topic, value, *args, **kwargs)
        try:
            kensu_add_kafka_output(
                topic=topic,
                cluster_name=self._kensu_stored_bootstrap_servers or 'unknown',
                output_data=value)
        except Exception as err:
            logging.info(f"An issue occurred when reporting Confluent Kafka output to Kensu: {err}")
        return result

    def __init__(self, config):
        super().__init__(config)
        self._kensu_stored_bootstrap_servers = config.get('bootstrap.servers')
