import logging

import urllib3

urllib3.disable_warnings()
from kensu.utils.kensu import Kensu
from kensu.client.models import *
from kensu.utils.helpers import to_datasource

from pyspark.sql import DataFrame
from pyspark.sql import SparkSession
from kensu.pyspark import get_process_run_info, get_inputs_lineage_fn, register_manual_lineage, get_spark_from_df, \
    get_df_with_inmem_tag
from kensu.utils.kensu_provider import KensuProvider


def get_spark_session():
    kensu_spark_session = None
    try:
        import gc
        for obj in gc.get_objects():
            if isinstance(obj, SparkSession):
                kensu_spark_session = obj
    except:
        return None
    else:
        return kensu_spark_session


import types


def get_schema_fields_from_spark_df(
        spark_df,  # type: DataFrame
):
    return list([
        FieldDef(name=f.name, field_type=f.dataType.simpleString(), nullable=False)
        for f in spark_df.schema.fields
    ])


def register_in_mem_schema(
        ds,  # type: DataSource
        schem_fields,  # type: list[FieldDef]
        in_mem_location,  # type: str
        in_mem_name  # type: str
):
    schema = Schema(in_mem_location, pk=SchemaPK(data_source_ref=DataSourceRef(by_guid=ds.to_guid()),
                                                 fields=schem_fields))._report()
    k = KensuProvider().instance()
    k.name_schema_lineage_dict[in_mem_name] = schema.to_guid()
    return schema


"""
Tag a Spark DataFrame as in-mem datasource, assuming that it will be transformed into python by using say .toPandas().
The result in Kensu will be: [spark input{1,2,..}] --lineage--> [in-mem: name]

Currently only a single .tagInMem() call is allowed on same Spark DataFrame. 
The subsequent calls would be interpreted as individual in-mem data-sources not dependent on the earlier one (due to
how spark works - DataFrame is never materialized before "write"), i.e.:
    `spark_df.tagInMem('name1').filter('col1 = 1').tagInMem('name2')`
would create two UNRELATED in-mem data-sources.
"""


def tagInMem(self,  # type: DataFrame
             name):
    try:
        # Get spark session info
        # FIXME: we can get Spark session more reliably/efficiently from `self: DataFrame`,
        #  while databricks have multiple sessions (and not sure about isolation there)!
        # spark = get_spark_session()
        # FIXME: check if self is Spark DataFrame?
        spark_df = self
        spark = get_spark_from_df(spark_df)
        spark_info = get_process_run_info(spark)
        process = spark_info['process_guid']

        # Creation of an in-mem data source
        spark_ds_name = f'{process}/{name}'
        # location = f'in-memory-data://{process}/{name}'
        location = f'in-memory-data://{spark_ds_name}'
        format = 'in-mem'
        k = KensuProvider().instance()
        ds_pk = DataSourcePK(location=location,
                             physical_location_ref=PhysicalLocationRef(by_pk=k.UNKNOWN_PHYSICAL_LOCATION.pk))
        df_ds = to_datasource(ds_pk, format, location, 'File', name)._report()
        spark_df_schema = register_in_mem_schema(
            ds=df_ds,
            schem_fields=get_schema_fields_from_spark_df(spark_df),
            in_mem_location=location,
            in_mem_name=name
        )
        spark_df_schema._report()

        # report Spark lineage to Kensu
        # FIXME: check if self is Spark DataFrame
        # report lineage to Kensu
        spark_lineage = get_inputs_lineage_fn(kensu_instance=k, df=spark_df, virtual_ds_name=spark_ds_name)
        print('got lineage from spark, just before calling .toPandas()')
        print(spark_lineage)
        # FIXME: we could use this and also report spark datastats
        # FIXME: or should we report using low level apis instead, so we'd easily keep the process info extracted from spark
        # spark_lineage.report(
        #     ksu=k,
        #     df_result=spark_df_schema,  # we don't handle Spark DataFrame directly in extractors yet, so pass a schema
        #     operation_type='Spark to Python',
        #     report_output=True,
        #     register_output_orig_data=False
        # )
        # k.report_with_mapping()
        report_spark_lineage(spark_lineage, k=k, result_schema=spark_df_schema, output_name=name)
    except Exception as e:
        logging.warning(f"tagInMem for toPandas didnt succeed to extract lineage within given time limit", e)

    return self


