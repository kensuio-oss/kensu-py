import logging


def kill_app_on_circuit_breaker(exit_code=254, spark=None):
    if spark is not None:
        logging.info(f'Going to check the circuit breakers for Spark datasources')
        from kensu.pyspark.spark_connector import check_spark_circuit_breakers_and_kill_if_broken
        check_spark_circuit_breakers_and_kill_if_broken(spark=spark, exit_code=exit_code)
    else:
        logging.info(f'Not checking any Circuit breakers (spark=None)')
