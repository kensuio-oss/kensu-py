#  python -m unittest discover -s tests/unit

import unittest
import pytest
from tests.unit import mocked_bigquery
from tests.unit.testing_helpers import assert_log_msg_exists


@pytest.mark.usefixtures("mocker")
class TestBigQuery(unittest.TestCase):

    def setUp(self):
        pass

    @pytest.fixture(autouse=True)
    def init_mocker(self, mocker):
        print('init_mocker')
        self.mocker = mocker

    def test_one(self):
        from tests.unit.testing_helpers import setup_logging, setup_kensu_tracker
        setup_logging()
        setup_kensu_tracker(test_cls=self,
                            bigquery_support=True,
                            report_in_mem=False,
                            compute_stats=False  # FIXME: stats testing disabled for now... :(
                            )
        from kensu.google.cloud import bigquery as kensu_bigquery
        mocked_bigquery.mock(self.mocker)

        client = kensu_bigquery.Client()
        q = client.query(mocked_bigquery.sample_sql)
        df = q.to_dataframe()
        df.to_csv('test_res_from_bigquery')
        assert_log_msg_exists(
            # FIXME: output name repeated, why?
            'Lineage to unit/test_res_from_bigquery,unit/test_res_from_bigquery from bigquery://projects/psyched-freedom-306508/datasets/cf/tables/ARG-stores,bigquery://projects/psyched-freedom-306508/datasets/cf/tables/ARG-tickets',
        )
        # FIXME: check that 'TestBigQuery.jsonl' contains  DATA_SOURCE, SCHEMA
        # FIXME: check that 'TestBigQuery.jsonl' contains  DATA_STATS


if __name__ == '__main__':
    unittest.main()
