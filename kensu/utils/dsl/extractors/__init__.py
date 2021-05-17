from kensu.utils.helpers import singleton


class ExtractorSupport(object):
    def is_supporting(self, value):
        pass

    def extract_data_source(self, value, physical_location, **kwargs):
        pass

    def extract_schema(self, data_source, value):
        pass

    def extract_data_source_and_schema(self, value, physical_location):
        pass

    def extract_stats(self, value):
        pass

    def is_machine_learning(self, ml):
        pass

    def extract_machine_learning_info(self, ml):
        pass

    def extract_machine_learning_metrics(self, ml, **kwargs):
        pass

    def extract_machine_learning_hyper_parameters(self, ml):
        pass


@singleton
class Extractors(object):

    def __init__(self, ):
        self.supports = []

    def add_default_supports(self, pandas_support=True, sklearn_support=True, numpy_support=True, tensorflow_support=False, bigquery_support=False, generic_datasource_info_support=True):
        if pandas_support:
            from kensu.pandas.extractor import KensuPandasSupport
            self.add_support(KensuPandasSupport())

        if sklearn_support:
            from kensu.sklearn.extractor import KensuSKLearnSupport
            self.add_support(KensuSKLearnSupport())

        if numpy_support:
            from kensu.numpy.extractor import ndarraySupport
            self.add_support(ndarraySupport())

        if bigquery_support:
            from kensu.google.cloud.bigquery.extractor import KensuBigQuerySupport
            self.add_support(KensuBigQuerySupport())

        if generic_datasource_info_support:
            from kensu.utils.dsl.extractors.generic_datasource_info_support import GenericDatasourceInfoSupport
            self.add_support(GenericDatasourceInfoSupport())



    def add_support(self, support):
        self.supports.append(support)

    def extract_data_source(self, value, physical_location, **kwargs):
        for support in self.supports:
            if support.is_supporting(value):
                return support.extract_data_source(value, physical_location, **kwargs)

        raise Exception("Not supported object: " + str(value.__class__))

    def extract_schema(self, data_source, value):
        for support in self.supports:
            if support.is_supporting(value):
                return support.extract_schema(data_source, value)

        raise Exception("Not supported object: " + value.__class__)

    def extract_data_source_and_schema(self, value, physical_location):
        for support in self.supports:
            if support.is_supporting(value):
                return support.extract_data_source_and_schema(value, physical_location)

        raise Exception("Not supported object: " + value.__class__)

    def extract_stats(self, value):
        for support in self.supports:
            if support.is_supporting(value):
                return support.extract_stats(value)

        raise Exception("Not supported container: " + value.__class__)

    def extract_machine_learning_info(self, ml):
        for support in self.supports:
            if support.is_machine_learning(ml):
                if support.is_supporting(ml):
                    return support.extract_machine_learning_info(ml)
        # Not sure though... maybe there is no support for the model yet... how to figure out
        return None

    def extract_machine_learning_metrics(self, ml, **kwargs):
        for support in self.supports:
            if support.is_machine_learning(ml):
                if support.is_supporting(ml):
                    return support.extract_machine_learning_metrics(ml, **kwargs)

        raise Exception("Not supported container: " + ml.__class__)

    def extract_machine_learning_hyper_parameters(self, ml):
        for support in self.supports:
            if support.is_machine_learning(ml):
                if support.is_supporting(ml):
                    return support.extract_machine_learning_hyper_parameters(ml)

        raise Exception("Not supported container: " + ml.__class__)
