import google
import pandas
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField

from kensu.google.cloud import bigquery as kensu_bigquery

# FIXME: ambigous table naming do not work currently with SQL service (default database name), e.g.:
# FIXME: `demotest.credit` instead of `psyched-freedom-306508.demotest.credit
from kensu.google.cloud.bigquery.job.offline_parser import BqOfflineParser

sample_sql = f"""SELECT DATE_KEY, "ARG" AS COUNTRY_KEY, s.STORE_KEY, CHAIN_TYPE_DESC, CARD_FLAG, sum(TOTAL) AS CA 
            FROM `psyched-freedom-306508`.`cf`.ARG-stores` AS s
            INNER JOIN `psyched-freedom-306508.cf.ARG-tickets` AS t
            ON s.STORE_KEY = t.STORE_KEY
            WHERE DATE_KEY = "2021-05-23" 
            GROUP BY DATE_KEY, s.STORE_KEY, CHAIN_TYPE_DESC, CARD_FLAG"""

bigquery_schemas = {
    # table_id (project.dataset.table) => schema
    "psyched-freedom-306508.cf.ARG-stores": [
        {"name": "CHAIN_TYPE_DESC", "type": "STRING"},
        {"name": "STORE_KEY", "type": "INTEGER"}
    ],
    "psyched-freedom-306508.cf.ARG-tickets": [
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


def make_bq_table(id, schema):
    t = google.cloud.bigquery.table.Table(id, schema=schema)
    # t.full_table_id = id
    t._properties[t._PROPERTY_TO_API_FIELD["full_table_id"]] = id
    return t


table_id_to_bqtable = dict([
    (t_id, make_bq_table(t_id, schema=[SchemaField(f['name'], f['type']) for f in schema]))
    for t_id, schema in bigquery_schemas.items()])


def mock(mocker):
    # also see https://stackoverflow.com/a/61111368
    # FIXME: we don't support rowIterator as result yet
    # from google.cloud.bigquery.table import _EmptyRowIterator
    # job_result = mocker.Mock(spec=_EmptyRowIterator())

    res_fields = ["DATE_KEY", "COUNTRY_KEY", "STORE_KEY", "CHAIN_TYPE_DESC", "CARD_FLAG", "CA"]
    res_sample_data = [["2012-01-01", "LT", 123, "A", "OK", 123]]
    res_table = make_bq_table("psyched-freedom-306508._temp._temp_out1234",
                              schema=[SchemaField(f, "DATE") for f in res_fields])
    job_result = mocker.Mock(
        spec=res_table,
        path=res_table.path,
        schema=res_table.schema,
        to_dataframe=lambda: pandas.DataFrame(res_sample_data, columns=res_fields))

    # as Kensu inherits/wraps QueryJob & Client, need a bit of special
    # patching magic to make the base class patching work
    # see https://newbedev.com/python-mock-mocking-base-class-for-inheritance
    kensu_bigquery.job.query.QueryJob.__bases__ = (
        FakeBaseClass.imitate(mocker, google.cloud.bigquery.job.query.QueryJob,
                              method_return_values={'query': sample_sql,
                                                    'result': job_result}),)

    kensu_bigquery.Client.__bases__ = (FakeBaseClass.imitate(
        mocker,
        google.cloud.bigquery.Client,
        method_return_values={
            # returns a Job with attr query returning sql
            'query': mocker.Mock(
                # define job.result here with type Iterator?
                spec=google.cloud.bigquery.job.query.QueryJob,
                query=sample_sql,
                referenced_tables=list(table_id_to_bqtable.keys()),
                ddl_target_table=None,
                destination=res_table,
                result=lambda: job_result
            ),
        },
        attr_values={
            'get_table': lambda self, table_id: table_id_to_bqtable[table_id]
        }),)


class FakeBaseClass(object):
    """Create Mock()ed methods that match another class's methods.
    """

    @classmethod
    def imitate(cls, mocker, *others,
                method_return_values={},  # for methods, e.g.: .query()
                attr_values={},  # for attributes or functions with params, e.g.: .query, .get_table(name)
                ):
        for other in others:
            for name in other.__dict__:
                if name != "__init__":
                    try:
                        if name in method_return_values:
                            setattr(cls, name,
                                    mocker.Mock(name=name + '_with_return_value',
                                                return_value=method_return_values[name]))
                        elif name in attr_values:
                            setattr(cls, name, attr_values[name])
                        else:
                            setattr(cls, name, mocker.Mock(name=name))
                        # mocker.patch.object(cls, name, autospec=True)
                    except (TypeError, AttributeError):
                        pass
        return cls
