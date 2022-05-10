from airflow.operators import python as airflow_python

from airflow.operators.python import *

from kensu.airflow.kensu_airflow_collector import COLLECTOR_STATUS_INIT, COLLECTOR_STATUS_DONE, log_status, \
    airflow_init_kensu, handle_ex


class PythonOperator(airflow_python.PythonOperator):
    def __init__(
            self,
            *args,
            **kwargs,
    ):
        super(PythonOperator, self).__init__(
            *args, **kwargs
        )

    def execute(self, context: Dict) -> None:
        # in PythonOperator, we need to initialize Kensu before calling the original execute(),
        # as the underlying python function could use Kensu tracked functions inside itself
        try:
            log_status(self, COLLECTOR_STATUS_INIT)
            airflow_init_kensu(airflow_operator=self)
        except Exception as ex:
            handle_ex(self, ex)
        res = super(PythonOperator, self).execute(context)
        log_status(self, COLLECTOR_STATUS_DONE)
        return res


PythonOperator.__doc__ = airflow_python.PythonOperator.__doc__
