import logging
import json
import time
import re
from kensu.utils.helpers import singleton, to_snake_case
from .kensu_class_handlers import KensuClassHandlers
from .. import client


@singleton
class Injection(object):
    ENTITIES_INJECTED = False
    DO_REPORT = True
    REPORT_TO_FILE = False
    OFFLINE_FILE = None

    # function taking three args: the entity, the api client, and the reporting method
    REPORTER = None

    @staticmethod
    def do_nothing_reporter(obj, kensu_api, method):
        return obj

    @staticmethod
    def printing_reporter(obj, kensu_api, method):
        json = Injection().get_offline_entity_json(obj, kensu_api)
        print(json)
        return obj

    @staticmethod
    def logging_info_reporter(obj, kensu_api, method):
        json = Injection().get_offline_entity_json(obj, kensu_api)
        logging.info(json)
        return obj

    @staticmethod
    def post_reporter(obj, kensu_api, method):
        method(obj)
        return obj

    @staticmethod
    def file_reporter_builder(offline_file_name):
        inj = Injection()
        file = open(offline_file_name or "kensu_offline_events.txt", "a")
        import atexit
        atexit.register(file.close)

        def f(obj, kensu_api, method):
            inj.OFFLINE_FILE.write(inj.get_offline_entity_json(obj, kensu_api))
            inj.OFFLINE_FILE.flush()
            return obj

        return f


    def __init__(self):
        pass

    def set_reporter(self, reporter):
        self.REPORTER = reporter

    def set_do_report(self, do_report=True, report_to_file=False, offline_file_name=None):
        self.DO_REPORT = do_report
        self.REPORT_TO_FILE = report_to_file
        if report_to_file:
            self.OFFLINE_FILE = open(offline_file_name or "kensu_offline_events.txt", "a")
            import atexit
            atexit.register(self.close_gracefully)

    def close(self):
        if self.OFFLINE_FILE is not None:
            self.OFFLINE_FILE.close()

    def close_gracefully(self):
        try:
            self.close()
        except IOError as ex:
            print('Failed closing the offline output file', ex)

    def set_kensu_api(self, kensu_api):
        if not self.ENTITIES_INJECTED:
            self.kensu_inject_entities(kensu_api)

    # injects to_ref and _report to Kensu entities
    def kensu_inject_entities(self, kensu_api):
        if self.ENTITIES_INJECTED:
            return
        this_injection = self
        kensu_entities = ["DataSource", "ProcessLineage", "Process", "ProcessRun", "User",
                        "Schema", "CodeVersion", "CodeBase", "PhysicalLocation", "Model",
                        "ModelTraining", "ModelMetrics", "DataStats", "LineageRun",
                        "Project"]

        def kensu_to_ref(self, use_pk=False):
            if use_pk:
                return getattr(client, self.__class__.__name__ + "Ref")(by_pk=self.pk)
            else:
                return getattr(client, self.__class__.__name__ + "Ref")(by_guid=self.to_guid())

        # note: self here is not Injection anymore but the object used during the method call below
        def kensu_report(self):
            c = self.__class__.__name__
            cc = to_snake_case(c)
            method_name = "report_" + cc
            method = getattr(kensu_api, method_name)
            if this_injection.REPORTER:
                this_injection.REPORTER(self, kensu_api, method)
            elif this_injection.DO_REPORT:
                if not this_injection.REPORT_TO_FILE:
                    # call method with self
                    method(self)
                else:
                    Injection().OFFLINE_FILE.write(this_injection.get_offline_entity_json(self, kensu_api))
                    Injection().OFFLINE_FILE.flush()
            return self

        to_guid_func = lambda x: KensuClassHandlers.guid.__func__(KensuClassHandlers, x)
        for c in kensu_entities:
            setattr(getattr(client, c), 'to_guid', to_guid_func)
            setattr(getattr(client, c), 'to_ref', kensu_to_ref)
            setattr(getattr(client, c), '_report', kensu_report)

        self.ENTITIES_INJECTED = True

    @staticmethod
    def get_offline_entity_json(entity, kensu_api):
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
