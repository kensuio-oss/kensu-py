from kensu.pyspark.spark_connector import init_kensu_spark, get_process_run_info, get_inputs_lineage_fn, get_df_with_inmem_tag, register_manual_lineage
from kensu.utils.kensu_provider import KensuProvider

import os

kensu_output_dir = os.path.abspath(os.environ.get('KENSU_OUTPUT_DIR', '/tmp/kensu_trash'))
jar_name = 'kensu-spark-collector-1.0.18-alpha230120105001_spark-3.3.0.jar'
print(f'you can download the jar with: wget https://public.usnek.com/n/repository/public/releases/kensu-spark-collector/alpha/{jar_name}')

kensu_jar_path = os.environ.get('KENSU_JAR', jar_name)
spark_warehouse_dir = f"{kensu_output_dir}/spark-warehouse-dir"

from pyspark.sql import SparkSession

# These options are not mandatory, but they make Spark a bit more lightweight
# P.S. javax.jdo.option.ConnectionURL needed to be able to run with .enableHiveSupport() in parallel
spark = SparkSession.builder \
    .config("spark.driver.extraClassPath", kensu_jar_path) \
    .config("spark.executor.memory", "2g") \
    .config("spark.driver.memory", "2g") \
    .config("spark.sql.warehouse.dir", spark_warehouse_dir) \
    .config("javax.jdo.option.ConnectionURL",
            "jdbc:derby:memory:;databaseName=${metastoreLocation.getAbsolutePath};create=true") \
    .config("hive.exec.dynamic.partition.mode", "nonstrict") \
    .enableHiveSupport() \
    .appName("test pyspark integration") \
    .getOrCreate()
spark.sparkContext.setLogLevel("INFO")

stats_enabled = True
init_kensu_spark(spark_session=spark,
                 project_name='better pyspark integration',
                 # these options are not needed, just testing here
                 compute_stats=stats_enabled,
                 compute_input_stats=stats_enabled,
                 compute_output_stats=stats_enabled,
                 cache_output_for_stats=stats_enabled,
                 input_stats_compute_quantiles=stats_enabled,
                 output_stats_compute_quantiles=stats_enabled,
                 input_stats_compute_std_dev=stats_enabled,
                 output_stats_compute_std_dev=stats_enabled,
                 # FIXME - i think this should be disabled (at least should not wrap pandas)
                 # so default has already been chaned to patch_pandas_conversions=False
                 patch_pandas_conversions=False)

run_info = get_process_run_info(spark)
if run_info:
    # "process_guid": run_info.processGuid(),
    #                 "process_run_guid"
    process_guid = run_info['process_guid']
    process_run_guid = run_info['process_run_guid']
    print(f'Got from spark process_guid={process_guid} process_run_guid={process_run_guid}')

KensuProvider().initKensu()

spark_df = spark.read.option('inferSchema', True).option('header', True) \
     .csv('tests/unit/data/Employee-Attrition.csv')

