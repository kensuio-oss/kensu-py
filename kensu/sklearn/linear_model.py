from kensu.pandas import DataFrame,Series
from kensu.utils.kensu_provider import KensuProvider
import sklearn.linear_model as lm
from kensu.utils.helpers import eventually_report_in_mem
from kensu.numpy import ndarray
from kensu.client.models import Model,ModelPK,ModelRef,ModelTraining,ModelTrainingPK,ModelTrainingRef


class LogisticRegression(lm.LogisticRegression):

    def fit(self, X, y, sample_weight=None):
        X_train = X.get_df()
        if isinstance(y,DataFrame):
            y_train = y.get_df()
        elif isinstance(y,Series):
            y_train = y.get_s()
        result = super(LogisticRegression,self).fit( X_train , y_train,sample_weight )
        kensu = KensuProvider().instance()

        metrics = kensu.extractors.extract_machine_learning_metrics(result,x_train = X_train, y_train = y_train,classification = True )
        kensu = KensuProvider().instance()

        train_X_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(X_train, kensu.default_physical_location_ref))
        train_X_sc = eventually_report_in_mem(kensu.extractors.extract_schema(train_X_ds, X_train))

        train_y_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(y, kensu.default_physical_location_ref))
        train_y_sc = eventually_report_in_mem(kensu.extractors.extract_schema(train_y_ds, y))

        result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref,format='Sklearn Model'))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

        hyperparams = result.get_params()

        if kensu.mapping:
            for result_col in [s.name for s in result_sc.pk.fields]:
                for col in [s.name for s in train_X_sc.pk.fields]:
                    kensu.add_dependencies_mapping(result_sc.to_guid(),result_col,train_X_sc.to_guid(),col,'Model Train')
                for col in [s.name for s in train_y_sc.pk.fields]:
                    kensu.add_dependencies_mapping(result_sc.to_guid(), result_col, train_y_sc.to_guid(), col,
                                                 'Model Train')

        attr = [result,'SkLearn.LogisticRegression',metrics,hyperparams,result_ds,result_sc]
        self.attr = attr

        return result

    def predict(self, X):
        if 'kensu' in str(X.__class__):
            X_test = X.get_df()
        else:
            X_test = X

        result = super(LogisticRegression, self).predict(X_test)
        kensu = KensuProvider().instance()

        X_test_ds = eventually_report_in_mem(
            kensu.extractors.extract_data_source(X_test, kensu.default_physical_location_ref))
        X_test_sc = eventually_report_in_mem(kensu.extractors.extract_schema(X_test_ds, X_test))

        ksu_result = ndarray.using(result)

        result_ds = eventually_report_in_mem(
            kensu.extractors.extract_data_source(ksu_result, kensu.default_physical_location_ref))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, ksu_result))

        result = ksu_result

        try:
            model_ds = self.attr[4]
            model_sc = self.attr[5]
        except:
            model_ds = None
            model_sc = None

        if model_sc is not None:
            model = eventually_report_in_mem(model_ds)
            model_sc = eventually_report_in_mem(model_sc)
        if kensu.mapping:
            for result_col in [s.name for s in result_sc.pk.fields]:
                for col in [s.name for s in X_test_sc.pk.fields]:
                    kensu.add_dependencies_mapping(result_sc.to_guid(), result_col, X_test_sc.to_guid(), col,
                                                 'Model Predict')
                if model_sc is not None:
                    for col in [s.name for s in model_sc.pk.fields]:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), result_col, model_sc.to_guid(), col,
                                                     'Model Predict')
        return result
