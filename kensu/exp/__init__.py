import urllib3
urllib3.disable_warnings()
from kensu.utils.kensu import Kensu
from kensu.client.models import *
from kensu.utils.helpers import to_datasource

from pyspark.sql import DataFrame
from pyspark.sql import SparkSession
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

def tagInMemWrapper():
    def tagInMemInner(self,  # type: DataFrame
                      name   # type: str
                      ):
        return tagInMem(self, name)
    return tagInMemInner


DataFrame.tagInMem = tagInMemWrapper()

def tagCreateDataFrame(self,name):

    #Get spark session info
    spark = get_spark_session()
    spark_info=get_process_run_info(spark)
    process = spark_info['process_guid']

    # Creation of an in-mem data source
    location = f'in-mem://{process}/{name}'
    format='in-mem'
    ds_pk=DataSourcePK(location=location,physical_location_ref=PhysicalLocationRef(by_pk=Kensu().UNKNOWN_PHYSICAL_LOCATION.pk))

    k = KensuProvider().instance()
    ds = to_datasource(ds_pk, format, location, 'File', name)._report()

    #TODO Real schema

    fields = [FieldDef('unknown', 'unknown', False)]
    schema = Schema(name, pk=SchemaPK(data_source_ref=DataSourceRef(by_guid=ds.to_guid()), fields=fields))._report()
    k.name_schema_lineage_dict[name] = schema.to_guid()

    return self

def tagCreateDataFrameWrapper():
    def tagInMemInner(self,  # type: DataFrame
                      name   # type: str
                      ):
        return tagCreateDataFrame(self, name)
    return tagInMemInner

DataFrame.tagCreateDataFrame = tagCreateDataFrameWrapper()


def create_publish_for_sklearn_model(model, location, name):
    format = 'SKLearn'
    ds_pk = DataSourcePK(location=location,
                         physical_location_ref=PhysicalLocationRef(by_pk=Kensu().UNKNOWN_PHYSICAL_LOCATION.pk))

    k = KensuProvider().instance()
    ds = DataSource(name=name,format=format,categories=[f'logical::{name}'],pk=ds_pk)._report()

    fields = [FieldDef('intercept','Numeric',False),FieldDef('coeff','Numeric',False)]
    schema = Schema(name,pk=SchemaPK(data_source_ref=DataSourceRef(by_guid=ds.to_guid()),fields=fields))._report()
    k.name_schema_lineage_dict[name] = schema.to_guid()


def get_schema(name):
   # use the lookup table
   k = KensuProvider().instance()
   return k.name_schema_lineage_dict[name]


def create_lineage(inputs,output):
    data_flow = [SchemaLineageDependencyDef(SchemaRef(by_guid=i),SchemaRef(by_guid=output),{'unknown':['unknown']}) for i in inputs ]
    lineage = ProcessLineage(name=f'Lineage to {str(output)}',operation_logic='APPEND',pk=ProcessLineagePK(process_ref=ProcessRef(by_guid=get_process_run_info(get_spark_session())['process_guid']),
                                                                                                           data_flow=data_flow))._report()
    return lineage

def link(input_names, output_name):
    # retrieve schemas for inputs
    input_scs = [get_schema(i) for i in input_names]
    # retrieve schemas for outputs
    output_sc = get_schema(output_name)
    # create lineage
    lineage = create_lineage(input_scs,output_sc)._report()
    # create lineage run
    spark_run = get_process_run_info(get_spark_session())['process_run_guid']
    k = KensuProvider().instance()
    lineage_run = LineageRun(LineageRunPK(process_run_ref=ProcessRunRef(by_guid=spark_run),lineage_ref=ProcessLineageRef(by_guid=lineage.to_guid()),timestamp=1000*k.timestamp))._report()