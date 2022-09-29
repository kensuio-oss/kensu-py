import logging
from kensu.utils.helpers import extract_config_property, get_conf_path

# This function takes the fully classified object name, say: <package>.<name>.
# Returns the static object instance on the heap
def ref_scala_object(jvm, object_name):
    reflection = False
    if reflection:
      clazz = jvm.java.lang.Class.forName(object_name + "$")
      ff = clazz.getDeclaredField("MODULE$")
      o = ff.get(None)
      return o
    else:
      # it seems in paid databricks (sometimes) reflection do not work...
      class_name_parts = (object_name + "$.MODULE$").split(".")
      o = jvm
      for p in class_name_parts:
        o = getattr(o, p)
      return o

def wait_for_dam_completion(spark, dam_wait_timeout_secs):
    sc = spark.sparkContext
    jvm = sc._jvm
    # call DamClientActorSystem.destroyActorSystem(actorSysTimeout: Duration = actorSysTimeout, futuresTimeout: Duration = futuresTimeout)
    dam_client_class = ref_scala_object(jvm, "io.kensu.third.integration.spline.DamClientActorSystem")
    duration_class = ref_scala_object(jvm, "scala.concurrent.duration.Duration")
    duration_30s = duration_class.apply(30, "second")
    duration_wait_timeout = duration_class.apply(dam_wait_timeout_secs, "second")
    return dam_client_class.destroyActorSystem(duration_30s, duration_wait_timeout)


def patched_spark_stop(wrapped, dam_wait_timeout_secs):
    def wrapper(self):
        try:
            logging.info('DAM: in spark.stop, waiting for DAM reporting to finish')
            wait_for_dam_completion(self, dam_wait_timeout_secs)
            logging.info('DAM: in spark.stop, waiting for DAM done, stopping spark context')
        except:
            import traceback
            logging.info("unexpected DAM issue: {}".format(traceback.format_exc()))
        result = wrapped(self)
        logging.info('DAM: in spark.stop, spark context stopped')
        return result

    wrapper.__doc__ = wrapped.__doc__
    return wrapper


def rand_str():
    import random
    import string
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(8))


def ensure_dir_exists(path):
    import os
    import errno
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def patched_spark_createDataFrame_pandas(wrapped, pandas_to_spark_df_via_tmp_file, tmp_dir=None):
    def wrapper(self, data, *args, **kwargs):
        try:
            logging.info('Kensu: before calling spark.createDataFrame')
            from kensu import pandas as ksu_pandas
            if isinstance(data, ksu_pandas.data_frame.DataFrame):
                logging.info('Kensu: replacing kensu.pandas.data_frame.DataFrame wrapper into a original pandas...')
                if not pandas_to_spark_df_via_tmp_file:
                    #  just unwrap the Kensu wrapper, so spark at least works
                    data = data.get_df() # type: pandas.DataFrame
                    # to ensure old-style spark.createDataFrame works
                    # even if passed extra kwarg when KSU tmp file is disabled
                    # we delete the key ksu_tmp_file_prefix if it exists
                    kwargs.pop('ksu_tmp_file_prefix', None)
                else:
                    # given `spark_df=spark.createDataFrame(pandas_df)`, it would be replaced into:
                    # res.to_parquet('/tmp/pandas_to_spark/some_tmp_file.parquet', index=False)
                    # spark_df = spark.read.parquet('file:/tmp/pandas_to_spark/some_tmp_file.parquet')
                    tmp_file_prefix = kwargs.get('ksu_tmp_file_prefix') or 'pandasdf_to_spark'
                    tmp_file_name = tmp_file_prefix + '-' + rand_str()
                    import os
                    # create a unique dir with unique file, so both LDS and file are unique - thus do not clash in Kensu
                    final_tmp_dir = os.path.join(tmp_dir, tmp_file_name)
                    ensure_dir_exists(final_tmp_dir)
                    tmp_file_path = os.path.join(final_tmp_dir, tmp_file_name + '.parquet')
                    # write to a temp file locally with pandas, using Kensu wrapper to capture the lineage
                    abs_tmp_file_name = os.path.abspath(tmp_file_path)
                    logging.info('Kensu: spark.createDataFrame(pandas_df): Kensu will write pandas_df to a temp file - '+ abs_tmp_file_name)
                    data.to_parquet(abs_tmp_file_name, index=False)
                    # here do not call the Spark's original implementation of spark.createDataFrame(),
                    # and just read tmp file with spark, so we'd have the lineage
                    spark_temp_file_path = 'file:' + abs_tmp_file_name
                    logging.info('Kensu: spark.createDataFrame(pandas_df): Kensu will read to a temp file in spark - ' + spark_temp_file_path)
                    spark_df = self.read.parquet(spark_temp_file_path)
                    return spark_df
            logging.info('Kensu: done modifying arguments to spark.createDataFrame')
        except:
            import traceback
            logging.info("unexpected DAM issue: {}".format(traceback.format_exc()))
        result = wrapped(self, data, *args, **kwargs)
        logging.info('Kensu: end of spark.createDataFrame')
        return result

    wrapper.__doc__ = wrapped.__doc__
    return wrapper


