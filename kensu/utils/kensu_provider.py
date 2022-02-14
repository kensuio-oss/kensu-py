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
            pandas_support = kwargs.get("pandas_support", True)
            sklearn_support = kwargs.get("sklearn_support")
            bigquery_support = kwargs.get("bigquery_support")
            tensorflow_support = kwargs.get("tensorflow_support")
            bigquery_headers = kwargs.get("bigquery_headers")

            project_names = kwargs.get("project_names")
            environment = kwargs.get("environment")
            timestamp = kwargs.get("timestamp")
            logical_naming = kwargs.get("logical_naming")
            mapping = kwargs["mapping"] if "mapping" in kwargs else True
            report_in_mem = kwargs.get("report_in_mem")
            get_code_version = kwargs.get("get_code_version")
            stats = kwargs.get("compute_stats")
            input_stats = kwargs.get("input_stats")
            sql_util_url = kwargs.get("sql_util_url")
            compute_delta = kwargs.get("compute_delta")
            sdk_verify_ssl = kwargs.get("sdk_verify_ssl")

            _kensu = Kensu(api_url=api_url, auth_token=auth_token, process_name=process_name, user_name=user_name,
                      code_location=code_location, init_context=init_context, do_report=do_report, pandas_support = pandas_support,
                      sklearn_support = sklearn_support, bigquery_support = bigquery_support, tensorflow_support = tensorflow_support, 
                      project_names=project_names,environment=environment,timestamp=timestamp,logical_naming=logical_naming,mapping=mapping, report_in_mem = report_in_mem,
                      report_to_file=report_to_file, offline_file_name=offline_file_name, reporter=reporter,
                      get_code_version=get_explicit_code_version_fn or get_code_version or get_code_version_fn,
                      compute_stats=stats,input_stats=input_stats, bigquery_headers = bigquery_headers, sql_util_url= sql_util_url,
                      compute_delta=compute_delta,
                      sdk_verify_ssl=sdk_verify_ssl)

            KensuProvider().setKensu(_kensu)
            return _kensu
        else:
            logging.error("Kensu default is already set kensu={}".format(str(ksu_provided_inst)))
