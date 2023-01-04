import json

from kensu.utils.kensu import Kensu
from kensu.client import *
import sys, logging, time
from kensu.utils.kensu_provider import KensuProvider

kensu_remote_conf_api = KensuRemoteAgentConfApi()

from http_to_jsonl_server import FakeIngestionConf, FakeIngestionApi
ingestion_token = 'mytoken'

# FIXME: handle remote conf errors- return fallback vs FAIL!?
# FIXME: handle remote conf timeout
# - CB
# - metric_conf - api
# - metric_conf - impl into kensu-py


def send_request(api, process_name, lds_names, requested_info='METRICS_CONFIG'):
    request_body = {
        'processName': process_name,
        'logicalDatasources': [{'ldsName': n} for n in lds_names],
        "requestedInfo": requested_info,
    }
    return api.query_remote_conf(request_body)


class SingleLdsRemoteConf:

    def __init__(self, activeMetrics, useDefaultConfig):
        self.activeMetrics = activeMetrics
        self.useDefaultConfig = useDefaultConfig

    def __unicode__(self):
        return f'LdsRemoteConf(activeMetrics: {self.activeMetrics}, useDefaultConfig: {self.useDefaultConfig})'

    def __str__(self):
        return self.__unicode__()

    def is_active(self, default_config_active):
        # FIXME: check if available field names / metrics overlap with remotely configured metrics
        if self.useDefaultConfig:
            return default_config_active
        else:
            return bool(self.activeMetrics)

    # somefield.somemetric
    def active_metric_names(self, available_metric_names):
        if self.useDefaultConfig:
            return available_metric_names
        else:
            return self.activeMetrics


def query_metric_conf(api, process_name, lds_name):
    # if remote_conf disabled...
    default_conf = SingleLdsRemoteConf(activeMetrics=None, useDefaultConfig=True)
    ksu = KensuProvider().instance()
    if not ksu.remote_conf_enabled:
        logging.info(f'Kensu agent remote config disabled, using agent default')
        return default_conf
    response_dict = send_request(
        api=api,
        process_name=process_name,
        lds_names=[lds_name],
        requested_info='METRICS_CONFIG'
    )
    metrics_configuration = response_dict.get('metricsConfiguration', [])
    # { 'activeMetrics': ['somefield.somemetric', ... ],
    #   'logicalDataSource': {'ldsName': 'hive_database.db/hive_table'},
    #   'useDefaultConfig': False }
    maybe_result = list([
         SingleLdsRemoteConf(activeMetrics=c.get('activeMetrics'),
                             useDefaultConfig=c.get('useDefaultConfig'))
         for c in metrics_configuration
         if c.get('logicalDataSource', {}).get('ldsName') == lds_name])
    if maybe_result:
        return maybe_result[0]
    else:
        # no explicit response received
        return default_conf


def query_if_to_break_app(api, process_name, lds_names):
    resp = send_request(
        api=api,
        process_name=process_name,
        lds_names=lds_names,
        requested_info='BREAKERS'
    )
    return resp.get('breakProcessExecutionNow', False)


def break_app_if_needed(exit_code=254):
    # FIXME: what if spark is used together with kensu-py?!
    # FIXME: what if customer code needs some cleanup too? pass a callback?

    ksu = KensuProvider().instance()
    if not ksu.remote_circuit_breaker_enabled:
        logging.info('Kensu circuit breaker check is not active.')
        return
    delay_secs = ksu.remote_circuit_breaker_precheck_delay_secs
    logging.info(f'Waiting for {delay_secs}s to ensure ingestion completed, before checking the circuit breaker status...')
    time.sleep(delay_secs)
    logging.info('Checking the circuit breaker status now...')
    # FIXME: get these from kensu-py
    process_name = 'FIXME'
    lds_names = ['FIXME', 'FIXME']
    break_app_now = query_if_to_break_app(
        api=kensu_remote_conf_api,
        process_name=process_name,
        lds_names=lds_names)
    if break_app_now:
        msg = f'Some Kensu circuit breaker got activated - killing the app with exitCode={exit_code}'
        logging.error(msg)
        sys.exit(exit_code)
    else:
        msg = f'Kensu circuit breaker check was successful - no active circuit breakers found.'
        logging.info(msg)


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

    c = query_metric_conf(api=kensu_remote_conf_api, process_name='my-process-name-2', lds_name='hive_database.db/hive_table')
    print(c)

    c = query_metric_conf(api=kensu_remote_conf_api,
                          process_name='my-process-name-3',
                          lds_name='hive_database.db/hive_tablex')
    print(c)



    break_app_if_needed()
    #print(json.loads(resp))
    print('done')
    import time
    time.sleep(1)