def patched_dataframe_write(wrapped):
    def wrapper(self):
        try:
            logging.info('DAM: in patched DataFrame.write, marking DataFrame as cached')
            from pyspark.sql import DataFrameWriter
            result = DataFrameWriter(self.cache())
            logging.info('DAM: in patched DataFrame.write, returning result')
        except:
            import traceback
            logging.info("DAM: unexpected issue in DataFrame.write: {}".format(traceback.format_exc()))
            from pyspark.sql import DataFrameWriter
            result = DataFrameWriter(self.cache())
        return result

    return property(wrapper)


def patched_dataframe_toPandas(wrapped):
    def wrapper(self):
        try:
            logging.info('DAM: in patched DataFrame.toPandas()')
            result = wrapped(self)
            logging.info('DAM: in patched DataFrame.toPandas(), returning result')
        except:
            import traceback
            logging.info("DAM: unexpected issue in DataFrame.toPandas(): {}".format(traceback.format_exc()))
            result = wrapped(self)
        return result

    return wrapper


def get_jvm_from_df(dataframe, # type: DataFrame
                    ):
    sql_context = dataframe.sql_ctx # type: SQLContext
    spark = sql_context.sparkSession
    return spark.sparkContext._jvm


def call_df_as_dam_datasource(df,  # type: DataFrame
                              location, datasource_type,
                              name=None, # type: str
                              logical_name=None # type: str
                             ):
    jvm = get_jvm_from_df(df)
    w = jvm.io.kensu.dam.lineage.spark.lineage.Implicits.SparkDataFrameDAMWrapper(df._jdf)
    return w.reportAsDamDatasource(location, datasource_type, jvm.scala.Option.apply(name), jvm.scala.Option.apply(logical_name))


def call_df_as_dam_jdbc_datasource(df,  # type: DataFrame
                                  dbType,  # type: str
                                  schemaName, # type: str
                                  tableName, # type: str
                                  maybeDatabaseName, # type: str
                                  name=None, # type: str
                                  logical_name=None # type: str
                                  ):
    jvm = get_jvm_from_df(df)
    w = jvm.io.kensu.dam.lineage.spark.lineage.Implicits.SparkDataFrameDAMWrapper(df._jdf)
    return w.reportAsDamJdbcDatasource(dbType, schemaName, tableName, jvm.scala.Option.apply(maybeDatabaseName), jvm.scala.Option.apply(name), jvm.scala.Option.apply(logical_name))


def do_disable_spark_writes(spark):
    """
    Disables spark writes, but keeps DAM reporting.
    Affects only the writes which use DataFrameWriter - dataFrame.write.someMethod(), including .csv(), .save(), .saveAsTable().

    Note: This function MUST be run before first spark write, otherwise spark writes will not be disabled!
    """
    logging.info('DAM disabling df.write')
    sc = spark.sparkContext
    jvm = sc._jvm
    spark_writes_disabler = ref_scala_object(jvm, "io.kensu.third.integration.spark.nowrites.SparkWritesDisabler")
    spark_writes_disabler.disableSparkWrites()
    logging.info('DAM disabling df.write done')


def set_fake_timestamp(spark, mocked_timestamp):
    """
    Sets a fake timestamp to be reported to DAM
    """
    logging.info('KENSU overriding execution_timestamp starting')
    sc = spark.sparkContext
    jvm = sc._jvm
    spark_writes_disabler = ref_scala_object(jvm, "io.kensu.third.integration.TimeUtils")
    force_override = False
    spark_writes_disabler.setMockedTime(int(mocked_timestamp), force_override)
    logging.info('KENSU overriding execution_timestamp done')


def add_ds_path_sanitizer(spark, search_str, replacement_str):
    """
    Sets a fake timestamp to be reported to DAM
    """
    logging.info('DAM add_ds_path_sanitizer starting')
    sc = spark.sparkContext
    jvm = sc._jvm
    spark_writes_disabler = ref_scala_object(jvm, "io.kensu.third.integration.DataSourceConv")
    spark_writes_disabler.addDsPathSanitizer(search_str, replacement_str)
    logging.info('DAM add_ds_path_sanitizer done')

def report_df_as_dam_datasource():
    def report_as_dam_datasource(self, # type: DataFrame
                                 location, # type: str
                                 datasource_type=None, # type: str
                                 name=None, # type: str
                                 logical_name=None # type: str
                                 ):
        try:
            logging.info('DAM: in df.report_as_dam_datasource')
            call_df_as_dam_datasource(self, location, datasource_type or 'in-memory-dataframe', name, logical_name)
            logging.info('DAM: df.report_as_dam_datasource started in background')
        except:
            import traceback
            logging.info("unexpected DAM issue: {}".format(traceback.format_exc()))
        return self
    return report_as_dam_datasource


