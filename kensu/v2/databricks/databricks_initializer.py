# Initialization flow is as follows:
# - [x] in  `ipykernel_launcher.py`: call kensu-py pre-init, to monkey-patch the required python packages so it starts tracking
# - [ ]  in ipykernel_launcher.py, notebook metadata in `dbutils` seems unavailable outside of cell - “security” stuff
# when in cell => use kensu-py lazy config retrieval?
#   - python cell calls dbutils -> calls scala -> scala dbutils -> fetch remote conf() -> return to python -> initKensu(remote_conf)
#   - allow_reinit should do it!
# - [ ] implement some reader/writer monkeypatch MVP
# - [ ] improve the way we patch the `ipykernel_launcher.py`

import logging
import inspect
import time

from kensu.client import FieldDef

spark_initialized = False
initialized = False

inputs_read = []

def run_fake_spark_job_to_init(spark):
    from pyspark.sql.types import StringType, IntegerType, StructField, StructType
    data = [('Alice', 25, 'New York'),
            ('Bob', 30, 'London'),
            ('Charlie', 35, 'Sydney')]
    schema = StructType([
        StructField("name", StringType(), True),
        StructField("age", IntegerType(), True),
        StructField("city", StringType(), True)
    ])
    # Convert RDD to DataFrame using the specified schema
    rdd = spark.sparkContext.parallelize(data)
    df = spark.createDataFrame(rdd, schema)
    df.collect()


def init_scala_spark(spark  # type: pyspark.sql.SparkSession
                     ):
    global spark_initialized
    try:
        print("Trying to explicitly init Spark collector")
        from kensu.pyspark.spark_connector import ref_scala_object
        # fixme: this could also check if not initialized already, and skip the job if so
        run_fake_spark_job_to_init(spark)
        # fixme: do I need to call computeDelayedStats to trigger initialization? probably not?
        #  just to wait for long enough
        # FIXME: use iterative waiting which checks if initialized already
        time.sleep(90)
        spark_initialized = True
    except Exception as e:
        print("Trying to explicitly init Spark collector failed: " + str(e))
        # print stacktrace
        import traceback
        traceback.print_exc()


def init_kensu_py(spark):
    global spark_initialized
    try:
        print("Kensu-py initialation started...")
        import os
        # FIXME: use remotely retrieved conf file contents  from scala, so it'd be fully in sync?
        # FIXME: for now, we use the local temp file?
        os.environ["KSU_CONF_FILE"] = "/databricks/driver/kensu_py.conf"
        from kensu.utils.kensu_provider import KensuProvider
        kensu_instance = KensuProvider().initKensu(report_process_info=not spark_initialized, allow_reinit=True)
        print("Kensu-py initialation succeeded.")
    except Exception as e:
        print("Kensu-py initialation failed: " + str(e))
        # print stacktrace
        import traceback
        traceback.print_exc()
    print("end of Kensu-py init code!")


def lazy_init():
    global initialized
    if not initialized:
        from kensu.exp import get_spark_session
        spark = get_spark_session() # FIXME: any better way to get spark variable, gc, global, etc!? cache it?
        # FIXME: init_scala_spark(spark)
        init_kensu_py(spark)
        initialized = True


def monkey_patch_readers_writers():
    # - this function is called from ipykernel_launcher.py ,
    #   but Kensu is not yet fully initialized with notebook details, because they seem not available at that stage
    # - here we monkey patch reader and writer functions in the tracked libraries like:
    #    * pandas
    #    * mlflow
    # - the reader and writer functions will call the lazy_init() function to ensure that Kensu is fully initialized
    monkey_patch_pandas()
    monkey_patch_spark_dataframe()


def patched_to_parquet(wrapped, fn_name, format_name):
    def wrapper(self, *args, **kwargs):
        result = wrapped(self, *args, **kwargs)
        try:
            logging.info(f'KENSU: in {fn_name} - original impl done, trying to lazy init Kensu')
            lazy_init()
            logging.info(f'KENSU: in {fn_name}, starting Kensu reporting')
            path = str(kwargs.get('path', None) or args[0])
            logging.info(f'KENSU: in {fn_name}, extracted OUTPUT path: {path} , format: {format_name}')
            # FIXME: get qualified path and report to Kensu
            qualified_path = path
            from kensu.exp import create_publish_for_data_source, link
            # import pandas as pd
            from kensu.pandas.extractor import KensuPandasSupport
            schema_fields = KensuPandasSupport().extract_schema_fields(self) + [FieldDef('unknown', 'unknown', True)]
            ds_name = qualified_path
            create_publish_for_data_source(ds=ds_name, name=qualified_path, location=qualified_path, format=format_name, schema=schema_fields)
            global inputs_read
            link(list(set(inputs_read)), ds_name)
            logging.info(f'KENSU: in {fn_name}, done reporting')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue in {}: {}".format(fn_name, traceback.format_exc()))
        return result

    wrapper.__doc__ = wrapped.__doc__
    wrapped.__signature__ = inspect.signature(wrapped)
    return wrapper


