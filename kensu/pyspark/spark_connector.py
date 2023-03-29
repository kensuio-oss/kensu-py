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


def wait_for_spark_completion(spark, wait_timeout_secs):
    sc = spark.sparkContext
    jvm = sc._jvm
    client_class = ref_scala_object(jvm, "io.kensu.sparkcollector.KensuSparkCollector")
    duration_class = ref_scala_object(jvm, "scala.concurrent.duration.Duration")
    duration_30s = duration_class.apply(30, "second")
    duration_wait_timeout = duration_class.apply(wait_timeout_secs, "second")
    return client_class.shutdown(duration_30s, duration_wait_timeout)


def patched_spark_stop(wrapped, wait_timeout_secs):
    def wrapper(self):
        try:
            logging.info('KENSU: in spark.stop, waiting for Kensu Spark-Collector reporting to finish')
            wait_for_spark_completion(self, wait_timeout_secs)
            logging.info('KENSU: in spark.stop, waiting for Kensu Spark-Collector done, stopping spark context')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue: {}".format(traceback.format_exc()))
        result = wrapped(self)
        logging.info('KENSU: in spark.stop, spark context stopped')
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
            from kensu import pandas as ksu_pandas
            if isinstance(data, ksu_pandas.data_frame.DataFrame):
                logging.info('KENSU: replacing kensu.pandas.data_frame.DataFrame wrapper into a original pandas...')
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
                    logging.info('KENSU: spark.createDataFrame(pandas_df): Kensu will write pandas_df to a temp file - '+ abs_tmp_file_name)
                    data.to_parquet(abs_tmp_file_name, index=False)
                    # here do not call the Spark's original implementation of spark.createDataFrame(),
                    # and just read tmp file with spark, so we'd have the lineage
                    spark_temp_file_path = 'file:' + abs_tmp_file_name
                    logging.info('KENSU: spark.createDataFrame(pandas_df): Kensu will read to a temp file in spark - ' + spark_temp_file_path)
                    spark_df = self.read.parquet(spark_temp_file_path)
                    return spark_df
            logging.info('KENSU: done modifying arguments to spark.createDataFrame')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue: {}".format(traceback.format_exc()))
        result = wrapped(self, data, *args, **kwargs)
        logging.info('KENSU: end of spark.createDataFrame')
        return result

    wrapper.__doc__ = wrapped.__doc__
    return wrapper


def patched_dataframe_write(wrapped):
    def wrapper(self):
        try:
            logging.info('KENSU: in patched DataFrame.write, marking DataFrame as cached')
            from pyspark.sql import DataFrameWriter
            result = DataFrameWriter(self.cache())
            logging.info('KENSU: in patched DataFrame.write, returning result')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue in DataFrame.write: {}".format(traceback.format_exc()))
            from pyspark.sql import DataFrameWriter
            result = DataFrameWriter(self.cache())
        return result

    return property(wrapper)


def patched_dataframe_toPandas(wrapped):
    def wrapper(self):
        try:
            logging.info('KENSU: in patched DataFrame.toPandas()')
            result = wrapped(self)
            logging.info('KENSU: in patched DataFrame.toPandas(), returning result')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue in DataFrame.toPandas(): {}".format(traceback.format_exc()))
            result = wrapped(self)
        return result

    return wrapper


def get_spark_from_df(dataframe  # type: DataFrame
                    ):
    sql_context = dataframe.sql_ctx  # type: SQLContext
    return sql_context.sparkSession


def get_jvm_from_df(dataframe  # type: DataFrame
                    ):
    spark = get_spark_from_df(dataframe)
    return spark.sparkContext._jvm


def call_df_as_kensu_datasource(df,  # type: DataFrame
                                location, datasource_type,
                                name=None,  # type: str
                                logical_name=None  # type: str
                                ):
    jvm = get_jvm_from_df(df)
    w = jvm.io.kensu.sparkcollector.KensuSparkCollector.KensuSparkDataFrame(df._jdf)
    return w.reportAsKensuDatasource(location, datasource_type, jvm.scala.Option.apply(name), jvm.scala.Option.apply(logical_name))


def call_df_as_kensu_jdbc_datasource(df,  # type: DataFrame
                                     dbType,  # type: str
                                     schemaName,  # type: str
                                     tableName,  # type: str
                                     maybeDatabaseName,  # type: str
                                     name=None,  # type: str
                                     logical_name=None  # type: str
                                     ):
    jvm = get_jvm_from_df(df)
    w = jvm.io.kensu.sparkcollector.KensuSparkCollector.KensuSparkDataFrame(df._jdf)
    return w.reportAsKensuJdbcDatasource(dbType, schemaName, tableName, jvm.scala.Option.apply(maybeDatabaseName), jvm.scala.Option.apply(name), jvm.scala.Option.apply(logical_name))