def report_spark_lineage(spark_lineage,
                         k,  # type: Kensu
                         result_schema,
                         output_name):
    # similar like GenericComputedInMemDs.report, but using processRun from spark and no Kensu-Py magic
    from kensu.utils.helpers import extract_ksu_ds_schema
    spark_input_names = []
    for input_ds in spark_lineage.inputs:
        ds, schema = extract_ksu_ds_schema(k, input_ds, report=True, register_orig_data=False)
        input_name = ds.pk.location
        spark_input_names.append(input_name)
        k.name_schema_lineage_dict[input_name] = schema.to_guid()

    # report output (if needed)
    lineage_run = link(input_names=spark_input_names, output_name=output_name)
    lineage_run_id = lineage_run.to_guid()
    # ask spark to publish stats given a lineage-run
    # FIXME: do we need to activate/deactivate it depending on config? but kensupy conf or pyspark conf?
    for input_ds in spark_lineage.inputs:
        input_ds.f_publish_stats(lineage_run_id)


def tagInMemWrapper():
    def tagInMemInner(self,  # type: DataFrame
                      name  # type: str
                      ):
        return tagInMem(self, name)

    return tagInMemInner


def tagCreateSparkDataFrameFromPy(
        self,  # type: DataFrame
        name,  # type: str
        input_names=None  # type: list[str]
):
    try:
        # Get spark session info
        spark = get_spark_from_df(self)
        spark_info = get_process_run_info(spark)
        process = spark_info['process_guid']

        # Creation of an in-mem data source
        location = f'in-memory-data://{process}/{name}'
        in_mem_format = 'in-mem'
        k = KensuProvider().instance()
        ds_pk = DataSourcePK(location=location,
                             physical_location_ref=PhysicalLocationRef(by_pk=k.UNKNOWN_PHYSICAL_LOCATION.pk))
        ds = to_datasource(ds_pk, in_mem_format, location, 'File', name)._report()

        # FIXME: only spark dataframe supported now, i.e. this function must be after spark.createDataFrame()
        fields = get_schema_fields_from_spark_df(spark_df=self)
        schema = Schema(location,
                        pk=SchemaPK(data_source_ref=DataSourceRef(by_guid=ds.to_guid()), fields=fields))._report()
        k.name_schema_lineage_dict[name] = schema.to_guid()

        # report lineage to Kensu between Python inputs and spark.createDataFrame which is not seen by Spark directly
        if input_names:
            link(input_names=input_names, output_name=name)
        else:
            # p.s. if we need mode where in-mem is not reported, would need to get earlier reported lineage
            pass

        # also need to report lineage to Spark JVM,
        # which for now will be simply `name` of this .createDataFrame() in-mem operation
        output_df_tag = f'spark_df_{name}'
        register_manual_lineage(
            spark,
            output_df_tag=output_df_tag,  # p.s. output_df_tag is only used as an ID in Spark agent side, nothing else
            # P.S. or alternatively we could pass over the input_names to Spark,
            #  and then not report any lineage between inputs_name(python) and {spark_dataframe} from within Python
            #  but then the `name` (of this in-memory spark dataframe)  would be not reported to Kensu, so
            #  current solution seems better/more consistent with the rest of this file
            inputs=[
                {
                    'path': location,  # FIXME: will DS name be consistently reported between python and Spark/scala?
                    'format': in_mem_format,
                    'schema': dict([(f.name, f.field_type) for f in fields])
                },
            ]
        )
        output_df = get_df_with_inmem_tag(df=self, df_tag=output_df_tag)
    except Exception as e:
        logging.warning(f"tagCreateSparkDataFrameFromPy encountered an issue", e)
        output_df = self
    return output_df


def tagCreateDataFrameWrapper():
    def tagInMemInner(self,  # type: DataFrame
                      name,  # type: str
                      input_names=None
                      ):
        return tagCreateSparkDataFrameFromPy(self, name=name, input_names=input_names)

    return tagInMemInner


def add_tagInMem_operations():
    DataFrame.tagInMem = tagInMemWrapper()
    DataFrame.tagCreateDataFrame = tagCreateDataFrameWrapper()