def report_df_as_dam_jdbc_datasource():
    def report_as_dam_jdbc_datasource(self,  # type: DataFrame
                                      db_type,  # type: str
                                      schema_name,  # type: str
                                      table_name,  # type: str
                                      maybe_db_name=None,  # type: str
                                      name=None, # type: str
                                      logical_name=None # type: str
                                      ):
        try:
            logging.info('DAM: in df.report_as_dam_jdbc_datasource')
            call_df_as_dam_jdbc_datasource(self, db_type, schema_name, table_name, maybe_db_name, name, logical_name)
            logging.info('DAM: df.report_as_dam_jdbc_datasource started in background')
        except:
            import traceback
            logging.info("unexpected DAM issue: {}".format(traceback.format_exc()))
        return self
    return report_as_dam_jdbc_datasource


def report_df_as_kpi():
    def report_as_kpi(self,  # type: DataFrame
                      name,  # type: str
                      logical_name=None,  # type: str
                      datasource_type="Business metric (KPI)" # type: str
                      ):
        try:
            logging.info('DAM: in df.report_as_kpi')
            jvm = get_jvm_from_df(self)
            w = jvm.io.kensu.dam.lineage.spark.lineage.Implicits.SparkDataFrameDAMWrapper(self._jdf)
            w.reportAsKPI(name, logical_name or name, datasource_type)
            logging.info('DAM: df.report_as_kpi started in background')
        except:
            import traceback
            logging.info("unexpected DAM issue: {}".format(traceback.format_exc()))
        return self
    return report_as_kpi


def patch_dam_df_helpers():
    try:
        logging.info('Adding DataFrame.report_as_dam_datasource')
        from pyspark.sql import DataFrame
        DataFrame.report_as_dam_datasource = report_df_as_dam_datasource()
        logging.info('done adding DataFrame.report_as_dam_datasource')
    except:
        import traceback
        logging.info("unexpected issue when patching DataFrame.report_as_dam_datasource: {}".format(traceback.format_exc()))
    try:
        logging.info('Adding DataFrame.report_as_dam_jdbc_datasource')
        from pyspark.sql import DataFrame
        DataFrame.report_as_dam_jdbc_datasource = report_df_as_dam_jdbc_datasource()
        logging.info('done adding DataFrame.report_as_dam_jdbc_datasource')
    except:
        import traceback
        logging.info("unexpected issue when patching DataFrame.report_as_dam_jdbc_datasource: {}".format(traceback.format_exc()))
    try:
        logging.info('Adding DataFrame.report_as_kpi')
        from pyspark.sql import DataFrame
        DataFrame.report_as_kpi = report_df_as_kpi()
        logging.info('done adding DataFrame.report_as_kpi')
    except:
        import traceback
        logging.info("unexpected issue when patching DataFrame.report_as_kpi: {}".format(traceback.format_exc()))


def join_paths(maybe_directory, # type: str
               file # type: str
               ):
    if maybe_directory is not None and maybe_directory.strip():
        import os
        return os.path.join(maybe_directory, file)
    else:
        return file


def convert_naming_rules(rules # type: list[str]
                         ):
    # a rule looks like this: dam-spline-persistence/hive-query-results->>File
    return list(["{}->>{}".format(matcher, formatter) for (matcher, formatter) in rules])


def scala_ds_and_schema_to_py(dam, ds, schema):
    from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema
    from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
    pl_ref = dam.UNKNOWN_PHYSICAL_LOCATION.to_ref()
    py_ds = DataSource(name=ds.name(),
                       format=ds.format(),
                       categories=list(ds.categories()),
                       pk=DataSourcePK(location=ds.pk().location(), physical_location_ref=pl_ref))

    # schema
    fields = [
        FieldDef(name=f.name(), field_type=f.fieldType(), nullable=f.nullable())
        for f in schema.fields()
    ]
    py_schema = Schema(
        name=schema.name(),
        pk=SchemaPK(py_ds.to_ref(),
                    fields=fields))

    def f_publish_stats(lineage_run_id):
        schema.attachStatsTo(lineage_run_id)

    def f_get_stats():
        # ******************************************************************************************
        # WARNING : Do not return anything else than None, because f_publish_stats is preferred giving the responsibility
        # to Spark to send the data stats only when it's available (when computation inside scala Future is completed)
        # ******************************************************************************************
        return None
    return KensuDatasourceAndSchema(ksu_ds=py_ds, ksu_schema=py_schema, f_get_stats=f_get_stats, f_publish_stats = f_publish_stats)


def j2py_dict_of_lists(jdict):
    r = {}
    for k, jlist in jdict.items():
        r[k] = list(jlist)
    return r


