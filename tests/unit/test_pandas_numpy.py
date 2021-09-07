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
from kensu.itertools import kensu_list as list
from kensu import itertools

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)

def ndarray_to_csv(nd_arr, fn):
    return pd.DataFrame(nd_arr).to_csv(fn)

class TestPandasNumpy(unittest.TestCase):
    offline_file = 'pandas_numpy.jsonl'
    ksu = KensuProvider().initKensu(
        #api_url="http://somewhere",
        #auth_token=token,
        init_context=True,
        report_in_mem=False,
        report_to_file=True,
        offline_file_name=offline_file,
        logical_naming='File',
        mapping=True
    )

    def setUp(self):
        self.ac = ApiClient()
        self.dataset = 'tests/unit/fixtures/Macroeconomical.csv'

    def read_df(self, index_col=None, header='infer'):
        return pd.read_csv(self.dataset, sep=';', header=header, index_col=index_col)

    def assert_msg_exists(self, msg, msg2=None):
        with open(self.offline_file, "r") as f:
            assert bool([True for l in f.readlines() if msg in l and (msg2 is None or msg2 in l)])

    def test_df_indexed_value(self):
        out_fname = 'test_df_indexed_value'
        dummy_ts_df = pd.read_csv('https://raw.githubusercontent.com/numenta/NAB/master/data/realTweets/Twitter_volume_AMZN.csv', index_col=0) # header=0,
        # <class 'kensu.pandas.data_frame.DataFrame'>
        value = dummy_ts_df.value[:"2015-04-05 00:00:00"]  # <class 'kensu.pandas.data_frame.Series'>

        print('done')

        # test numpy expressions
        # v = dummy_ts_df.values[0] -> <class 'kensu.numpy.ndarray'>
        #fixme: mask = np.abs((v - v.mean(0)) / v.std(0)) > 100
        #fixme: v = np.where(mask, np.nan, v) # v is target

    def test_df_values_i(self):
        out_fname = 'test_df_values_i'
        df = self.read_df()
        assert str(type(df)) == "<class 'kensu.pandas.data_frame.DataFrame'>"
        df_vals = df.values
        assert str(type(df_vals)) == "<class 'kensu.numpy.ndarray'>"

        df1 = df.values[0] # ndarray/numpy.array
        assert str(type(df1)) == "<class 'kensu.numpy.ndarray'>"

        ndarray_to_csv(df1, out_fname)
        self.assert_msg_exists('Lineage to kensu-py/test_df_values_i from fixtures/Macroeconomical.csv',
                               # FIXME: this might be not stable string (order of items)
                               # '"columnDataDependencies": {"0": ["Income Age (18_49)", "Total Population", "Net national disposable income", "Rainy_days", "Spirtis Price", "Month", "Smoking_prohibition", "unemployment_rate", "LDA Population ", "Temperature", "Soft Drinks Price", "Tomorrowland", "Income Age (25_49)", "Income Age (18_24)", "FIFA", "Beer Price", "Rainfall(mm)", "Wine Price", "Consumer confidence index", "Beer Volume ", "financial_situation_over_next_12m"]}}'
                               )


    # def test_df_to_dict_toDF(self):
    #     out_fname = 'test_df_dict_df'
    #     df = self.read_df()
    #     l = []
    #     # FIXME: not the most relevant test here...
    #     for item in df.values[:1]:
    #         l.append(item)
    #         print(type(item))
    #     # FIXME: numpy.repeat
    #     res = pd.DataFrame(
    #         {
    #             # FIXME: lineage seems to fail here
    #             "column": list(itertools.chain.from_iterable(l)),
    #         }
    #     )
    #     print(type(res))
    #     ndarray_to_csv(res, out_fname)





if __name__ == '__main__':
    unittest.main()
