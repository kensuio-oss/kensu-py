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
    def initKensu(kensu_ingestion_url=None, kensu_ingestion_token=None, process_name=None, user_name=None, code_location=None,
                  get_code_version_fn=None, get_explicit_code_version_fn=None, do_report=None,
                  report_to_file=None, offline_file_name=None, reporter=None, report_process_info=True, **kwargs):
        allow_reinit = kwargs["allow_reinit"] if "allow_reinit" in kwargs else False
        ksu_provided_inst = KensuProvider().instance()
        if ksu_provided_inst is not None and allow_reinit:
            logging.warning("KensuProvider.initKensu called more than once - reinitializing as requested by allow_reinit=True")
            KensuProvider().setKensu(None)
        if ksu_provided_inst is None or allow_reinit:
            from kensu.utils.kensu import Kensu
            pandas_support = kwargs.get("pandas_support", True)
            numpy_support = kwargs.get("numpy_support", True)

            sklearn_support = kwargs.get("sklearn_support")

            tensorflow_support = kwargs.get("tensorflow_support")

            bigquery_support = kwargs.get("bigquery_support")
            bigquery_headers = kwargs.get("bigquery_headers")

            project_name = kwargs.get("project_name")
            environment = kwargs.get("environment")
            execution_timestamp = kwargs.get("execution_timestamp")
            logical_data_source_naming_strategy = kwargs.get("logical_data_source_naming_strategy")
            get_code_version = kwargs.get("get_code_version")
            
            stats = kwargs.get("compute_stats")
            input_stats = kwargs.get("compute_input_stats")
            compute_delta = kwargs.get("compute_delta_stats")
            kensu_sql_parser_url = kwargs.get("kensu_sql_parser_url")
            api_verify_ssl = kwargs.get("kensu_api_verify_ssl")
            
            assume_default_physical_location_exists = kwargs.get("assume_default_physical_location_exists", False)

            _kensu = Kensu(kensu_ingestion_url=kensu_ingestion_url, kensu_ingestion_token=kensu_ingestion_token, process_name=process_name,
                           user_name=user_name, code_location=code_location, kensu_api_verify_ssl=api_verify_ssl,
                           do_report=do_report, pandas_support=pandas_support, numpy_support=numpy_support, sklearn_support=sklearn_support,
                           bigquery_support=bigquery_support, tensorflow_support=tensorflow_support,
                           project_name=project_name, environment=environment, execution_timestamp=execution_timestamp,
                           logical_data_source_naming_strategy=logical_data_source_naming_strategy,
                           report_to_file=report_to_file, offline_file_name=offline_file_name, reporter=reporter,
                           get_code_version=get_explicit_code_version_fn or get_code_version or get_code_version_fn,
                           compute_stats=stats, compute_input_stats=input_stats, bigquery_headers=bigquery_headers,
                           kensu_sql_parser_url=kensu_sql_parser_url, compute_delta_stats=compute_delta,
                           assume_default_physical_location_exists=assume_default_physical_location_exists,
                           report_process_info=report_process_info)

            KensuProvider().setKensu(_kensu)
            return _kensu
        else:
            logging.warning("Kensu default is already set kensu={}".format(str(ksu_provided_inst)))