def get_inputs_lineage_fn(dam, df):
    jvm = get_jvm_from_df(df)
    # call def fetchToPandasReport(
    #     df: DataFrame,
    #     name: String = UUID.randomUUID().toString,
    #     logicalName: Option[String] = None,
    #     datasourceType: String = InternalDatasourceTags.TAG_INPUT_LINEAGE_ONLY,
    #     timeout: Duration
    #   )
    dam_client_class = ref_scala_object(jvm, "io.kensu.third.integration.dataconversions.SparkToPandasConvTracker")
    duration_300s =  ref_scala_object(jvm, "scala.concurrent.duration.Duration").apply(300, "second")
    # FIXME: it should NOT wait for datasts -> check
    import uuid
    virtual_ds_name = str(uuid.uuid1())
    no_logical_name = jvm.scala.Option.apply(None)
    lineage_from_scala = dam_client_class.fetchToPandasReport(
        df._jdf,
        virtual_ds_name,
        no_logical_name,
        # ds_type,
        duration_300s
    )
    # logging.info('lineage_from_scala:', lineage_from_scala)
    df.lineage_from_scala = lineage_from_scala
    from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs, ExtDependencyEntry
    # case class SimpleInputDsSchemaAndLineage(
    #   ds: DataSource,
    #   schema: Schema,
    #   lineage: Map[String, Seq[String]]
    # )
    #
    # case class SimpleInputsLineageReport(
    #   lineage: Seq[SimpleInputDsSchemaAndLineage]
    # )
    lineage_info = [
        ExtDependencyEntry(
            input_ds=scala_ds_and_schema_to_py(dam, e.ds(), e.schema()),
            lineage=j2py_dict_of_lists(e.lineage())
        ) for e in lineage_from_scala.lineage()
    ]
    logging.info('lineage_info:', lineage_info)
    return GenericComputedInMemDs(inputs=list([x.input_ds for x in lineage_info]), lineage=lineage_info)


