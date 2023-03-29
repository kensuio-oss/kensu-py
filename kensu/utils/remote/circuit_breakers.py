import logging


def raise_default_circuit_breaker_exception(msg):
    raise AssertionError(msg)


def kill_app_on_circuit_breaker(
        exit_code=254,
        spark=None,
        stop_spark=True,
        sys_exit=True,
        raise_exception_fn=lambda msg: raise_default_circuit_breaker_exception(msg)
):
    if spark is not None:
        logging.info(f'Going to check the circuit breakers for Spark datasources')
        from kensu.pyspark.spark_connector import check_spark_circuit_breakers_and_stop_if_broken
        breakers_failed = check_spark_circuit_breakers_and_stop_if_broken(spark=spark, stop_spark=stop_spark)

        if breakers_failed:
            if sys_exit:
                import sys
                logging.warning(f"Some kensu circuit breaker has failed - killing the app with exit_code={exit_code}")
                sys.exit(exit_code)
            else:
                msg = f"Some kensu circuit breaker has failed - raising an Exception to stop the default app flow"
                logging.warning(msg)
                raise_exception_fn(msg)
                return False
        else:
            logging.info("Circuit breakers did not fail")
        return breakers_failed
    else:
        logging.info(f'Not checking any Circuit breakers (spark=None)')
        return True


"""
To be used interactively, as it do not kill spark and do not call sys.exit(), just raises an exception
"""
def databricks_notebook_break_app_on_circuit_breaker(
        spark=None,
        raise_exception_fn=lambda msg: raise_default_circuit_breaker_exception(msg)
):
    breakers_failed = kill_app_on_circuit_breaker(
        spark=spark,
        stop_spark=False,  # FIXME: not clear if better to stop
        sys_exit=False,
        raise_exception_fn=raise_exception_fn
    )
    return breakers_failed