def patched_read_parquet(wrapped, fn_name, format_name):
    def wrapper(*args, **kwargs):
        result = wrapped(*args, **kwargs)
        try:
            logging.info(f'KENSU: in {fn_name} - original impl done, trying to lazy init Kensu')
            lazy_init()
            logging.info(f'KENSU: in {fn_name}, starting Kensu reporting')
            path = str(kwargs.get('path', None) or args[0])
            logging.info(f'KENSU: in {fn_name}, extracted INPUT path: {path} , format: {format_name}')
            # FIXME: get qualified path and report to Kensu
            qualified_path = path
            from kensu.exp import create_publish_for_data_source
            # import pandas as pd
            from kensu.pandas.extractor import KensuPandasSupport
            schema_fields = KensuPandasSupport().extract_schema_fields(result) + [FieldDef('unknown', 'unknown', True)]
            ds_name = qualified_path
            create_publish_for_data_source(ds=ds_name, name=qualified_path, location=qualified_path, format=format_name, schema=schema_fields)
            global inputs_read
            inputs_read.append(ds_name)
            logging.info(f'KENSU: in {fn_name}, done reporting')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue in {}: {}".format(fn_name, traceback.format_exc()))
        return result

    wrapper.__doc__ = wrapped.__doc__
    wrapped.__signature__ = inspect.signature(wrapped)
    return wrapper


def monkey_patch_pandas():
    # FIXME: try/catch if not installed
    import pandas as pd
    from pandas import DataFrame
    try:
        setattr(pd, 'read_parquet', patched_read_parquet(pd.read_parquet, 'read_parquet', 'parquet'))
    except Exception as e:
        print("Kensu-py pandas patching read_parquet failed: " + str(e))
        # print stacktrace
        import traceback
        traceback.print_exc()

    # df: pd.DataFrame = pd.DataFrame()
    #     def to_parquet(
    #         self,
    #         path: FilePath | WriteBuffer[bytes] | None = None,
    #         engine: Literal["auto", "pyarrow", "fastparquet"] = "auto",
    #         compression: str | None = "snappy",
    #         index: bool | None = None,
    #         partition_cols: list[str] | None = None,
    #         storage_options: StorageOptions | None = None,
    #         **kwargs,
    #     ) -> bytes | None:
    try:
        setattr(DataFrame, 'to_parquet', patched_to_parquet(pd.DataFrame.to_parquet, 'to_parquet', 'parquet'))
    except Exception as e:
        print("Kensu-py pandas patching DataFrame.to_parquet failed: " + str(e))
        # print stacktrace
        import traceback
        traceback.print_exc()


toPandas_idx = 0


def patched_to_df_toPandas(wrapped, fn_name, format_name):
    def wrapper(self, *args, **kwargs):
        # call original .toPandas() from Spark
        result = wrapped(self, *args, **kwargs)
        try:
            logging.info(f'KENSU: in {fn_name} - original impl done, trying to lazy init Kensu')
            lazy_init()
            spark_df = self
            global toPandas_idx
            global inputs_read
            toPandas_idx += 1
            toPandas_in_mem_name = f'spark_df.toPandas{toPandas_idx}'  # FIXME: do we have a better way of naming - FIXME: add process-name at least!!!
            # retrieve lineage, and store via random name
            spark_df.tagInMem(name=toPandas_in_mem_name)
            inputs_read.append(toPandas_in_mem_name)
            logging.info(f'KENSU: in {fn_name}, done reporting')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue in {}: {}".format(fn_name, traceback.format_exc()))
        return result

    wrapper.__doc__ = wrapped.__doc__
    wrapped.__signature__ = inspect.signature(wrapped)
    return wrapper


def monkey_patch_spark_dataframe():
    from kensu.exp import add_tagInMem_operations
    add_tagInMem_operations()  # this adds spark_df.tagInMem()
    from pyspark.sql import DataFrame
    # from pyspark.sql import SparkSession
    # this replaces .toPandas() by this: spark_df.tagInMem(name="spark_df.toPandas123").toPandas()
    try:
        setattr(DataFrame, 'toPandas', patched_to_df_toPandas(DataFrame.toPandas, 'pyspark.sql.DataFrame.toPandas', 'Spark.toPandas()'))
    except Exception as e:
        print("Kensu-py patching Spark DataFrame.toPandas() failed: " + str(e))
        # print stacktrace
        import traceback
        traceback.print_exc()

    # TODO: spark.createDataFrame(pandas_df).tagCreateDataFrame('created_df',input_names = None)