"""
Assuming Datasource name is /a/b/c.ext
Allowed values for parameters:
- data_source_naming_strategy:
  * None (default) - (file) name of DS if use_short_datasource_names else full_path
  * 'File' - c.ext
  * 'LastTwoFoldersAndFile' - a/b/c.ext
  * 'LastFolderAndFile' - b/c.ext
  * 'LastFolder' - b
  * 'PathBasedRule' - use data_source_naming_strategy_rules
- logical_data_source_naming_strategy_rules:
  * None (default) - do not set logical datasource
  * 'File' - c.ext
  * 'LastTwoFoldersAndFile' - a/b/c.ext
  * 'LastFolderAndFile' - b/c.ext
  * 'LastFolder' - b
  * 'PathBasedRule' - use logical_datasource_name_strategy_rules
- data_source_naming_strategy_rules or logical_data_source_naming_strategy_rules:
  * pass a list of tuples (string_matcher, naming_strategy) like this:
    [("features_with_attrition_horizon_label", "File"),
     ("attri_pro_risk_indicator_disabled_3", "LastTwoFoldersAndFile"),
     # default - empty string matches everything
     ("", "LastFolderAndFile")]
- missing_column_lineage_strategy:
    * 'CaseInsensitiveColumnNameMatcherStrat'
    * 'CaseSensitiveColumnNameMatcherStrat'
    * 'AllToAllLineageStrat'
    * 'OutFieldEndsWithInFieldNameLineageStrat'
    * 'OutFieldStartsWithInFieldNameLineageStrat'
"""
def init_kensu_spark(
        spark_session=None,  # Must stay first as mostly this is the only argument passed
        ingestion_url=None,
        ingestion_token=None,
        report_to_file=None,
        is_dam_tracking_enabled=True,
        logs_dir_path=None,
        offline_file_name=None,
        process_name=None,
        process_run_name=None,
        code_location=None,
        code_version=None,
        user_name=None,
        enable_entity_compaction=None,
        allow_invalid_ssl_certificates=None,
        compute_stats=None,
        compute_input_stats=None,
        compute_output_stats=None,
        input_stats_for_only_used_columns=None,
        input_stats_keep_filters=None,
        input_stats_compute_quantiles=None,
        input_stats_cache_bypath=None,
        input_stats_coalesce_enabled=None,
        input_stats_coalesce_workers=None,
        output_stats_compute_quantiles=None,
        output_stats_cache_bypath=None,
        output_stats_coalesce_enabled=None,
        output_stats_coalesce_workers=None,
        cache_output_for_stats=None,
        shorten_data_source_names=None,
        shutdown_timeout_sec=None,
        enable_debugging=None,
        debugging_log_level=None,
        data_source_naming_strategy=None,
        data_source_naming_strategy_rules=None,
        logical_data_source_naming_strategy=None,
        logical_data_source_naming_strategy_rules=None,
        missing_column_lineage_strategy=None,
        debugging_include_spark_logs=None,
        patch_spark_data_frame=None,
        disable_spark_writes=None,
        environment=None,
        execution_timestamp=None,
        project_name=None,  # type: list[str]
        h2o_support=None,
        h2o_create_virtual_training_datasource=None,
        patch_pandas_conversions=None,
        pandas_to_spark_df_via_tmp_file=None,
        pandas_to_spark_tmp_dir=None,
        **kwargs
):
    if is_dam_tracking_enabled:
        logging.info("Initializing DAM...")
        jvm = spark_session.sparkContext._jvm

        from configparser import ConfigParser, ExtendedInterpolation
        config = ConfigParser(interpolation=ExtendedInterpolation())
        conf_path = get_conf_path("conf.ini")
        try:
            config.read(conf_path)
        except:
            logging.warning(f"Cannot load config from file `%s`" % (conf_path))

        kensu_conf = config['kensu'] if config.has_section('kensu') else config['DEFAULT']

        ingestion_url = extract_config_property('ingestion_url',None,ingestion_url, kw=kwargs, conf=kensu_conf)
        ingestion_token = extract_config_property('ingestion_token',None,ingestion_token, kw=kwargs, conf=kensu_conf)
        report_to_file = extract_config_property('report_to_file', False, report_to_file, kw=kwargs, conf=kensu_conf, tpe=bool)
        logs_dir_path = extract_config_property('logs_dir_path', None, logs_dir_path, kw=kwargs, conf=kensu_conf)
        offline_file_name = extract_config_property('offline_file_name', 'dam-offline.log', offline_file_name, kw=kwargs, conf=kensu_conf)

        shutdown_timeout_sec = extract_config_property('shutdown_timeout_sec', 10 * 60, shutdown_timeout_sec, kw=kwargs, conf=kensu_conf, tpe=int)
        # TODO api_verify_ssl ?
        allow_invalid_ssl_certificates = extract_config_property('api_verify_ssl',False,allow_invalid_ssl_certificates, kw=kwargs, conf=kensu_conf, tpe=bool)
        enable_debugging = extract_config_property('enable_debugging', False, enable_debugging, kw=kwargs, conf=kensu_conf, tpe=bool)
        debugging_log_level = extract_config_property('debugging_log_level', 'INFO', debugging_log_level, kw=kwargs, conf=kensu_conf)
        debugging_include_spark_logs = extract_config_property('debugging_include_spark_logs', False, debugging_include_spark_logs, kw=kwargs, conf=kensu_conf, tpe=bool)

        process_name = extract_config_property('process_name', None, process_name, kw=kwargs, conf=kensu_conf)
        process_run_name = extract_config_property('process_run_name', None, process_run_name, kw=kwargs, conf=kensu_conf)
        code_location = extract_config_property('code_location', None, code_location, kw=kwargs, conf=kensu_conf)
        code_version = extract_config_property('code_version', None, code_version, kw=kwargs, conf=kensu_conf)
        user_name = extract_config_property('user_name', None, user_name, kw=kwargs, conf=kensu_conf)
        enable_entity_compaction = extract_config_property('enable_entity_compaction',True,enable_entity_compaction, kw=kwargs, conf=kensu_conf, tpe=bool)
        environment = extract_config_property('environment',None,environment, kw=kwargs, conf=kensu_conf)
        project_name = extract_config_property('project_name', None, project_name, kw=kwargs, conf=kensu_conf, tpe=list)  # type: list[str]
        execution_timestamp = extract_config_property('execution_timestamp', None, execution_timestamp, kw=kwargs, conf=kensu_conf, tpe=int)

        compute_stats = extract_config_property('compute_stats', True, compute_stats, kw=kwargs, conf=kensu_conf, tpe=bool)
        compute_input_stats = extract_config_property('compute_input_stats', True, compute_input_stats, kw=kwargs, conf=kensu_conf, tpe=bool)
        compute_output_stats = extract_config_property('compute_output_stats', True, compute_output_stats, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_for_only_used_columns = extract_config_property('input_stats_for_only_used_columns',True,input_stats_for_only_used_columns, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_keep_filters = extract_config_property('input_stats_keep_filters',True,input_stats_keep_filters, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_compute_quantiles = extract_config_property('input_stats_compute_quantiles',False,input_stats_compute_quantiles, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_cache_bypath = extract_config_property('input_stats_cache_bypath',True,input_stats_cache_bypath, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_coalesce_enabled = extract_config_property('input_stats_coalesce_enabled',True,input_stats_coalesce_enabled, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_coalesce_workers = extract_config_property('input_stats_coalesce_workers',1,input_stats_coalesce_workers, kw=kwargs, conf=kensu_conf, tpe=int)
        output_stats_compute_quantiles = extract_config_property('output_stats_compute_quantiles',False,output_stats_compute_quantiles, kw=kwargs, conf=kensu_conf, tpe=bool)
        output_stats_cache_bypath = extract_config_property('output_stats_cache_bypath',False,output_stats_cache_bypath, kw=kwargs, conf=kensu_conf, tpe=bool)
        output_stats_coalesce_enabled = extract_config_property('output_stats_coalesce_enabled',False,output_stats_coalesce_enabled, kw=kwargs, conf=kensu_conf, tpe=bool)
        output_stats_coalesce_workers = extract_config_property('output_stats_coalesce_workers',100,output_stats_coalesce_workers, kw=kwargs, conf=kensu_conf, tpe=int)
        cache_output_for_stats = extract_config_property('cache_output_for_stats', False, cache_output_for_stats, kw=kwargs, conf=kensu_conf, tpe=bool)

        shorten_data_source_names = extract_config_property('shorten_data_source_names', True, shorten_data_source_names, kw=kwargs, conf=kensu_conf, tpe=bool)
        data_source_naming_strategy = extract_config_property('data_source_naming_strategy', None, data_source_naming_strategy, kw=kwargs, conf=kensu_conf)
        data_source_naming_strategy_rules = extract_config_property('data_source_naming_strategy_rules', None, data_source_naming_strategy_rules, kw=kwargs, conf=kensu_conf)
        logical_data_source_naming_strategy = extract_config_property('logical_data_source_naming_strategy', None, logical_data_source_naming_strategy, kw=kwargs, conf=kensu_conf)
        logical_data_source_naming_strategy_rules = extract_config_property('logical_data_source_naming_strategy_rules', None, logical_data_source_naming_strategy_rules, kw=kwargs, conf=kensu_conf)

        missing_column_lineage_strategy = extract_config_property('missing_column_lineage_strategy', None, missing_column_lineage_strategy, kw=kwargs, conf=kensu_conf)

        disable_spark_writes = extract_config_property('disable_spark_writes',False,disable_spark_writes, kw=kwargs, conf=kensu_conf, tpe=bool)

        h2o_support = extract_config_property('h2o_support', False, h2o_support, kw=kwargs, conf=kensu_conf, tpe=bool)
        h2o_create_virtual_training_datasource = extract_config_property('h2o_create_virtual_training_datasource',True,h2o_create_virtual_training_datasource, kw=kwargs, conf=kensu_conf, tpe=bool)

        patch_spark_data_frame = extract_config_property('patch_spark_data_frame', True, patch_spark_data_frame, kw=kwargs, conf=kensu_conf, tpe=bool)

        patch_pandas_conversions = extract_config_property('patch_pandas_conversions', True, patch_pandas_conversions, kw=kwargs, conf=kensu_conf, tpe=bool)
        pandas_to_spark_df_via_tmp_file = extract_config_property('pandas_to_spark_df_via_tmp_file',True,pandas_to_spark_df_via_tmp_file, kw=kwargs, conf=kensu_conf, tpe=bool)
        pandas_to_spark_tmp_dir = extract_config_property('pandas_to_spark_tmp_dir','/tmp/spark-to-pandas-tmp',pandas_to_spark_tmp_dir, kw=kwargs, conf=kensu_conf)

        try:
            # Not initializing ML trackers yet
            # injected_classes = jvm.io.kensu.third.integration.spark.model.DamModelPublisher.activate().toString()
            ###  Get notebook name ...
            #### see https://github.com/jupyter/notebook/issues/1000#issuecomment-359875246
            import json
            import os.path
            import re
            import requests
            try:  # Python 3
                from urllib.parse import urljoin
            except ImportError:  # Python 2
                from urlparse import urljoin

            def get_notebook_name():
                """
                Return the full path of the jupyter notebook.
                """
                try:  # Python 3
                    from notebook.notebookapp import list_running_servers
                except ImportError:  # Python 2
                    try:
                        import warnings
                        from IPython.utils.shimmodule import ShimWarning
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", category=ShimWarning)
                            from IPython.html.notebookapp import list_running_servers
                    except ImportError:  # Probably pyspark script is run without IPython/Jupyter
                        if not process_name:
                            logging.warning('WARN Unable to automatically extract Jupyter/pyspark notebook name (did you run it without jupyter?)')
                        return ['', process_name or 'Unknown pyspark filename']
                try:
                    import ipykernel
                    kernel_id = re.search('kernel-(.*).json',
                                          ipykernel.connect.get_connection_file()).group(1)
                    servers = list_running_servers()
                    for ss in servers:
                        response = requests.get(urljoin(ss['url'], 'api/sessions'),
                                                params={'token': ss.get('token', '')})
                        for nn in json.loads(response.text):
                            if nn['kernel']['id'] == kernel_id:
                                server = ss
                                notebooks_path = server['notebook_dir']
                                return [notebooks_path, nn['notebook']['path']]
                except Exception as e:
                    if not process_name:
                        logging.warning('WARN Unable to automatically extract pyspark notebook name')
                    return ['', process_name or 'Unknown pyspark filename']

            notebooks_path, notebook_name = get_notebook_name()
            logging.info("Notebook name " + notebook_name)

            ### Configuration for tracker
            global dam_url
            dam_url = os.environ.get("DAM_INGESTION_URL") or ingestion_url

            damIngestionUrl = jvm.scala.Option.apply(dam_url)
            t2 = jvm.scala.Tuple2
            providerClassName = t2("dam.activity.spark.environnement.provider", "io.kensu.dam.lineage.spark.lineage.DefaultSparkEnvironnementProvider")

            ### How to get GIT info here?
            #         explicit_code_repo=None,
            #         explicit_code_version=None,
            #         explicit_code_maintainers=None,
            #         explicit_lauched_by_user=None,
            code_repo_name = code_location or os.environ.get("DAM_CODE_REPOSITORY", "Jupyter-Notebook:spark-" + spark_session.version + "::" + notebooks_path)
            repository = t2("dam.activity.code.repository", code_repo_name)
            from datetime import datetime
            d = datetime.now()

            code_version_value = code_version or os.environ.get("DAM_CODE_VERSION", notebook_name + "::" + str(d))
            version = t2("dam.activity.code.version", code_version_value)

            global dam_version
            dam_version = code_version_value
            user = t2("dam.activity.user", user_name)

            organization = t2("dam.activity.organization", "Unknown")  # TODO this is not used by Scala side

            properties = jvm.scala.collection.mutable.HashSet()

            def add_prop(name, value):
                if value is not None:
                    properties.add(t2(name, value))

            properties.add(providerClassName)
            properties.add(repository)
            properties.add(version)
            properties.add(user)
            properties.add(organization)
            if ingestion_token:
                properties.add(t2("dam.ingestion.auth.token", ingestion_token))
            if report_to_file is not None:
                properties.add(t2("dam.ingestion.is_offline", report_to_file))
            if offline_file_name:
                properties.add(t2("dam.ingestion.offline.file", join_paths(logs_dir_path, offline_file_name)))
            if allow_invalid_ssl_certificates is not None:
                properties.add(t2("dam.ingestion.ignore.ssl.cert", allow_invalid_ssl_certificates))
            if enable_entity_compaction is not None:
                properties.add(t2("dam.ingestion.entity.compaction", enable_entity_compaction))

            if compute_stats is not None:
                properties.add(t2("dam.spark.data_stats.enabled", compute_stats))
            if compute_input_stats is not None:
                properties.add(t2("dam.spark.data_stats.input.enabled", compute_input_stats))
            if compute_input_stats is not None:
                properties.add(t2("dam.spark.data_stats.output.enabled", compute_input_stats))
            if input_stats_for_only_used_columns:
                properties.add(t2("dam.spark.data_stats.input.only_used_in_lineage", input_stats_for_only_used_columns))
            if input_stats_keep_filters is not None:
                properties.add(t2("dam.spark.data_stats.input.keep_filters", input_stats_keep_filters))

            add_prop("dam.spark.data_stats.input.computeQuantiles", input_stats_compute_quantiles)
            add_prop("dam.spark.data_stats.input.cachePerPath", input_stats_cache_bypath)
            add_prop("dam.spark.data_stats.input.coalesceEnabled", input_stats_coalesce_enabled)
            add_prop("dam.spark.data_stats.input.coalesceWorkers", input_stats_coalesce_workers)

            add_prop("dam.spark.data_stats.output.computeQuantiles", output_stats_compute_quantiles)
            add_prop("dam.spark.data_stats.output.cachePerPath", output_stats_cache_bypath)
            add_prop("dam.spark.data_stats.output.coalesceEnabled", output_stats_coalesce_enabled)
            add_prop("dam.spark.data_stats.output.coalesceWorkers", output_stats_coalesce_workers)

            if shutdown_timeout_sec is not None:
                properties.add(t2("dam.spark.shutdown_timeout", shutdown_timeout_sec))
            if enable_debugging:
                debug_level = debugging_log_level or "INFO"
                if process_name is not None:
                    dam_debug_filename = join_paths(logs_dir_path, process_name + ".kensu-collector-debug.log")
                else:
                    notebook_file_name = notebook_name.split('/')[-1].split('\\')[-1]  # remove path from notebook name
                    dam_debug_filename = join_paths(logs_dir_path, notebook_file_name + ".kensu-collector-debug.log")
                properties.add(t2("dam.spark.file_debug.level", debug_level))
                properties.add(t2("dam.spark.file_debug.file_name", dam_debug_filename))
                properties.add(t2("dam.spark.file_debug.capture_spark_logs", debugging_include_spark_logs))
                logging.info("Will write dam DAM log to file:" + dam_debug_filename)
            if shorten_data_source_names is not None:
                properties.add(t2("dam.datasources.short.name", shorten_data_source_names))

            if data_source_naming_strategy_rules is not None:
                data_source_naming_strategy = 'PathBasedRule'
                converted_rules = convert_naming_rules(data_source_naming_strategy_rules)
                properties.add(t2("dam.datasources.path_rules.short.naming_strategy", converted_rules))
            if logical_data_source_naming_strategy_rules is not None:
                logical_data_source_naming_strategy = 'PathBasedRule'
                converted_rules = convert_naming_rules(logical_data_source_naming_strategy_rules)
                properties.add(t2("dam.logical.datasources.path_rules.naming_strategy", converted_rules))

            if missing_column_lineage_strategy is not None:
                properties.add(t2('dam.spark.lineage.column_lineage_fallback_strategy', missing_column_lineage_strategy))

            if data_source_naming_strategy is not None:
                properties.add(t2("dam.datasources.short.naming_strategy", data_source_naming_strategy))
            if logical_data_source_naming_strategy is not None:
                properties.add(t2("dam.logical.datasources.naming_strategy", logical_data_source_naming_strategy))
            if environment is not None:
                properties.add(t2("dam.activity.environment", environment))
            if project_name is not None:
                properties.add(t2("dam.activity.projects", project_name))

            process_name = None
            if process_name is not None:
                process_name = process_name
            elif notebook_name != 'Unknown pyspark filename':
                process_name = notebook_name
            if process_name is not None:
                properties.add(t2("dam.activity.explicit.process.name", process_name))

            if process_run_name is not None:
                properties.add(t2("dam.activity.explicit.process_run.name", process_name))

            maybe_fake_timestamp = execution_timestamp
            if maybe_fake_timestamp is not None:
                set_fake_timestamp(spark_session, maybe_fake_timestamp)
            maybe_ds_path_sanitizer_search = os.environ.get('DAM_DS_PATH_SANITIZER_SEARCH')
            maybe_ds_path_sanitizer_replace = os.environ.get('DAM_DS_PATH_SANITIZER_REPLACE')
            if (maybe_ds_path_sanitizer_search is not None) and (maybe_ds_path_sanitizer_replace is not None):
                add_ds_path_sanitizer(spark_session, maybe_ds_path_sanitizer_search, maybe_ds_path_sanitizer_replace)

            w = jvm.io.kensu.dam.lineage.spark.lineage.Implicits.SparkSessionDAMWrapper(spark_session._jsparkSession)
            w.track(damIngestionUrl, jvm.scala.Option.empty(), properties.toSeq())

            if (shutdown_timeout_sec is not None) and (shutdown_timeout_sec > 0):
                logging.info('patching spark.stop to wait for DAM reporting to finish')
                from pyspark.sql import SparkSession
                SparkSession.stop = patched_spark_stop(SparkSession.stop, shutdown_timeout_sec)
                logging.info('patching spark.stop done')

            if disable_spark_writes:
                try:
                    do_disable_spark_writes(spark_session)
                except:
                    import traceback
                    logging.info("unexpected issue when disabling df.write {}".format(traceback.format_exc()))

            if cache_output_for_stats and compute_stats:
                try:
                    logging.info('patching DataFrame.write to cache/persist the results to speedup data-stats computation')
                    from pyspark.sql import DataFrame
                    DataFrame.write = patched_dataframe_write(DataFrame.write)
                    logging.info('done patching DataFrame.write')
                except:
                    import traceback
                    logging.info("unexpected issue when patching DataFrame.write: {}".format(traceback.format_exc()))

            if patch_spark_data_frame:
                patch_dam_df_helpers()

            if patch_pandas_conversions:
                try:
                    logging.info('patching DataFrame.toPandas')
                    from pyspark.sql import DataFrame
                    import kensu.pandas as pd
                    DataFrame.toPandas = pd.data_frame.wrap_external_to_pandas_transformation(
                        DataFrame.toPandas,
                        get_inputs_lineage_fn
                    )
                    logging.info('done patching DataFrame.toPandas')
                except:
                    import traceback
                    logging.info("unexpected issue when patching DataFrame.toPandas: {}".format(traceback.format_exc()))
                try:
                    logging.info('patching spark.createDataFrame to work with pandas dataframes')
                    from pyspark.sql import SparkSession
                    SparkSession.createDataFrame = patched_spark_createDataFrame_pandas(
                        SparkSession.createDataFrame,
                        pandas_to_spark_df_via_tmp_file=pandas_to_spark_df_via_tmp_file,
                        tmp_dir=pandas_to_spark_tmp_dir
                    )
                    logging.info('patching  spark.createDataFrame done')
                except:
                    import traceback
                    logging.info("unexpected issue when patching DataFrame.toPandas: {}".format(traceback.format_exc()))
                try:
                    logging.info('adding spark env var spark.executorEnv.KSU_DISABLE_PY_COLLECTOR=true'
                                 ' to disable kensu-py collector on executor nodes')
                    spark_session.conf.set("spark.executorEnv.KSU_DISABLE_PY_COLLECTOR", 'true')
                    spark_session.sparkContext.environment['KSU_DISABLE_PY_COLLECTOR'] = 'true'
                    logging.info('done adding spark.executorEnv.KSU_DISABLE_PY_COLLECTOR')
                except:
                    import traceback
                    logging.info("unexpected issue when adding spark.executorEnv.KSU_DISABLE_PY_COLLECTOR: {}".format(traceback.format_exc()))


            if 'kensu_py_client' in kwargs:
                if kwargs['kensu_py_client']:
                    from kensu.utils.kensu_provider import KensuProvider as K
                    K().initKensu(do_report=False)

            if h2o_support:
                # needed to support both ways of importing: from local file or dam-client-python package
                try:
                    from kensu_dam.h2o import dam_patch_h2o
                except ImportError:
                    from dam_h2o_collector import dam_patch_h2o

                if logs_dir_path is not None:
                    dam_patch_h2o(log_file_prefix=process_name or '',
                                  debug_file_enabled=True,
                                  debug_stdout_enabled=True,
                                  dam_logs_directory=logs_dir_path,
                                  create_virtual_training_datasource=h2o_create_virtual_training_datasource)
                else:
                    dam_patch_h2o(debug_file_enabled=False,
                                  debug_stdout_enabled=True,
                                  create_virtual_training_datasource=h2o_create_virtual_training_datasource)


        except Exception as e:
            logging.info("Error when initializing DAM tracker:")
            import traceback
            logging.info(traceback.format_exc())
