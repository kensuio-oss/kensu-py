from kensu.utils.kensu import Kensu
from kensu.client import *
import sys
import logging
import time
from kensu.utils.kensu_provider import KensuProvider

from kensu.utils.remote.remote_conf import _send_request

def query_if_to_break_app(api, process_name, lds_names):
    resp = _send_request(
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
    process_name = ksu.process.pk.qualified_name
    lds_names = ksu.circuit_breaker_logical_datasource_names

    break_app_now = query_if_to_break_app(
        api=ksu.kensu_remote_conf_api,
        process_name=process_name,
        lds_names=lds_names)
    if break_app_now:
        msg = f'Some Kensu circuit breaker got activated - killing the app with exitCode={exit_code}'
        logging.error(msg)
        sys.exit(exit_code)
    else:
        msg = f'Kensu circuit breaker check was successful - no active circuit breakers found.'
        logging.info(msg)


