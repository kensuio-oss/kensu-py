from confluent_kafka import Producer as ConfluentProducer
from kensu.nuclio.agent import kensu_add_kafka_output

class Producer(ConfluentProducer):
    def produce(self, topic, value=None, *args, **kwargs):
        result = super().produce(topic, value, *args, **kwargs)
        try:
            if not self._kensu_nuclio_context:
                return result
            kensu_add_kafka_output(
                context=self._kensu_nuclio_context,
                topic=topic,
                cluster_name=self._kensu_stored_config.get('bootstrap.servers') or 'unknown',
                output_data=value)
        except Exception:
            pass
        return result

    def kensu_set_nuclio_context(self, context):
        # FIXME: store only needed info - context.user_data
        self._kensu_nuclio_context = context

    def __init__(self, config):
        super().__init__(config)
        # FIXME: store only needed info - bootstrap.servers
        self._kensu_stored_config = config
        self._kensu_nuclio_context = None
