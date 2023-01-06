import json

from kensu.utils.kensu import Kensu
from kensu.client import *
import sys
import logging
import time
from kensu.utils.kensu_provider import KensuProvider



# FIXME: handle remote conf errors- return fallback vs FAIL!?
# FIXME: handle remote conf timeout
# - CB
# - metric_conf - api
# - metric_conf - impl into kensu-py

from kensu.utils.remote.circuit_breakers import query_if_to_break_app, break_app_if_needed
from kensu.utils.remote.remote_conf import query_metric_conf


kensu_remote_conf_api = KensuRemoteAgentConfApi()

from http_to_jsonl_server import FakeIngestionConf, FakeIngestionApi
ingestion_token = 'mytoken'
conf = FakeIngestionConf(out_file_path='outfile.custom.txt',
                         error_log_path='errors.txt',
                         expected_useragent_subsubstr=None,
                         expected_xauth_token=ingestion_token)
with FakeIngestionApi.create(conf=conf) as fake_ingestion_port:
    print('bound fake ingestion server to port={}'.format(fake_ingestion_port))

    from tests.unit.testing_helpers import setup_kensu_tracker, setup_logging
    setup_logging()
    setup_kensu_tracker(out_file='somefile.txt')

    # need to be after kensu init, to override default config
    Kensu._configure_api(kensu_remote_conf_api, f'http://localhost:{fake_ingestion_port}', ingestion_token)
    ksu = KensuProvider().instance()
    ksu.remote_circuit_breaker_precheck_delay_secs = 5

    break_app_now = query_if_to_break_app(
        api=kensu_remote_conf_api,
        process_name="my-process-name",
        lds_names=[
            "hive_database.db/hive_table",
            "/warehouse/2019-10/my_ds_name_3"
        ])
    print(f'break_app_now: {break_app_now}')
    print(break_app_now.__class__)

    c = query_metric_conf(process_name='my-process-name-2', lds_name='hive_database.db/hive_table')
    print(c)

    c = query_metric_conf(process_name='my-process-name-3',
                          lds_name='hive_database.db/hive_tablex')
    print(c)



    break_app_if_needed()
    #print(json.loads(resp))
    print('done')
    time.sleep(1)

