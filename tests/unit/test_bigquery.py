#  python -m unittest discover -s tests/unit

import unittest

import google.cloud.bigquery.job.query
import pandas
import pandas as pd
import pytest
from google.cloud.bigquery import SchemaField

import kensu.google.cloud.bigquery.job.query

# see https://newbedev.com/python-mock-mocking-base-class-for-inheritance
from kensu.google.cloud.bigquery.job.offline_parser import BqOfflineParser


class Fake(object):
    """Create Mock()ed methods that match another class's methods."""

    @classmethod
    def imitate(cls, mocker, *others, return_values={}):
        for other in others:
            for name in other.__dict__:
                if name != "__init__":
                    try:
                        if name in return_values:
                            setattr(cls, name,
                                    mocker.Mock(name=name + '_with_return_value', return_value=return_values[name]))
                        else:
                            setattr(cls, name, mocker.Mock(name=name))
                        # mocker.patch.object(cls, name, autospec=True)
                    except (TypeError, AttributeError):
                        pass
        return cls


@pytest.mark.usefixtures("mocker")
class TestBigQuery(unittest.TestCase):

    def setUp(self):
        pass

    @pytest.fixture(autouse=True)
    def init_mocker(self, mocker):
        print('init_mocker')
        self.mocker = mocker

    def test_one(self):
        # see https://stackoverflow.com/a/61111368
        # mock_table = mocker.patch('google.cloud.bigquery.Table', autospec=True)
        from google.cloud import bigquery
        # mock_client = self.mocker.patch.object(bigquery, 'Client', autospec=True)
        # mock_client = self.mocker.patch.object(bigquery, 'Client.query', autospec=True)

        from tests.unit.testing_helpers import setup_logging
        setup_logging()
        from tests.unit.testing_helpers import setup_kensu_tracker
        setup_kensu_tracker(test_cls=self,
                            bigquery_support=True,
                            report_in_mem=False,
                            compute_stats=False  # FIXME: stats testing disabled for now... :(
                            )
        from kensu.google.cloud import bigquery as kensu_bigquery

        # FIXME: ambigous table naming do not work currently with SQL service (default database name), e.g.:
        # FIXME: `demotest.credit` instead of `psyched-freedom-306508.demotest.credit
        sql = f"""SELECT DATE_KEY, "ARG" AS COUNTRY_KEY, s.STORE_KEY, CHAIN_TYPE_DESC, CARD_FLAG, sum(TOTAL) AS CA 
                    FROM `psyched-freedom-306508.cf.ARG-stores` AS s 
                    INNER JOIN `psyched-freedom-306508.cf.ARG-tickets` AS t 
                    ON s.STORE_KEY = t.STORE_KEY
                    WHERE DATE_KEY = "2021-05-23" 
                    GROUP BY DATE_KEY, s.STORE_KEY, CHAIN_TYPE_DESC, CARD_FLAG"""

        sample_metadata = {
            "tables": [
                {
                    "id": "`psyched-freedom-306508.cf.ARG-stores`",
                    "schema": {
                        "fields": [
                            {"name": "CHAIN_TYPE_DESC", "type": "STRING"},
                            {"name": "STORE_KEY", "type": "INTEGER"}
                        ]
                    }
                },
                {
                    "id": "`psyched-freedom-306508.cf.ARG-tickets`",
                    "schema": {
                        "fields": [
                            {"name": "TICKET_KEY", "type": "STRING"},
                            {"name": "CUSTOMER_KEY", "type": "STRING"},
                            {"name": "DATE_KEY", "type": "DATE"},
                            {"name": "STORE_KEY", "type": "INTEGER"},
                            {"name": "TOTAL", "type": "FLOAT"},
                            {"name": "NBR_ITEMS", "type": "INTEGER"},
                            {"name": "CARD_FLAG", "type": "INTEGER"},
                            {"name": "CARD_FLAGGED", "type": "BOOLEAN"}
                        ]
                    }
                }
            ]
        }
        table_id_to_bqtable = dict([
            (x, google.cloud.bigquery.table.Table(x.replace("`", ""))) for x in [
                # project, dataset, table
                "`psyched-freedom-306508.cf.ARG-stores`",
                "`psyched-freedom-306508.cf.ARG-tickets`"
            ]])

        self.mocker.patch.object(BqOfflineParser, 'get_referenced_tables_metadata', lambda kensu, client, sql_query: \
            (sample_metadata, table_id_to_bqtable, []))

        # FIXME: we don't support rowIterator as result yet
        # from google.cloud.bigquery.table import _EmptyRowIterator
        # job_result = self.mocker.Mock(spec=_EmptyRowIterator())
        out_fields = ["DATE_KEY", "COUNTRY_KEY", "STORE_KEY", "CHAIN_TYPE_DESC", "CARD_FLAG", "CA"]
        out_table = google.cloud.bigquery.table.Table("psyched-freedom-306508._temp._temp_out1234",
                                                      schema=[SchemaField(f, "DATE") for f in out_fields])
        job_result = self.mocker.Mock(
            spec=out_table,
            # wraps=out_table,
            path=out_table.path,
            schema=out_table.schema,
            to_dataframe=lambda: pandas.DataFrame(
                [["2012-01-01", "LT", 123, "A", "OK", 123]],
                columns=out_fields))
        kensu_bigquery.job.query.QueryJob.__bases__ = (
        Fake.imitate(self.mocker, google.cloud.bigquery.job.query.QueryJob,
                     return_values={'query': sql,
                                    'result': lambda: job_result}),)

        kensu_bigquery.Client.__bases__ = (Fake.imitate(self.mocker, bigquery.Client,
                                                        return_values={
                                                            # returns a Job with attr query returning sql
                                                            'query': self.mocker.Mock(
                                                                # define job.result here with type Iterator?
                                                                spec=google.cloud.bigquery.job.query.QueryJob,
                                                                query=sql,
                                                                result=lambda: job_result
                                                            )
                                                        }),)
        client = kensu_bigquery.Client()

        q = client.query(sql)
        df = q.to_dataframe()
        df.to_csv('test_res_from_bigquery')

        # mock_table.assert_called_with('project.dataset.blahblahbloo', schema=schema)
        # mock_client().query.assert_called_with(sql)


if __name__ == '__main__':
    unittest.main()
