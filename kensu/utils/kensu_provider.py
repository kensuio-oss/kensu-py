import logging

from kensu.utils.helpers import singleton


@singleton
class KensuProvider(object):
    default = None  # type: Kensu

    def instance(self):
        # type: () -> Kensu
        return self.default

    def setKensu(self, kensu):
        self.default = kensu

    # FIXME: probably we don't need get_explicit_code_version_fn & get_code_version_fn anymore. but keeping it for backwards-compat for now...
    @staticmethod
    def initKensu(api_url=None, auth_token=None, process_name=None, user_name=None, code_location=None, get_code_version_fn=None, get_explicit_code_version_fn=None, init_context=True, do_report=None, report_to_file=None, offline_file_name=None, reporter=None, **kwargs):
        allow_reinit = kwargs["allow_reinit"] if "allow_reinit" in kwargs else False
        ksu_provided_inst = KensuProvider().instance()
        if ksu_provided_inst is not None and allow_reinit:
            logging.warning("KensuProvider.initKensu called more than once - reinitializing as requested by allow_reinit=True")
            KensuProvider().setKensu(None)
        if ksu_provided_inst is None or allow_reinit:
            from kensu.utils.kensu import Kensu
            pandas_support = kwargs["pandas_support"] if "pandas_support" in kwargs else True
            sklearn_support = kwargs["sklearn_support"] if "sklearn_support" in kwargs else True
            bigquery_support = kwargs["bigquery_support"] if "bigquery_support" in kwargs else None
            tensorflow_support = kwargs["tensorflow_support"] if "tensorflow_support" in kwargs else None
            bigquery_headers = kwargs["bigquery_headers"] if "bigquery_headers" in kwargs else None

            project_names = kwargs["project_names"] if "project_names" in kwargs else None
            environment = kwargs["environment"] if "environment" in kwargs else None
            timestamp = kwargs["timestamp"] if "timestamp" in kwargs else None
            logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None
            mapping = kwargs["mapping"] if "mapping" in kwargs else True
            report_in_mem = kwargs["report_in_mem"] if "report_in_mem" in kwargs else False
            get_code_version = kwargs["get_code_version"] if "get_code_version" in kwargs else None
            stats = kwargs["compute_stats"] if "compute_stats" in kwargs else True
            sql_util_url = kwargs["sql_util_url"] if "sql_util_url" in kwargs else None

            _kensu = Kensu(api_url=api_url, auth_token=auth_token, process_name=process_name, user_name=user_name,
                      code_location=code_location, init_context=init_context, do_report=do_report, pandas_support = pandas_support,
                      sklearn_support = sklearn_support, bigquery_support = bigquery_support, tensorflow_support = tensorflow_support, 
                      project_names=project_names,environment=environment,timestamp=timestamp,logical_naming=logical_naming,mapping=mapping, report_in_mem = report_in_mem,
                      report_to_file=report_to_file, offline_file_name=offline_file_name, reporter=reporter,
                      get_code_version=get_explicit_code_version_fn or get_code_version or get_code_version_fn,
                      compute_stats=stats, bigquery_headers = bigquery_headers, sql_util_url= sql_util_url)

            KensuProvider().setKensu(_kensu)
            return _kensu
        else:
            logging.error("Kensu default is already set kensu={}".format(str(ksu_provided_inst)))
