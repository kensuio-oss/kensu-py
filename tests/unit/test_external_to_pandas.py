#  python -m unittest discover -s tests/unit

import logging
import sys
import unittest

import kensu.pandas as pd
from kensu.client import ApiClient
from kensu.utils.kensu_provider import KensuProvider

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)

# Below is an example of how easily one could track a lineage of data conversion from an external library into pandas
# A real world example would be Apache Spark's DataFrame.toPandas() function,
# here to reduce need of heavy dependency we use a mocked version of such function


class FakeSparkDataFrame:

    def toPandas(self):
        import pandas as pd_orig
        data = [['tom', 10], ['nick', 15], ['juli', 14]]
        df = pd_orig.DataFrame(data, columns = ['out_field_name1', 'Age'])
        return df


def get_inputs_lineage_fn(ksu, df):
    from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema, GenericComputedInMemDs, \
        ExtDependencyEntry
    from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
    pl_ref = ksu.UNKNOWN_PHYSICAL_LOCATION.to_ref()
    ds_pk = DataSourcePK(location="hdfs://namenode/dataset1/partition1/file1.parquet", physical_location_ref=pl_ref)
    ds = DataSource(name="file1.parquet", format="parquet", categories=['logical::dataset1'], pk=ds_pk)
    fields = [
        FieldDef(name=str("in1"), field_type="string", nullable=True),
        FieldDef(name=str("in2"), field_type="string", nullable=True),
    ]
    schema = Schema(name="schema:" + ds.name,
                    pk=SchemaPK(ds.to_ref(), fields=fields))
    lineage_info = [ExtDependencyEntry(
        input_ds=KensuDatasourceAndSchema(ksu_ds=ds, ksu_schema=schema, f_get_stats=lambda: {'in1.max': 123.12}),
        lineage={
            "out_field_name1": ["in1", "in2"],
            "Age": ["in2"]

        })]
    return GenericComputedInMemDs(inputs=list([x.input_ds for x in lineage_info]), lineage=lineage_info)


def patch_external_transformation():
    print('patching FakeDataFrame.toPandas')
    FakeSparkDataFrame.toPandas = pd.data_frame.wrap_external_to_pandas_transformation(
        FakeSparkDataFrame.toPandas,
        get_inputs_lineage_fn
    )
    print('done patching FakeDataFrame.toPandas')


class TestExternalToPandas(unittest.TestCase):
    offline = True
    kensu = KensuProvider().initKensu(init_context=True,
                                      report_to_file=offline,
                                      offline_file_name='kensu-offline-to-pandas-test.jsonl',
                                      mapping=True, report_in_mem=True)

    def setUp(self):
        self.ac = ApiClient()
        patch_external_transformation()

    def test_one(self):
        FakeSparkDataFrame().\
            toPandas()\
            .to_csv('fake_spark_to_pandas_out')


if __name__ == '__main__':
    unittest.main()