# how to handle .toPandas():
# option 1: internal function to extract lineage of given Spark DataFrame, without patching Spark DataFrame
spark_lineage = get_inputs_lineage_fn(kensu_instance=KensuProvider().instance(), df=spark_df)
# returns:
# GenericComputedInMemDs(lineage=[ExtDependencyEntry(input_ds=KensuDatasourceAndSchema(ksu_ds={'categories': [],
#  'format': 'csv',
#  'name': 'data/Employee-Attrition.csv',
#  'pk': {'location': 'file:///home/../kensu-py/tests/unit/data/Employee-Attrition.csv',
#         'physical_location_ref': {'by_guid': 'k-d2f40e99e5dd4c9fc9c634b15a7fb03073191c0158e52a572769df8c05f59b7b',
#                                   'by_pk': None}}}, ksu_schema={'name': 'schema::data/Employee-Attrition.csv',
#  'pk': {'data_source_ref': {'by_guid': 'k-f9ec8c96ba3190ff5b69dcc552ba50b74a3d590a3454855a80bbf9e4f73f6f9a',
#                             'by_pk': None},
#         'fields': [{'field_type': 'integer', 'name': 'Age', 'nullable': True},
#                    {'field_type': 'integer',
#                     'name': 'YearsWithCurrManager',
#                     'nullable': True}]}}), lineage={'JobLevel': ['JobLevel'], 'Department': ['Department'], 'EmployeeNumber': ['EmployeeNumber'], 'StockOptionLevel': ['StockOptionLevel'], 'PerformanceRating': ['PerformanceRating'], 'YearsSinceLastPromotion': ['YearsSinceLastPromotion'], 'Over18': ['Over18'], 'TrainingTimesLastYear': ['TrainingTimesLastYear'], 'HourlyRate': ['HourlyRate'], 'YearsWithCurrManager': ['YearsWithCurrManager'], 'PercentSalaryHike': ['PercentSalaryHike'], 'JobSatisfaction': ['JobSatisfaction'], 'YearsAtCompany': ['YearsAtCompany'], 'Attrition': ['Attrition'], 'MonthlyIncome': ['MonthlyIncome'], 'TotalWorkingYears': ['TotalWorkingYears'], 'EnvironmentSatisfaction': ['EnvironmentSatisfaction'], 'DailyRate': ['DailyRate'], 'Age': ['Age'], 'OverTime': ['OverTime'], 'RelationshipSatisfaction': ['RelationshipSatisfaction'], 'EmployeeCount': ['EmployeeCount'], 'BusinessTravel': ['BusinessTravel'], 'JobInvolvement': ['JobInvolvement'], 'StandardHours': ['StandardHours'], 'DistanceFromHome': ['DistanceFromHome'], 'JobRole': ['JobRole'], 'NumCompaniesWorked': ['NumCompaniesWorked'], 'WorkLifeBalance': ['WorkLifeBalance'], 'EducationField': ['EducationField'], 'Education': ['Education'], 'Gender': ['Gender'], 'MaritalStatus': ['MaritalStatus'], 'YearsInCurrentRole': ['YearsInCurrentRole'], 'MonthlyRate': ['MonthlyRate']})])
# stats should be sent only when kensu requests it in GenericComputedInMemDs.inputs[x].f_publish_stats
# which is KensuDatasourceAndSchema.f_publish_stats, and gets called when we call
# GenericComputedInMemDs.report(...)
# ---
# see GenericDatasourceInfoSupport(ExtractorSupport) in kensu/utils/dsl/extractors/generic_datasource_info_support.py
print(spark_lineage)

# P.S. if create_lineage was called before markInMem, we could have one function instead of these following two
spark_df_from_pandas = get_df_with_inmem_tag(
    df=spark.createDataFrame(spark_df.toPandas()),  # originally this would lose lineage
    df_tag='pandas_df')

register_manual_lineage(
    spark,
    output_df_tag='pandas_df',
    inputs=[
        {
            # FIXME: demonstrate how to use lineage extracted from .toPandas()
            'path': '1st manual input for createDataFrame',
            'format': 'CSV',
            'schema': {'field11': 'datatype1', 'field12': 'datatype2'}
        },
        {
            # FIXME: demonstrate how to use lineage extracted from .toPandas()
            'path': '2nd manual input for createDataFrame',
            'format': 'CSV',
            'schema': {'field21': 'string', 'field22': 'int'}
        }
    ]
   )

spark_df_from_pandas.write.mode('overwrite').csv('spark_test_createDataFrame_output.csv')

# option 2:  patched .toPandas() to extract/return lineage of Spark DataFrame, but without wrapping Pandas DataFrame
# FIXME - TODO: maybe spark_df.kensuTagInMem('some-alias').toPandas()
# FIXME - TODO: or maybe spark_df.tagInMemToPandas('some-alias')


spark.stop()
