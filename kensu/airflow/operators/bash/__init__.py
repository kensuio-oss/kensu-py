import logging
from typing import Dict

import airflow

from kensu.airflow.kensu_airflow_collector import COLLECTOR_STATUS_INIT, COLLECTOR_STATUS_DONE, log_status, \
    airflow_init_kensu, handle_ex, report_simple_copy_with_guessed_schema


def dumb_parse_curl(s):
    import re
    try:
        # This is just a very simple example and should be customized to customer needs
        # e.g.: curl -sSL https://s3.amazonaws.com/nyc-tlc/trip+data/yellow_tripdata_2021-01.csv > /home/airflow/gcs/data/yellow_tripdata_2021-01.csv
        regexp = re.compile(r'curl.* (http[^> ]+) > (.+)')
        logging.info(f"dumb_parse_curl(s={s})")
        m = regexp.match(s)
        if m:
            logging.info("dumb_parse_curl parsed groups: " + str(m.groups()))
            input_uri = m.group(1)
            output_filename = m.group(2)
            report_simple_copy_with_guessed_schema(input_uri=input_uri, output_filename=output_filename)
            return True
    except Exception as e:
        logging.warning(f"caught exception in dumb_parse_curl", e)

    return None


class BashOperator(airflow.operators.bash.BashOperator):
    def __init__(
            self,
            *args,
            **kwargs,
    ):
        super(BashOperator, self).__init__(
            *args, **kwargs
        )
        self.cmd_matchers = [
            dumb_parse_curl
        ]

    def execute(self, context: Dict) -> None:
        res = super(BashOperator, self).execute(context)
        try:
            log_status(self, COLLECTOR_STATUS_INIT)
            airflow_init_kensu(airflow_operator=self)
            for matcher in self.cmd_matchers:
                if matcher(self.bash_command):
                    break
        except Exception as ex:
            handle_ex(self, ex)
        log_status(self, COLLECTOR_STATUS_DONE)
        return res

