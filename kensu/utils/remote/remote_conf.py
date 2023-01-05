from kensu.utils.helpers import lds_name_from_datasource
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
        self.remotelyKnownColumnNames = set([])  # FIXME: agree/implement API client
        self.remotelyKnownColumnNamesEnabled = False # FIXME

    def __unicode__(self):
        return f'LdsRemoteConf(activeMetrics: {self.activeMetrics}, useDefaultConfig: {self.useDefaultConfig})'

    def __str__(self):
        return self.__unicode__()

    def is_enabled(self, default_conf_enabled):
        # FIXME: check if available field names / metrics overlap with remotely configured metrics
        if self.useDefaultConfig:
            return default_conf_enabled
        else:
            return bool(self.activeMetrics)

    # somefield.somemetric
    def active_metric_names(self, available_metric_names):
        if self.useDefaultConfig:
            return available_metric_names
        else:
            return self.activeMetrics

    def is_metric_active(self, metric, column=None):
        # explicitly enabled by remote conf or using agent-conf
        if self.active_metric_names([metric]):
            return True
        elif column:
            if column in self.remotelyKnownColumnNames:
                # column was known remotely, thus, it's explicitly disabled
                return False
            elif self.remotelyKnownColumnNamesEnabled:
                # fallback to agent config for a column/field which was not known to Kensu
                # at the time the config was saved
                return True
        # for nrows, column_name=None
        return False

    @staticmethod
    def default():
        return SingleLdsRemoteConf(activeMetrics=None, useDefaultConfig=True)

    def __eq__(self, other):
        return self.activeMetrics == other.activeMetrics and \
               self.useDefaultConfig == other.useDefaultConfig


# FIXME: ADD actual_column_names (schema?)
def query_metric_conf_by_datasource(ds):
    return query_metric_conf(lds_name_from_datasource(ds))


def query_metric_conf_via_extractor(orig_variable):
    ksu = KensuProvider().instance()  # type: Kensu
    ds = ksu.extractors.extract_data_source(orig_variable,
                                            ksu.default_physical_location_ref,
                                            logical_data_source_naming_strategy=ksu.logical_naming)
    return query_metric_conf_by_datasource(ds)

# FIXME: ADD actual_column_names
def query_metric_conf(lds_name, process_name=None):
    # if remote_conf disabled...
    default_conf = SingleLdsRemoteConf.default()
    ksu = KensuProvider().instance()  # type: Kensu
    if not ksu.remote_conf_enabled:
        logging.info(f'Kensu agent remote config disabled, using agent config')
        return default_conf

    if not process_name:
        process_name = ksu.process_name

    http_resp_dict = _send_request(
        api=ksu.kensu_remote_conf_api,
        process_name=process_name,
        lds_names=[lds_name],
        requested_info='METRICS_CONFIG'
    )
    metrics_configuration = http_resp_dict.get('metricsConfiguration', [])
    # { 'activeMetrics': ['somefield.somemetric', ... ],
    #   'logicalDataSource': {'ldsName': 'hive_database.db/hive_table'},
    #   'useDefaultConfig': False }
    maybe_result = list([
         SingleLdsRemoteConf(activeMetrics=c.get('activeMetrics'),
                             useDefaultConfig=c.get('useDefaultConfig'))
         for c in metrics_configuration
         if c.get('logicalDataSource', {}).get('ldsName') == lds_name])
    if maybe_result:
        remote_res = maybe_result[0]

        if remote_res.useDefaultConfig:
            logging.info(f'Kensu Remote config didnt specify what to do with LDS "{lds_name}", using agent conf instead')
        elif not remote_res.activeMetrics:
            # FIXME: take into account the actual columns (e.g. might not overlap -> no datastats at all)
            #  FIXME: take into account remotely known-columns (some columns may be new/renamed, thus use agent-conf for these)
            logging.info(f'DataStats were disabled by Kensu Remote config for LDS "{lds_name}"')

        return remote_res
    else:
        # no explicit response received
        return default_conf