def do_disable_spark_writes(spark):
    """
    Disables spark writes, but keeps Kensu Spark-Collector reporting.
    Affects only the writes which use DataFrameWriter - dataFrame.write.someMethod(), including .csv(), .save(), .saveAsTable().

    Note: This function MUST be run before first spark write, otherwise spark writes will not be disabled!
    """
    logging.info('KENSU: disabling df.write')
    sc = spark.sparkContext
    jvm = sc._jvm
    spark_writes_disabler = ref_scala_object(jvm, "io.kensu.sparkcollector.spark.nowrites.SparkWritesDisabler")
    spark_writes_disabler.disableSparkWrites()
    logging.info('KENSU: disabling df.write done')


def set_fake_timestamp(spark, mocked_timestamp):
    """
    Sets a fake timestamp to be reported to Kensu Spark-Collector
    """
    logging.info('KENSU: overriding execution_timestamp starting')
    sc = spark.sparkContext
    jvm = sc._jvm
    clazz = ref_scala_object(jvm, "io.kensu.sparkcollector.utils.TimeUtils")
    force_override = False
    clazz.setMockedTime(int(mocked_timestamp), force_override)
    logging.info('KENSU: overriding execution_timestamp done')


def add_ds_path_sanitizer(spark, search_str, replacement_str):
    logging.info('KENSU: add_ds_path_sanitizer starting')
    sc = spark.sparkContext
    jvm = sc._jvm
    clazz = ref_scala_object(jvm, "io.kensu.sparkcollector.datasources.DataSourceConverters")
    clazz.addDsPathSanitizer(search_str, replacement_str)
    logging.info('KENSU: add_ds_path_sanitizer done')

def report_df_as_kensu_datasource():
    def report_as_kensu_datasource(self, # type: DataFrame
                                 location, # type: str
                                 datasource_type=None, # type: str
                                 name=None, # type: str
                                 logical_name=None # type: str
                                 ):
        try:
            logging.info('KENSU: in df.report_as_kensu_datasource')
            call_df_as_kensu_datasource(self, location, datasource_type or 'in-memory-dataframe', name, logical_name)
            logging.info('KENSU: df.report_as_kensu_datasource started in background')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue: {}".format(traceback.format_exc()))
        return self
    return report_as_kensu_datasource


def report_df_as_kensu_jdbc_datasource():
    def report_as_kensu_jdbc_datasource(self,  # type: DataFrame
                                      db_type,  # type: str
                                      schema_name,  # type: str
                                      table_name,  # type: str
                                      maybe_db_name=None,  # type: str
                                      name=None, # type: str
                                      logical_name=None # type: str
                                      ):
        try:
            logging.info('KENSU: in df.report_as_kensu_jdbc_datasource')
            call_df_as_kensu_jdbc_datasource(self, db_type, schema_name, table_name, maybe_db_name, name, logical_name)
            logging.info('KENSU: df.report_as_kensu_jdbc_datasource started in background')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue: {}".format(traceback.format_exc()))
        return self
    return report_as_kensu_jdbc_datasource


def report_df_as_kpi():
    def report_as_kpi(self,  # type: DataFrame
                      name,  # type: str
                      logical_name=None,  # type: str
                      datasource_type="Business metric (KPI)" # type: str
                      ):
        try:
            logging.info('KENSU: in df.report_as_kpi')
            jvm = get_jvm_from_df(self)
            w = jvm.io.kensu.sparkcollector.KensuSparkCollector.KensuSparkDataFrame(self._jdf)
            w.reportAsKPI(name, logical_name or name, datasource_type)
            logging.info('KENSU: df.report_as_kpi started in background')
        except:
            import traceback
            logging.warning("KENSU: unexpected issue: {}".format(traceback.format_exc()))
        return self
    return report_as_kpi


def patch_kensu_df_helpers():
    fns_to_patch = list(map(lambda fn: [fn.__name__, fn], [
        addOutputObservations,
        addCustomObservationsToOutput,
        reportCustomKafkaInputSchema,
        reportCustomEventhubInputSchema
    ])) + [
        ['report_as_kensu_datasource', report_df_as_kensu_datasource()],
        ['report_as_kensu_jdbc_datasource', report_df_as_kensu_jdbc_datasource()],
        ['report_as_kpi', report_df_as_kpi()]
    ]
    for fn_name, wrapper_builder in fns_to_patch:
        try:
            logging.info(f'KENSU: Patching DataFrame.{fn_name}')
            from pyspark.sql import DataFrame
            # can setattr behave differently than .somename = somevalue?
            setattr(DataFrame, fn_name, wrapper_builder)
            logging.info(f'KENSU: done patching DataFrame.{fn_name}')
        except:
            import traceback
            log_and_print(logging.warning,
                          f"KENSU: unexpected issue when patching DataFrame.{fn_name}: {traceback.format_exc()}")


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
    # a rule looks like this: kensu-spark-collector/hive-query-results->>File
    rules_list = list(["{}->>{}".format(matcher, formatter) for (matcher, formatter) in rules])
    # FIXME: allow passing a list in spark-collector
    return ";".join(rules_list)


