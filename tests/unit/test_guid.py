#  python -m unittest discover -s tests/unit
'''

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

    kensu = Kensu(api_url = "http://example.com", init_context = False)

    def setUp(self):
        self.data = {}
        # Load test data
        ac = ApiClient()
        with open('tests/unit/fixtures/raw-events.json') as fp:
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

'''
from kensu.client.models import *
from kensu.utils.injection import Injection
Injection().kensu_inject_entities('api')
v= DataSource(name='predict/jan-customers-data.csv',format='csv',pk=DataSourcePK(location='file:/Users/kensu/Customers/Kensu/oreilly/data/predict/jan-customers-data.csv',physical_location_ref=PhysicalLocationRef(by_guid='k-d2f40e99e5dd4c9fc9c634b15a7fb03073191c0158e52a572769df8c05f59b7b')))
print(v.to_guid())