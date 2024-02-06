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

spark_initialized = False
initialized = False

inputs_read = []

def init_scala_spark(spark  # type: pyspark.sql.SparkSession
                     ):
    global spark_initialized
    try:
        print("Trying to explicitly init Spark collector")
        from kensu.pyspark.spark_connector import ref_scala_object
        # entry_point seems JVM object, so we can use it to get JVM
        #sc = spark.sparkContext
        jvm = spark.sparkContext._jvm
        client_class = ref_scala_object(jvm, "org.apache.spark.sql.kensu.KensuZeroCodeListener")
        client_class.explicitlyInitKensuForAliveSession(spark._jsparkSession)  # fixme: this should also check if not initialized already
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
        # FIXME: test patching pandas
        import pandas as pd
        pd.kensu = 'Kensu'
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
        init_scala_spark(spark)
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
            schema_fields = KensuPandasSupport().extract_schema_fields(self)
            ds_name = qualified_path
            create_publish_for_data_source(ds=ds_name, name=qualified_path, location=qualified_path, format=format_name, schema=schema_fields)
            global inputs_read
            link(inputs_read, ds_name)
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
            schema_fields = KensuPandasSupport().extract_schema_fields(result)
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