def create_publish_for_data_source(name, format, location, schema=None, **kwargs):
    k = KensuProvider().instance()
    ds_pk = DataSourcePK(location=location,
                         physical_location_ref=PhysicalLocationRef(by_pk=k.UNKNOWN_PHYSICAL_LOCATION.pk))

    ds = DataSource(name=name, format=format, categories=[f'logical::{name}'], pk=ds_pk)._report()

    if schema is not None:
        fields = schema
    else:
        fields = [FieldDef('unknown', 'unknown', True)]
    schema = Schema(name, pk=SchemaPK(data_source_ref=DataSourceRef(by_guid=ds.to_guid()), fields=fields))._report()
    k.name_schema_lineage_dict[name] = schema.to_guid()


def create_publish_for_postgres_table(table, location, cur=None):
    format = 'Postgres Table'
    from kensu.psycopg2.pghelpers import get_table_schema
    try:
        if cur:
            SchemaFields = get_table_schema(cur=cur, table_name=table)
            from kensu.client.models import FieldDef
            schema_ = [FieldDef(f['field_name'], f['field_type'], True) for f in SchemaFields]
        else:
            schema_ = None
    except:
        schema_ = None
    create_publish_for_data_source(ds=table, name=location, location=location, format=format, schema=schema_)


def create_publish_for_csv(name, location):
    format = 'csv'
    import pandas as pd
    from kensu.pandas.extractor import KensuPandasSupport
    schema_ = None
    create_publish_for_data_source(ds=name, name=name, location=location, format=format, schema=schema_)


def create_publish_for_sklearn_model(name, location):
    format = 'SKLearn'
    k = KensuProvider().instance()
    ds_pk = DataSourcePK(location=location,
                         physical_location_ref=PhysicalLocationRef(by_pk=k.UNKNOWN_PHYSICAL_LOCATION.pk))
    ds = DataSource(name=name, format=format, categories=[f'logical::{name}'], pk=ds_pk)._report()

    fields = [FieldDef('intercept', 'Numeric', False), FieldDef('coeff', 'Numeric', False)]
    schema = Schema(name, pk=SchemaPK(data_source_ref=DataSourceRef(by_guid=ds.to_guid()), fields=fields))._report()
    k.name_schema_lineage_dict[name] = schema.to_guid()


def get_schema(name):
    # use the lookup table

    k = KensuProvider().instance()
    if name in k.name_schema_lineage_dict:
        return k.name_schema_lineage_dict[name]
    else:
        logging.info(f'Unable to retrieve Kensu GUID for schema {name}')
        return None


def create_lineage(inputs, output):
    data_flow = [SchemaLineageDependencyDef(from_schema_ref=SchemaRef(by_guid=i),
                                            to_schema_ref=SchemaRef(by_guid=output),
                                            # FIXME: or should we report column_data_dependencies=None ?
                                            column_data_dependencies={'unknown': ['unknown']}) for i in inputs]

    # Definition of the process
    if get_spark_session() != None:
        process_guid = get_process_run_info(get_spark_session())['process_guid']
    else:
        k = KensuProvider().instance()
        process_guid = k.process.to_guid()

    lineage = ProcessLineage(name=f'Lineage to {str(output)}',  # FIXME: List inputs too?
                             operation_logic='APPEND',
                             pk=ProcessLineagePK(process_ref=ProcessRef(
                                 by_guid=process_guid),
                                                 data_flow=data_flow))._report()
    return lineage


def link(input_names, output_name):
    # retrieve schemas for inputs
    input_scs = [get_schema(i) for i in input_names]
    # retrieve schemas for outputs
    output_sc = get_schema(output_name)
    # create lineage
    lineage = create_lineage(input_scs, output_sc)._report()

    # Definition of the process run
    if get_spark_session() != None:
        process_run_guid = get_process_run_info(get_spark_session())['process_run_guid']
    else:
        k = KensuProvider().instance()
        process_run_guid = k.process_run.to_guid()

    # create lineage run
    k = KensuProvider().instance()
    lineage_run = LineageRun(LineageRunPK(process_run_ref=ProcessRunRef(by_guid=process_run_guid),
                                          lineage_ref=ProcessLineageRef(by_guid=lineage.to_guid()),
                                          # Should be int/long
                                          timestamp=int(k.timestamp)))
    print(f'reporting lineage_run for {input_names} -> {output_name}. payload={lineage_run}...')
    lineage_run._report()
    return lineage_run
