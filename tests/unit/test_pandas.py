#  python -m unittest discover -s tests/unit

import logging
import sys
import unittest

import kensu.pandas as pd
from kensu.client import ApiClient
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.dsl import mapping_strategies
from kensu.utils.dsl.mapping_strategies import Strategy

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)


class TestPandas(unittest.TestCase):
    token = "eyJhbGciOiJIUzI1NiJ9.eyIkaW50X3Blcm1zIjpbXSwic3ViIjoib3JnLnBhYzRqLmNvcmUucHJvZmlsZS5Db21tb25Qcm9maWxlI3NhbW15IiwidG9rZW5faWQiOiI4NmYxMWU0Ni02NDk1LTRkNWItODhjZS01ODk1NTAxNDM0NzUiLCJhcHBncm91cF9pZCI6IjUyZTVkNDNjLTM0ZGYtNGRkZi1hM2Y3LTIwODU2Y2MzOWY2ZCIsIiRpbnRfcm9sZXMiOlsiYXBwIl0sImV4cCI6MTg4ODE0MTk2NiwiaWF0IjoxNTcyNzgxOTY2fQ.4CdaN9a80xc1ry6aT52MFxc33vb0nJVXX5TdGzdoJ7E"
    kensu = KensuProvider().initKensu(api_url="https://api.sandbox.kensu.io", auth_token=token, init_context=True)

    # FIXME... dunno ... that sounds rather nasty
    # def _constructor(self):
    #     print("yolo")
    #     return pd.DataFrame
    # opd.DataFrame._constructor = property(_constructor)

    def setUp(self):
        self.ac = ApiClient()
        self.dataset = 'tests/unit/fixtures/Macroeconomical.csv'

    def test_one(self):
        dataframe = pd.read_csv(self.dataset, sep=';')

        t = 11

        # lineage to send to kensu
        newdata = dataframe.iloc[:, [0, 4, 5]]
        self.kensu.add_dependency(dataframe, newdata, mapping_strategy=mapping_strategies.DIRECT)
        newdata.to_json('output/pd_iloc_test_{}.json'.format(t))

        # other lineage to send to kensu
        # *WARN*;
        #  we need to do this because otherwise, the object is mutated and unicity is kept between newdata and newdata2
        newdata_kensu = self.kensu.extractors.extract_data_source_and_schema(newdata, self.kensu.default_physical_location_ref)
        print(newdata_kensu)
        newdata2 = newdata
        newdata2.loc[:, 'Total'] = newdata2.loc[:, 'Spirtis Price'] + newdata2.loc[:, 'Wine Price']
        self.kensu.add_dependency((newdata, newdata_kensu[0], newdata_kensu[1]), newdata2, mapping_strategy=mapping_strategies.DIRECT.or_else(
            Strategy.from_dict({"Total": ['Spirtis Price', 'Wine Price']})))
        newdata2.to_json('output/pd_loc_test_{}.json'.format(t))


if __name__ == '__main__':
    unittest.main()