def scala_ds_and_schema_to_py(kensu_instance, ds, schema):
    from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema
    from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
    pl_ref = kensu_instance.UNKNOWN_PHYSICAL_LOCATION.to_ref()
    py_ds = DataSource(name=ds.name(),
                       format=ds.format() or None,
                       categories=list(ds.categories() or []), # NULLABLE
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


def get_inputs_lineage_fn(kensu_instance, df, virtual_ds_name=None, virtual_ds_logical_name=None):
    jvm = get_jvm_from_df(df)
    # call def fetchToPandasReport(
    #     df: DataFrame,
    #     name: String = UUID.randomUUID().toString,
    #     logicalName: Option[String] = None,
    #     datasourceType: String = InternalDatasourceTags.TAG_INPUT_LINEAGE_ONLY,
    #     timeout: Duration
    #   )
    client_class = ref_scala_object(jvm, "io.kensu.sparkcollector.dataconversions.SparkToPandasConversionTracker")
    duration_300s =  ref_scala_object(jvm, "scala.concurrent.duration.Duration").apply(300, "second")
    # FIXME: it should NOT wait for datasts -> check
    import uuid
    if not virtual_ds_name:
        virtual_ds_name = str(uuid.uuid1())
    # FIXME: virtual_ds_logical_name
    # FIXME: add format
    no_logical_name = jvm.scala.Option.apply(None)
    lineage_from_scala = client_class.fetchToPandasReport(
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
            input_ds=scala_ds_and_schema_to_py(kensu_instance, e.ds(), e.schema()),
            lineage=j2py_dict_of_lists(e.lineage())
        ) for e in lineage_from_scala.lineage()
    ]
    logging.info('KENSU: lineage_info:', lineage_info)
    return GenericComputedInMemDs(inputs=list([x.input_ds for x in lineage_info]), lineage=lineage_info)


def get_process_run_info(spark):
    if spark is not None:
        logging.info(f'Getting Process info from Kensu Spark Agent')
        cls = ref_scala_object(spark.sparkContext._jvm, "io.kensu.sparkcollector.pyspark.PySparkUtils")
        # requires Kensu collector to be already initialized - if not yet, it returns None
        # getProcessAndRunGuid(spark): ProcessRunInfo (nullable)
        # case class ProcessRunInfo(processGuid: String, processRunGuid: String)
        run_info = cls.getProcessAndRunGuid(spark._jsparkSession)
        if run_info:
            logging.info(f'Successfully retrieved the Process info from Kensu Spark Agent')
            return {
                "process_guid": run_info.processGuid(),
                "process_run_guid": run_info.processRunGuid()
            }
    logging.info(f'Unable to get Process info from Kensu Spark Agent, maybe Spark Agent is not initialized yet?')
    return None


def get_df_with_inmem_tag(df,  # type: DataFrame
                          df_tag  # type: str
                          ):
    jvm = get_jvm_from_df(df)
    cls = ref_scala_object(jvm, "io.kensu.sparkcollector.lineage.CreateDataFrameLineage")
    # def dataframeWithLineageTag(df: DataFrame, inputsId: String): DataFrame
    jdf = cls.dataframeWithLineageTag(df._jdf, df_tag)
    # finally convert Java DataFrame back to python DataFrame
    spark = get_spark_from_df(df)
    from pyspark.sql.dataframe import DataFrame
    return DataFrame(jdf, spark)


