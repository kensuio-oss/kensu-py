import google
import pandas
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField

from kensu.google.cloud import bigquery as kensu_bigquery

# FIXME: ambigous table naming do not work currently with SQL service (default database name), e.g.:
# FIXME: `demotest.credit` instead of `psyched-freedom-306508.demotest.credit
from kensu.google.cloud.bigquery.job.offline_parser import BqOfflineParser

sample_sql = f"""SELECT DATE_KEY, "ARG" AS COUNTRY_KEY, s.STORE_KEY, CHAIN_TYPE_DESC, CARD_FLAG, sum(TOTAL) AS CA 
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


def mock(mocker):
    # also see https://stackoverflow.com/a/61111368
    # FIXME: refactor our code so we won't need to patch this guy...
    mocker.patch.object(BqOfflineParser, 'get_referenced_tables_metadata', lambda kensu, client, query: \
        (sample_metadata, table_id_to_bqtable, []))

    # FIXME: we don't support rowIterator as result yet
    # from google.cloud.bigquery.table import _EmptyRowIterator
    # job_result = mocker.Mock(spec=_EmptyRowIterator())

    res_fields = ["DATE_KEY", "COUNTRY_KEY", "STORE_KEY", "CHAIN_TYPE_DESC", "CARD_FLAG", "CA"]
    res_sample_data = [["2012-01-01", "LT", 123, "A", "OK", 123]]
    res_table = google.cloud.bigquery.table.Table("psyched-freedom-306508._temp._temp_out1234",
                                                  schema=[SchemaField(f, "DATE") for f in res_fields])
    job_result = mocker.Mock(
        spec=res_table,
        # wraps=out_table,
        path=res_table.path,
        schema=res_table.schema,
        to_dataframe=lambda: pandas.DataFrame(res_sample_data, columns=res_fields))

    # as Kensu inherits/wraps QueryJob & Client, need a bit of special
    # patching magic to make the base class patching work
    # see https://newbedev.com/python-mock-mocking-base-class-for-inheritance
    kensu_bigquery.job.query.QueryJob.__bases__ = (
        FakeBaseClass.imitate(mocker, google.cloud.bigquery.job.query.QueryJob,
                              attr_return_values={'query': sample_sql,
                                             'result': lambda: job_result}),)

    kensu_bigquery.Client.__bases__ = (FakeBaseClass.imitate(mocker, google.cloud.bigquery.Client,
                                                             attr_return_values={
                                                                 # returns a Job with attr query returning sql
                                                                 'query': mocker.Mock(
                                                                     # define job.result here with type Iterator?
                                                                     spec=google.cloud.bigquery.job.query.QueryJob,
                                                                     query=sample_sql,
                                                                     result=lambda: job_result
                                                                 )
                                                             }),)


class FakeBaseClass(object):
    """Create Mock()ed methods that match another class's methods.
    """

    @classmethod
    def imitate(cls, mocker, *others, attr_return_values={}):
        for other in others:
            for name in other.__dict__:
                if name != "__init__":
                    try:
                        if name in attr_return_values:
                            setattr(cls, name,
                                    mocker.Mock(name=name + '_with_return_value', return_value=attr_return_values[name]))
                        else:
                            setattr(cls, name, mocker.Mock(name=name))
                        # mocker.patch.object(cls, name, autospec=True)
                    except (TypeError, AttributeError):
                        pass
        return cls
