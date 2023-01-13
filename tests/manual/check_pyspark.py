from kensu.pyspark.spark_connector import init_kensu_spark
from kensu.utils.remote.circuit_breakers import kill_app_on_circuit_breaker

import os

kensu_output_dir = os.path.abspath(os.environ.get('KENSU_OUTPUT_DIR', '/tmp/kensu_trash'))
kensu_jar_path = os.environ.get('KENSU_JAR', 'kensu-spark-collector-1.0.18-alpha230103142250_spark-3.3.0.jar')
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
    .appName("SimpleApp") \
    .getOrCreate()
spark.sparkContext.setLogLevel("INFO")

# Test various options/features:
# - agent:stats_off -> remote:on
# - agent:stats_on -> remote:off
# - agent:on -> remote:off-specific-metric
# - circuit_breaker (should fail)
# - circuit_breaker (should succeed)

# - report_to_file=True
#   * note that CB usage might appear misleading in this case. nothing would be sent to backend, so CBs would check old stats
#   * maybe CBs should be disabled in report_to_file=True (at least by default)
# - report_to_file=False
stats_enabled = False
init_kensu_spark(spark_session=spark,
                 # these options are not needed, just testing here
                 compute_stats=stats_enabled,
                 compute_input_stats=stats_enabled,
                 compute_output_stats=stats_enabled,
                 cache_output_for_stats=stats_enabled,
                 input_stats_compute_quantiles=stats_enabled,
                 output_stats_compute_quantiles=stats_enabled,
                 input_stats_compute_std_dev=stats_enabled,
                 output_stats_compute_std_dev=stats_enabled,
                 # --
                 # p.s. having either of remote_conf_enabled=True or remote_circuit_breaker_enabled=True,
                 # makes kensu_ingestion_url & kensu_ingestion_token config properties mandatory
                 remote_conf_enabled=True,
                 remote_circuit_breaker_enabled=True,
                 remote_circuit_breaker_precheck_delay_secs=5)


df = spark.read.option('inferSchema', True).option('header', True) \
    .csv('tests/unit/data/Employee-Attrition.csv')
df.write.mode('overwrite').csv('remoteconf_someoutput.csv')

kill_app_on_circuit_breaker(exit_code=254, spark=spark)

spark.stop()
