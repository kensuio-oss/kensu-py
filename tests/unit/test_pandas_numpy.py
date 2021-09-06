#  python -m unittest discover -s tests/unit

import logging
import sys
import unittest

import kensu.pandas as pd
from kensu.client import ApiClient
import kensu
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.dsl import mapping_strategies
from kensu.utils.dsl.mapping_strategies import Strategy

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)

def ndarray_to_csv(nd_arr, fn):
    return pd.DataFrame(nd_arr).to_csv(fn)

class TestPandasNumpy(unittest.TestCase):
    ksu = KensuProvider().initKensu(
        #api_url="http://somewhere",
        #auth_token=token,
        init_context=True,
        report_in_mem=False,
        report_to_file=True,
        offline_file_name='pandas_numpy.jsonl',
        logical_naming='File',
        mapping=True
    )

    def setUp(self):
        self.ac = ApiClient()
        self.dataset = 'tests/unit/fixtures/Macroeconomical.csv'

    def read_df(self):
        return pd.read_csv(self.dataset, sep=';')

    def test_df_values_i(self):
        fname = 'test_df_values_i'
        df = self.read_df()
        assert str(type(df)) == "<class 'kensu.pandas.data_frame.DataFrame'>"
        df_vals = df.values
        assert str(type(df_vals)) == "<class 'kensu.numpy.ndarray'>"

        df1 = df.values[0] # ndarray/numpy.array
        assert str(type(df1)) == "<class 'kensu.numpy.ndarray'>"
        ndarray_to_csv(df1, fname)
        print('done')




if __name__ == '__main__':
    unittest.main()
