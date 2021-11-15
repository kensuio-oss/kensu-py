from abc import ABC, abstractmethod
import json
import logging
import re
import time
from kensu.utils.helpers import singleton, to_snake_case

class Reporter(object):

    def __init__(self, config):
        self.config = config
    
    # function taking three args: the entity, the api client, and the reporting method (e.g. `report_datastats`)
    @abstractmethod
    def apply(self, obj, kensu_api, method):
        pass 

    def entity_to_json_event(self, entity, kensu_api):
        # FIXME: check if there's a nicer way than to call kensu_api.api_client.sanitize_for_serialization
        sanitized_body = kensu_api.api_client.sanitize_for_serialization(entity)
        # p.s. serialization based on existing rules in kensu-client-scala
        now = round(1000.0 * time.time())
        offline_entity = {
            "action": "add_entity",
            "entity": re.sub(r'(.)([A-Z])', r'\1_\2', entity.__class__.__name__).upper(),
            "generatedEntityGUID": "empty",
            "schemaVersion": "0.1",
            "jsonPayload": sanitized_body,
            "context": {
                "clientId": "",
                # FIXME: make this configurable for reporting events in past
                "clientEventTimestamp": now,
                "serverReceivedTimestamp": now
            }
        }
        return json.dumps(offline_entity) + "\n"
    
    @staticmethod
    def create(config, name = None):
        name = name or config.get("name", None)
        reporter = None
        if name == "GenericReporter":
            reporter = GenericReporter(config)
        elif name == "DoNothingReporter":
            reporter = DoNothingReporter(config)
        elif name == "PrintReporter":
            reporter = PrintReporter(config)
        elif name == "LoggingReporter":
            reporter = LoggingReporter(config)
        elif name == "FileReporter":
            reporter = FileReporter(config)
        elif name == "ApiReporter":
            reporter = ApiReporter(config)
        elif name == "KafkaReporter":
            reporter = KafkaReporter(config)
        elif name == "MultiReporter":
            reporter = MultiReporter(config)
        return reporter


class GenericReporter(Reporter):
    def __init__(self, config, fun):
        super().__init__(config)
        self.fun = fun
    def apply(self, obj, kensu_api, method):
        return fun(obj, kensu_api, method)


class DoNothingReporter(Reporter):
    def apply(self, obj, kensu_api, method):
        return obj


class PrintReporter(Reporter):
    def apply(self, obj, kensu_api, method):
        json = self.entity_to_json_event(obj, kensu_api)
        print(json)
        return obj


class LoggingReporter(Reporter):
    def __init__(self, config, level=None):
        super().__init__(config)
        self.level = level
        if self.level is None and config is not None and config["level"] is not None:
            self.level = config["level"]
        self.level = self.level.lower()
        if self.level == "info":
            self.log = logging.info
        elif self.level == "warn":
            self.log = logging.warn
        elif self.level == "error":
            self.log = logging.error
        elif self.level == "debug":
            self.log = logging.debug
        else:
            print('No logging level was specified for LoggingReporter, using ERROR log level')
            self.log = logging.error

    def apply(self, obj, kensu_api, method):
        json = self.entity_to_json_event(obj, kensu_api)
        if self.log:
            res = self.log(obj)
        return obj


class FileReporter(Reporter):
    def __init__(self, config, file_name=None):
        super().__init__(config)
        if config is not None:
            file_name = file_name or config["file_name"]
        self.file = open(file_name, "a")
        import atexit
        atexit.register(self.close_gracefully)

    def close(self):
        if self.file is not None:
            self.file.close()

    def close_gracefully(self):
        try:
            self.close()
        except IOError as ex:
            print('Failed closing the output file', ex)

    def apply(self, obj, kensu_api, method):
        self.file.write(self.entity_to_json_event(obj, kensu_api))
        self.file.flush()
        return obj


class ApiReporter(Reporter):
    def apply(self, obj, kensu_api, method):
        method(obj)
        return obj


class KafkaReporter(Reporter):
    def __init__(self, config):
        super().__init__(config)
        if config is not None:
            from confluent_kafka import Producer
            import socket
            self.bootstrap_servers = ",".join(json.loads(config["bootstrap_servers"]))
            conf = {'bootstrap.servers': self.bootstrap_servers,
                    'client.id': socket.gethostname()}
            self.topic = config["topic"]
            self.producer = Producer(conf)


    def apply(self, obj, kensu_api, method):
        guid = obj.to_guid()
        token_and_entity = {
            "token": kensu_api.api_client.default_headers["X-Auth-Token"],
            "entity": self.entity_to_json_event(obj, kensu_api)
        }
        s = json.dumps(token_and_entity)
        self.producer.produce(self.topic, key=guid, value=s)
        return obj


class MultiReporter(Reporter):
    def __init__(self, config):
        super().__init__(config)
        reporters_names = json.loads(config.get("reporters"))
        self.reporters = [Reporter.create(config, name = name) for name in reporters_names]

    def apply(self, obj, kensu_api, method):
        for r in self.reporters:
            r.apply(obj, kensu_api, method)
