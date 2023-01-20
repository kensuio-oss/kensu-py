import urllib3
urllib3.disable_warnings()
from kensu.utils.kensu import Kensu
from kensu.client.models import *
from kensu.utils.helpers import to_datasource

from pyspark.sql.dataframe import DataFrame
from pyspark.sql.session import SparkSession
from kensu.pyspark import get_process_run_info, get_inputs_lineage_fn
from kensu.utils.kensu_provider import KensuProvider


def get_spark_session():
    import gc
    for obj in gc.get_objects():
        if isinstance(obj, SparkSession):
            kensu_spark_session = obj
    return kensu_spark_session or None

import types

def tagInMem(self,name):

    #Get spark session info
    spark = get_spark_session()
    spark_info=get_process_run_info(spark)
    process = spark_info['process_guid']

    # Creation of an in-mem data source
    location = f'in-mem://{process}/{name}'
    format='in-mem'
    ds_pk=DataSourcePK(location=location,physical_location_ref=PhysicalLocationRef(by_pk=Kensu().UNKNOWN_PHYSICAL_LOCATION.pk))

    k = KensuProvider().instance()
    to_datasource(ds_pk, format, location, 'File', name)._report()

    get_inputs_lineage_fn(kensu_instance=KensuProvider().instance(),
                          df=self)

    return self

DataFrame.tagInMem = property(tagInMem)


def create_publish_for_sklearn_model(model, location, name):
    format = 'SKLearn'
    ds_pk = DataSourcePK(location=location,
                         physical_location_ref=PhysicalLocationRef(by_pk=Kensu().UNKNOWN_PHYSICAL_LOCATION.pk))

    k = KensuProvider().instance()
    ds = to_datasource(ds_pk, format, location, 'File', name)._report()

    fields = [FieldDef('intercept','Numeric',False),FieldDef('coeff','Numeric',False)]
    schema = Schema(name,pk=SchemaPK(data_source_ref=DataSourceRef(by_guid=ds.to_guid),fields=fields))._report()
