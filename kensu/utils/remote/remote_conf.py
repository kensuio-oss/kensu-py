from kensu.utils.kensu import Kensu
from kensu.client import *
import sys
import logging
import time
from kensu.utils.kensu_provider import KensuProvider


def _send_request(api, process_name, lds_names, requested_info='METRICS_CONFIG'):
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

    @staticmethod
    def default():
        return SingleLdsRemoteConf(activeMetrics=None, useDefaultConfig=True)

    def __eq__(self, other):
        return self.activeMetrics == other.activeMetrics and \
               self.useDefaultConfig == other.useDefaultConfig


def query_metric_conf(api, process_name, lds_name):
    # if remote_conf disabled...
    default_conf = SingleLdsRemoteConf.default()
    ksu = KensuProvider().instance()
    if not ksu.remote_conf_enabled:
        logging.info(f'Kensu agent remote config disabled, using agent default')
        return default_conf
    response_dict = _send_request(
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