def register_manual_lineage(spark,
                            output_df_tag,  # type: str
                            inputs          # type: list[dict[str, object]]
                            ):
    # def registerLineage(spark: SparkSession, inputsId: String, inputDatasources: java.util.List[SimpleInputDsSchema])
    cls_reporter = ref_scala_object(spark.sparkContext._jvm, "io.kensu.sparkcollector.lineage.CreateDataFrameLineage")
    # build inputDatasources
    # case class SimpleInputDsSchema(path: String, format: String, schema: java.util.Map[String, String])
    cls_inputobj = ref_scala_object(spark.sparkContext._jvm, "io.kensu.sparkcollector.lineage.SimpleInputDsSchema")
    inputDatasources = list([
        cls_inputobj.apply(i.get('path'), i.get('format'), i.get('schema'))
        for i in inputs
    ])
    cls_reporter.registerLineage(spark._jsparkSession, output_df_tag, inputDatasources)

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
- logical_data_source_naming_strategy:
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
        kensu_ingestion_url=None,
        kensu_ingestion_token=None,
        report_to_file=None,
        disable_tracking=False,
        logs_dir_path=None,
        offline_file_name=None,
        process_name=None,
        process_run_name=None,
        code_location=None,
        code_version=None,
        user_name=None,
        enable_entity_compaction=None,
        kensu_api_verify_ssl=None,
        compute_stats=None,
        compute_input_stats=None,
        compute_output_stats=None,
        input_stats_for_only_used_columns=None,
        input_stats_keep_filters=None,
        input_stats_compute_quantiles=None,
        input_stats_compute_simple_num=None,
        input_stats_compute_std_dev=None,
        input_stats_cache_by_path=None,
        input_stats_coalesce_enabled=None,
        input_stats_coalesce_workers=None,
        output_stats_compute_quantiles=None,
        output_stats_compute_simple_num=None,
        output_stats_compute_std_dev=None,
        output_stats_cache_by_path=None,
        output_stats_coalesce_enabled=None,
        output_stats_coalesce_workers=None,
        cache_output_for_stats=None,
        shorten_data_source_names=None,
        shutdown_timeout_sec=None,
        enable_collector_log_file=None,
        collector_log_level=None,
        collector_log_include_spark_logs=None,
        data_source_naming_strategy=None,
        data_source_naming_strategy_rules=None,
        logical_data_source_naming_strategy=None,
        logical_data_source_naming_strategy_rules=None,
        missing_column_lineage_strategy=None,
        patch_spark_data_frame=None,
        disable_spark_writes=None,
        environment=None,
        execution_timestamp=None,
        project_name=None,
        h2o_support=None,
        h2o_create_virtual_training_datasource=None,
        patch_pandas_conversions=False,
        pandas_to_spark_df_via_tmp_file=None,
        pandas_to_spark_tmp_dir=None,
        use_api_client=None,
        remote_conf_enabled=True,
        remote_conf_timeout_secs=None,
        remote_circuit_breaker_enabled=True,
        remote_circuit_breaker_precheck_delay_secs=None,
        datastats_send_timeout_secs=None,
        conf_file_path=None,
        **kwargs
):
    import os
    is_tracking_disabled = (os.environ.get("KSU_DISABLE_TRACKING", 'False') == 'True') or disable_tracking

    if not is_tracking_disabled:
        logging.info("Initializing Kensu tracking...")
        jvm = spark_session.sparkContext._jvm

        from configparser import ConfigParser, ExtendedInterpolation
        config = ConfigParser(interpolation=ExtendedInterpolation())
        conf_path = get_conf_path("conf.ini")
        try:
            config.read(conf_path)
        except:
            logging.warning(f"Cannot load config from file `%s`" % (conf_path))

        kensu_conf = config['kensu'] if config.has_section('kensu') else config['DEFAULT']

        use_api_client = extract_config_property('use_api_client', False, use_api_client, kw=kwargs, conf=kensu_conf, tpe=bool)

        kensu_ingestion_url = extract_config_property('kensu_ingestion_url', None, kensu_ingestion_url, kw=kwargs, conf=kensu_conf)
        kensu_ingestion_token = extract_config_property('kensu_ingestion_token', None, kensu_ingestion_token, kw=kwargs, conf=kensu_conf)
        report_to_file = extract_config_property('report_to_file', False, report_to_file, kw=kwargs, conf=kensu_conf, tpe=bool)
        logs_dir_path = extract_config_property('logs_dir_path', None, logs_dir_path, kw=kwargs, conf=kensu_conf)
        offline_file_name = extract_config_property('offline_file_name', 'kensu-offline.log', offline_file_name, kw=kwargs, conf=kensu_conf)

        shutdown_timeout_sec = extract_config_property('shutdown_timeout_sec', 10 * 60, shutdown_timeout_sec, kw=kwargs, conf=kensu_conf, tpe=int)
        kensu_api_verify_ssl = extract_config_property('kensu_api_verify_ssl', True, kensu_api_verify_ssl, kw=kwargs, conf=kensu_conf, tpe=bool)
        enable_collector_log_file = extract_config_property('enable_collector_log_file', False, enable_collector_log_file, kw=kwargs, conf=kensu_conf, tpe=bool)
        collector_log_level = extract_config_property('collector_log_level', 'INFO', collector_log_level, kw=kwargs, conf=kensu_conf)
        collector_log_include_spark_logs = extract_config_property('collector_log_include_spark_logs', False, collector_log_include_spark_logs, kw=kwargs, conf=kensu_conf, tpe=bool)

        process_name = extract_config_property('process_name', None, process_name, kw=kwargs, conf=kensu_conf)
        process_run_name = extract_config_property('process_run_name', None, process_run_name, kw=kwargs, conf=kensu_conf)
        code_location = extract_config_property('code_location', None, code_location, kw=kwargs, conf=kensu_conf)
        code_version = extract_config_property('code_version', None, code_version, kw=kwargs, conf=kensu_conf)
        user_name = extract_config_property('user_name', None, user_name, kw=kwargs, conf=kensu_conf)
        enable_entity_compaction = extract_config_property('enable_entity_compaction',True,enable_entity_compaction, kw=kwargs, conf=kensu_conf, tpe=bool)
        environment = extract_config_property('environment',None,environment, kw=kwargs, conf=kensu_conf)
        project_name = extract_config_property('project_name', None, project_name, kw=kwargs, conf=kensu_conf)
        execution_timestamp = extract_config_property('execution_timestamp', None, execution_timestamp, kw=kwargs, conf=kensu_conf, tpe=int)

        compute_stats = extract_config_property('compute_stats', True, compute_stats, kw=kwargs, conf=kensu_conf, tpe=bool)
        compute_input_stats = extract_config_property('compute_input_stats', True, compute_input_stats, kw=kwargs, conf=kensu_conf, tpe=bool)
        compute_output_stats = extract_config_property('compute_output_stats', True, compute_output_stats, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_for_only_used_columns = extract_config_property('input_stats_for_only_used_columns',True,input_stats_for_only_used_columns, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_keep_filters = extract_config_property('input_stats_keep_filters',True,input_stats_keep_filters, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_compute_quantiles = extract_config_property('input_stats_compute_quantiles',False,input_stats_compute_quantiles, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_compute_simple_num = extract_config_property('input_stats_compute_simple_num',None,input_stats_compute_simple_num, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_compute_std_dev = extract_config_property('input_stats_compute_std_dev',None,input_stats_compute_std_dev, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_cache_by_path = extract_config_property('input_stats_cache_by_path', True, input_stats_cache_by_path, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_coalesce_enabled = extract_config_property('input_stats_coalesce_enabled',True,input_stats_coalesce_enabled, kw=kwargs, conf=kensu_conf, tpe=bool)
        input_stats_coalesce_workers = extract_config_property('input_stats_coalesce_workers',1,input_stats_coalesce_workers, kw=kwargs, conf=kensu_conf, tpe=int)
        output_stats_compute_quantiles = extract_config_property('output_stats_compute_quantiles',False,output_stats_compute_quantiles, kw=kwargs, conf=kensu_conf, tpe=bool)
        output_stats_compute_simple_num = extract_config_property('output_stats_compute_simple_num',None,output_stats_compute_simple_num, kw=kwargs, conf=kensu_conf, tpe=bool)
        output_stats_compute_std_dev = extract_config_property('output_stats_compute_std_dev',None,output_stats_compute_std_dev, kw=kwargs, conf=kensu_conf, tpe=bool)
        output_stats_cache_by_path = extract_config_property('output_stats_cache_by_path', False, output_stats_cache_by_path, kw=kwargs, conf=kensu_conf, tpe=bool)
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

        patch_pandas_conversions = extract_config_property('patch_pandas_conversions', False, patch_pandas_conversions, kw=kwargs, conf=kensu_conf, tpe=bool)
        pandas_to_spark_df_via_tmp_file = extract_config_property('pandas_to_spark_df_via_tmp_file',True,pandas_to_spark_df_via_tmp_file, kw=kwargs, conf=kensu_conf, tpe=bool)
        pandas_to_spark_tmp_dir = extract_config_property('pandas_to_spark_tmp_dir','/tmp/spark-to-pandas-tmp',pandas_to_spark_tmp_dir, kw=kwargs, conf=kensu_conf)

        try:
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
            ingestion_url = jvm.scala.Option.apply(kensu_ingestion_url)
            t2 = jvm.scala.Tuple2
            provider_class_name = t2("spark_environment_provider", "io.kensu.sparkcollector.system.DefaultSparkEnvironmentProvider")

            ### How to get GIT info here?
            #         explicit_code_repo=None,
            #         explicit_code_version=None,
            #         explicit_code_maintainers=None,
            #         explicit_lauched_by_user=None,
            code_repo_name = code_location or "Jupyter-Notebook:spark-" + spark_session.version + "::" + notebooks_path
            repository = t2("code_location", code_repo_name)
            from datetime import datetime
            d = datetime.now()

            code_version_value = code_version or notebook_name + "::" + str(d)
            version = t2("code_version", code_version_value)

            user = t2("user_name", user_name)

            properties = jvm.scala.collection.mutable.HashSet()

            def add_prop(name, value):
                if value is not None:
                    properties.add(t2(name, value))

            properties.add(provider_class_name)
            properties.add(repository)
            properties.add(version)
            properties.add(user)
            if kensu_ingestion_url:
                properties.add(t2("kensu_ingestion_url", kensu_ingestion_url))
            if kensu_ingestion_token:
                properties.add(t2("kensu_ingestion_token", kensu_ingestion_token))
            if report_to_file is not None:
                properties.add(t2("report_to_file", report_to_file))
            if logs_dir_path:
                properties.add(t2("offline_report_dir_path", logs_dir_path))
            if offline_file_name:
                properties.add(t2("offline_file_name", offline_file_name))
            if kensu_api_verify_ssl is not None:
                properties.add(t2("kensu_api_verify_ssl", kensu_api_verify_ssl))
            if enable_entity_compaction is not None:
                properties.add(t2("enable_entity_compaction", enable_entity_compaction))

            if compute_stats is not None:
                properties.add(t2("compute_stats", compute_stats))
            if compute_input_stats is not None:
                properties.add(t2("compute_input_stats", compute_input_stats))
            if compute_output_stats is not None:
                properties.add(t2("compute_output_stats", compute_output_stats))
            if input_stats_for_only_used_columns:
                properties.add(t2("input_stats_for_only_used_columns", input_stats_for_only_used_columns))
            if input_stats_keep_filters is not None:
                properties.add(t2("input_stats_keep_filters", input_stats_keep_filters))

            add_prop("input_stats_compute_quantiles", input_stats_compute_quantiles)
            add_prop("input_stats_compute_simple_num", input_stats_compute_simple_num)
            add_prop("input_stats_compute_std_dev", input_stats_compute_std_dev)
            add_prop("input_stats_cache_by_path", input_stats_cache_by_path)
            add_prop("input_stats_coalesce_enabled", input_stats_coalesce_enabled)
            add_prop("input_stats_coalesce_workers", input_stats_coalesce_workers)

            add_prop("output_stats_compute_quantiles", output_stats_compute_quantiles)
            add_prop("output_stats_compute_simple_num", output_stats_compute_simple_num)
            add_prop("output_stats_compute_std_dev", output_stats_compute_std_dev)
            add_prop("output_stats_cache_by_path", output_stats_cache_by_path)
            add_prop("output_stats_coalesce_enabled", output_stats_coalesce_enabled)
            add_prop("output_stats_coalesce_workers", output_stats_coalesce_workers)

            def extract_prop(name, tpe, value):
                return name, extract_config_property(key=name, default=None, arg=value, kw=kwargs, conf=kensu_conf, tpe=tpe)

            properties_by_name = [
                extract_prop('remote_conf_enabled', tpe=bool, value=remote_conf_enabled),
                extract_prop('remote_conf_timeout_secs', tpe=int, value=remote_conf_timeout_secs),
                extract_prop('remote_circuit_breaker_enabled', tpe=bool, value=remote_circuit_breaker_enabled),
                extract_prop('remote_circuit_breaker_precheck_delay_secs', tpe=int, value=remote_circuit_breaker_precheck_delay_secs),
                extract_prop('datastats_send_timeout_secs', tpe=int, value=datastats_send_timeout_secs),
            ]
            for prop_name, prop_value in properties_by_name:
                if prop_value is not None:
                    add_prop(prop_name, prop_value)

            if shutdown_timeout_sec is not None:
                properties.add(t2("shutdown_timeout_sec", shutdown_timeout_sec))
            if enable_collector_log_file:
                debug_level = collector_log_level or "INFO"
                if process_name is not None:
                    kensu_debug_filename = join_paths(logs_dir_path, process_name + ".kensu-collector.log")
                else:
                    notebook_file_name = notebook_name.split('/')[-1].split('\\')[-1]  # remove path from notebook name
                    kensu_debug_filename = join_paths(logs_dir_path, notebook_file_name + ".kensu-collector.log")
                properties.add(t2("collector_log_level", debug_level))
                properties.add(t2("collector_log_file_path", kensu_debug_filename))
                properties.add(t2("collector_log_include_spark_logs", collector_log_include_spark_logs))
                logging.info("KENSU: Will write Kensu Spark Collector logs to file: " + kensu_debug_filename)
            if shorten_data_source_names is not None:
                properties.add(t2("shorten_data_source_names", shorten_data_source_names))

            if data_source_naming_strategy_rules is not None:
                data_source_naming_strategy = 'PathBasedRule'
                converted_rules = convert_naming_rules(data_source_naming_strategy_rules)
                properties.add(t2("data_source_naming_strategy_rules", converted_rules))
            if logical_data_source_naming_strategy_rules is not None:
                logical_data_source_naming_strategy = 'PathBasedRule'
                converted_rules = convert_naming_rules(logical_data_source_naming_strategy_rules)
                properties.add(t2("logical_data_source_naming_strategy_rules", converted_rules))

            if missing_column_lineage_strategy is not None:
                properties.add(t2('missing_column_lineage_strategy', missing_column_lineage_strategy))

            if data_source_naming_strategy is not None:
                properties.add(t2("data_source_naming_strategy", data_source_naming_strategy))
            if logical_data_source_naming_strategy is not None:
                properties.add(t2("logical_data_source_naming_strategy", logical_data_source_naming_strategy))
            if environment is not None:
                properties.add(t2("environment", environment))
            if project_name is not None:
                properties.add(t2("project_name", project_name))

            process_name = None
            if process_name is not None:
                process_name = process_name
            elif notebook_name != 'Unknown pyspark filename':
                process_name = notebook_name
            if process_name is not None:
                properties.add(t2("process_name", process_name))

            if process_run_name is not None:
                properties.add(t2("process_run_name", process_run_name))

            maybe_fake_timestamp = execution_timestamp
            if maybe_fake_timestamp is not None:
                set_fake_timestamp(spark_session, maybe_fake_timestamp)
            maybe_ds_path_sanitizer_search = os.environ.get('KSU_DS_PATH_SANITIZER_SEARCH')
            maybe_ds_path_sanitizer_replace = os.environ.get('KSU_DS_PATH_SANITIZER_REPLACE')
            if (maybe_ds_path_sanitizer_search is not None) and (maybe_ds_path_sanitizer_replace is not None):
                add_ds_path_sanitizer(spark_session, maybe_ds_path_sanitizer_search, maybe_ds_path_sanitizer_replace)

            if is_databricks():
                print('Detected Databricks Notebook - initializing Kensu via DatabricksCollector.track()')
                w = ref_scala_object(jvm, 'io.kensu.sparkcollector.environments.DatabricksCollector')
                # FIXME: DON'T WE OVERRIDE SOME UNNEEDED CONF KEYS!?
                w.track(spark_session._jsparkSession, conf_file_path or get_conf_path(), properties.toSeq())
            else:
                w = jvm.io.kensu.sparkcollector.KensuSparkCollector.KensuSparkSession(spark_session._jsparkSession)
                w.track(ingestion_url, jvm.scala.Option.empty(), properties.toSeq())

            if (shutdown_timeout_sec is not None) and (shutdown_timeout_sec > 0):
                logging.info('KENSU: patching spark.stop to wait for Kensu Spark-Collector reporting to finish')
                from pyspark.sql import SparkSession
                SparkSession.stop = patched_spark_stop(SparkSession.stop, shutdown_timeout_sec)
                logging.info('KENSU: patching spark.stop done')

            if disable_spark_writes:
                try:
                    do_disable_spark_writes(spark_session)
                except:
                    import traceback
                    logging.warning("KENSU: unexpected issue when disabling df.write {}".format(traceback.format_exc()))

            if cache_output_for_stats and compute_stats:
                try:
                    logging.info('KENSU: patching DataFrame.write to cache/persist the results to speedup data-stats computation')
                    from pyspark.sql import DataFrame
                    DataFrame.write = patched_dataframe_write(DataFrame.write)
                    logging.info('KENSU: done patching DataFrame.write')
                except:
                    import traceback
                    logging.warning("KENSU: unexpected issue when patching DataFrame.write: {}".format(traceback.format_exc()))

            if patch_spark_data_frame:
                patch_kensu_df_helpers()

            if patch_pandas_conversions:
                try:
                    logging.info('KENSU: patching DataFrame.toPandas')
                    from pyspark.sql import DataFrame
                    import kensu.pandas as pd
                    DataFrame.toPandas = pd.data_frame.wrap_external_to_pandas_transformation(
                        DataFrame.toPandas,
                        get_inputs_lineage_fn
                    )
                    logging.info('KENSU: done patching DataFrame.toPandas')
                except:
                    import traceback
                    logging.warning("KENSU: unexpected issue when patching DataFrame.toPandas: {}".format(traceback.format_exc()))
                try:
                    logging.info('KENSU: patching spark.createDataFrame to work with pandas dataframes')
                    from pyspark.sql import SparkSession
                    SparkSession.createDataFrame = patched_spark_createDataFrame_pandas(
                        SparkSession.createDataFrame,
                        pandas_to_spark_df_via_tmp_file=pandas_to_spark_df_via_tmp_file,
                        tmp_dir=pandas_to_spark_tmp_dir
                    )
                    logging.info('KENSU: patching  spark.createDataFrame done')
                except:
                    import traceback
                    logging.warning("KENSU: unexpected issue when patching DataFrame.createDataFrame: {}".format(traceback.format_exc()))
                try:
                    logging.info('KENSU: adding spark env var KSU_DISABLE_PY_COLLECTOR=true to disable kensu-py collector on executor nodes')
                    spark_session.conf.set("KSU_DISABLE_PY_COLLECTOR", 'true')
                    spark_session.sparkContext.environment['KSU_DISABLE_PY_COLLECTOR'] = 'true'
                    logging.info('KENSU: done adding KSU_DISABLE_PY_COLLECTOR')
                except:
                    import traceback
                    logging.warning("KENSU: unexpected issue when adding spark.executorEnv.KSU_DISABLE_PY_COLLECTOR: {}".format(traceback.format_exc()))

            if use_api_client:
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
            import traceback
            logging.warning("Error when initializing Kensu tracking: " + traceback.format_exc())
    else:
        logging.info("Tracking by Kensu is disabled")


def check_spark_circuit_breakers_and_stop_if_broken(
        spark,
        stop_spark=True):
    cls = ref_scala_object(spark.sparkContext._jvm, "io.kensu.sparkcollector.KensuSparkCollector")
    breakers_failed = cls.checkIfCircuitBreakersFailedAndPrepShutdown(spark._jsparkSession)
    if breakers_failed:
        logging.warning("Some kensu circuit breaker has failed (there are active unresolved tickets in a rule "
                        "marked as a circuit breaker), so the app will shutdown now")
        if stop_spark:
            logging.warning("Shutting down Spark context now...")
            spark.stop()
        else:
            logging.warning("Not shutting down Spark context as it was not requested.")
    return breakers_failed


def is_databricks():
    import os
    return "DATABRICKS_RUNTIME_VERSION" in os.environ


def log_and_print(log_fn, msg):
    log_fn(msg)
    # in Databricks print to stdout too, so output is visible in the same notebook
    # (default logging loglevel is WARNING, so logging.info would be lost)
    if is_databricks():
        print(msg)


def with_catch_errors(fn_name, default_result, fn_result_lambda):
    # TODO: check configurable decorators too https://stackoverflow.com/a/27446895 ?
    result = default_result
    try:
        logging.info(f'KENSU: in {fn_name}')
        result = fn_result_lambda(default_result)
        logging.info(f'KENSU: {fn_name} done')
    except:
        import traceback
        log_and_print(logging.warning, f"KENSU: unexpected issue in {fn_name}: {traceback.format_exc()}")
    return result


def catch_errors_with_default_self(func):
    def new_func(*args, **kwargs):
        default_self = args[0]
        return with_catch_errors(
            fn_name=func.__name__,
            default_result=default_self,
            fn_result_lambda=lambda default_result: func(*args, **kwargs))
    new_func.__doc__ = func.__doc__
    new_func.__name__ = func.__name__
    try:
        import inspect
        new_func.__signature__ = inspect.signature(func)
    except:
        pass
    return new_func


@catch_errors_with_default_self
def addOutputObservations(df,  # type: DataFrame
                          compute_count_distinct=False  # not recommended due to likely performance impact
                          ):
    # FIXME: looks like we have a repeating pyspark DF -> JVM DF -> pyspark DF pattern here
    spark = df.sql_ctx.sparkSession
    jvm = spark.sparkContext._jvm
    cls = ref_scala_object(jvm, "org.apache.spark.sql.kensu.KensuObserveMetrics")
    #   def addOutputObservations(df: DataFrame, computeCountDistinct: Boolean = false): DataFrame
    jdf = cls.addOutputObservations(df._jdf, compute_count_distinct)
    # finally convert Java DataFrame back to python DataFrame
    from pyspark.sql.dataframe import DataFrame
    return DataFrame(jdf, spark)


# a global var, used in addCustomObservationsToOutput
next_observation_num = 0


@catch_errors_with_default_self
def addCustomObservationsToOutput(df,  # type: DataFrame
                                  *exprs  # type: pyspark.sql.column.Column
                                 ):
    """
    custom observations/metrics can be added at any stage of the stream DataFrame - and currently uses same semantics as
     pyspark's own DataFrame.observe(), so can pass any Spark aggregation expressions.

    just make sure that each expression:
    - return a double datatype .cast("double")
    - has a unique and meaningful alias within the whole stream DataFrame
      because that will become metrics name in Kensu, e.g. expr.alias("someColumn.max_before_filtering")

    see https://spark.apache.org/docs/latest/api/python/reference/pyspark.sql/api/pyspark.sql.DataFrame.observe.html
    """
    global next_observation_num
    next_observation_num = next_observation_num + 1
    return df.observe(
        # observation ID must be unique and start with ksu_metrics_output_
        f"ksu_metrics_output_custom_gen{next_observation_num}",
       *exprs
    )


def pyspark_datatype_to_jvm(jvm, pyspark_datatype):
    return ref_scala_object(jvm, "org.apache.spark.sql.types.DataType")\
        .fromJson(pyspark_datatype.json())


@catch_errors_with_default_self
def reportCustomKafkaInputSchema(df,  # type: DataFrame
                                 custom_schema=None,  # StructType, if None, will use current DataFrame schema
                                 fieldNamePrefix="value.",
                                 schemaDesc="after Kafka event value parsing"
                                ):
    """
    this reports a custom schema for a Kafka read operations in Spark Streaming.
    it works by finding all/any such source URIs in the provided `SparkStreaming DataFrame`,
    and for each (if any), reporting the provided custom schema

    P.S. custom schema may appear in Kensu a few minutes later if the source was not yet ingested before (ingestion delay)
    """
    jvm = get_jvm_from_df(df)
    cls = ref_scala_object(jvm, "org.apache.spark.sql.kensu.KafkaStreamCustomSchema")
    jvm_datatype = pyspark_datatype_to_jvm(jvm, custom_schema or df.schema())
    #   def reportCustomSchema(df: DataFrame, custom_schema: StructType, fieldNamePrefix: String, schemaDesc: String): DataFrame
    res = cls.reportCustomSchema(df._jdf, jvm_datatype, fieldNamePrefix, schemaDesc)
    log_and_print(logging.info, f'Tried reporting custom Kafka schema: {res}')
    return df


@catch_errors_with_default_self
def reportCustomEventhubInputSchema(df,  # type: DataFrame
                                 custom_schema=None,  # StructType, if None, will use current DataFrame schema
                                 fieldNamePrefix="body.",
                                 schemaDesc="after EventHub event value parsing"
                                 ):
    """
    this reports a custom schema for a EventHub read operations in Spark Streaming.
    it works by finding all/any such source URIs in the provided `SparkStreaming DataFrame`,
    and for each (if any), reporting the provided custom schema

    P.S. custom schema may appear in Kensu a few minutes later if the source was not yet ingested before (ingestion delay)
    """
    jvm = get_jvm_from_df(df)
    cls = ref_scala_object(jvm, "org.apache.spark.sql.kensu.EventHubsCustomSchema")
    jvm_datatype = pyspark_datatype_to_jvm(jvm, custom_schema or df.schema())
    #   def reportCustomSchema(df: DataFrame, custom_schema: StructType, fieldNamePrefix: String, schemaDesc: String): DataFrame
    res = cls.reportCustomSchema(df._jdf, jvm_datatype, fieldNamePrefix, schemaDesc)
    log_and_print(logging.info, f'Tried reporting custom EventHub schema: {res}')
    return df
