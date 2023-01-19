from kensu.pyspark.spark_connector import init_kensu_spark, get_process_run_info

import os

kensu_output_dir = os.path.abspath(os.environ.get('KENSU_OUTPUT_DIR', '/tmp/kensu_trash'))
jar_name = 'kensu-spark-collector-1.0.18-alpha230119084751_spark-3.3.0.jar'
print(f'get jar with: wget https://public.usnek.com/n/repository/public/releases/kensu-spark-collector/alpha/{jar_name}')

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
                 output_stats_compute_std_dev=stats_enabled)

run_info = get_process_run_info(spark)
if run_info:
    # "process_guid": run_info.processGuid(),
    #                 "process_run_guid"
    process_guid = run_info['process_guid']
    process_run_guid = run_info['process_run_guid']
    print(f'Got from spark process_guid={process_guid} process_run_guid={process_run_guid}')


# df = spark.read.option('inferSchema', True).option('header', True) \
#     .csv('tests/unit/data/Employee-Attrition.csv')
# df.write.mode('overwrite').csv('spark_test_someoutput.csv')


spark.stop()
