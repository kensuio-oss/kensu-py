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

    @staticmethod
    def initKensu(api_url=None, auth_token=None, process_name=None, user_name=None, code_location=None, init_context=True, do_report=True, report_to_file=False, offline_file_name=None, **kwargs):
        if KensuProvider().instance() is None:
            from kensu.utils.kensu import Kensu


            pandas_support = kwargs["pandas_support"] if "pandas_support" in kwargs else True
            sklearn_support = kwargs["sklearn_support"] if "sklearn_support" in kwargs else True
            bigquery_support = kwargs["bigquery_support"] if "bigquery_support" in kwargs else False
            tensorflow_support = kwargs["tensorflow_support"] if "tensorflow_support" in kwargs else False
            project_names = kwargs["project_names"] if "project_names" in kwargs else []
            environment = kwargs["environment"] if "environment" in kwargs else None
            timestamp = kwargs["timestamp"] if "timestamp" in kwargs else None
            logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None
            mapping = kwargs["mapping"] if "mapping" in kwargs else True
            report_in_mem =  kwargs["report_in_mem"] if "report_in_mem" in kwargs else False

            _kensu = Kensu(api_url=api_url, auth_token=auth_token, process_name=process_name, user_name=user_name,
                      code_location=code_location, init_context=init_context, do_report=do_report, pandas_support = pandas_support,
                      sklearn_support = sklearn_support, bigquery_support = bigquery_support, tensorflow_support = tensorflow_support, 
                      project_names=project_names,environment=environment,timestamp=timestamp,logical_naming=logical_naming,mapping=mapping, report_in_mem = report_in_mem,
                      report_to_file=report_to_file, offline_file_name=offline_file_name)

            KensuProvider().setKensu(_kensu)
            return _kensu
        else:
            logging.error("Kensu default is already set kensu={}" % KensuProvider.instance())
