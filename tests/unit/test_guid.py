#  python -m unittest discover -s tests/unit

import json
import unittest

import urllib3

from kensu.client import ApiClient
from kensu.client import rest
from kensu.utils.kensu import Kensu
from kensu.utils.kensu_class_handlers import KensuClassHandlers


class TestRawEvents(unittest.TestCase):
    TypeToClass = {
        "PHYSICAL_LOCATION": "PhysicalLocation"
        , "USER": "User"
        , "CODE_BASE": "CodeBase"
        , "CODE_VERSION": "CodeVersion"
        , "PROCESS": "Process"
        , "PROCESS_RUN": "ProcessRun"
        , "DATA_SOURCE": "DataSource"
        , "SCHEMA": "Schema"
        , "PROCESS_LINEAGE": "ProcessLineage"
        , "LINEAGE_RUN": "LineageRun"
        , "DATA_STATS": "DataStats"
        , "MODEL": "Model"
        , "MODEL_TRAINING": "ModelTraining"
        , "MODEL_METRICS": "ModelMetrics"
    }

    kensu = Kensu(kensu_ingestion_url="http://example.com", init_context = False, reporter ="DoNothingReporter")

    def setUp(self):
        self.data = {}
        # Load test data
        ac = ApiClient()
        with open('tests/unit/data/raw-events.json') as fp:
            for line in fp:
                j = json.loads(line)
                if j["action"] == "add_entity": # only entities
                    jp = j["jsonPayload"]
                    r = rest.RESTResponse(urllib3.response.HTTPResponse(json.dumps(jp)))
                    e = ac.deserialize(r, TestRawEvents.TypeToClass[j["entity"]])
                    self.data[j["generatedEntityGUID"]] = e
                
    def test_guids(self):
        for [expected_guid, entity] in self.data.items() :
            guid = KensuClassHandlers.guid(entity)
            self.assertEqual(guid, expected_guid)
                
    def test_to_guids(self):
        for [expected_guid, entity] in self.data.items() :
            guid = entity.to_guid()
            self.assertEqual(guid, expected_guid)


if __name__ == '__main__':
    unittest.main()