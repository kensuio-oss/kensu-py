from kensu.pandas import DataFrame
from kensu.utils.kensu_provider import KensuProvider
import sklearn.neighbors as ngb
from kensu.utils.helpers import eventually_report_in_mem


class KNeighborsClassifier(ngb.KNeighborsClassifier):

    def fit(self, X, y):
        X_train = X.get_df()
        y_train = y.get_s()
        result = super(KNeighborsClassifier,self).fit( X_train , y_train )
        kensu = KensuProvider().instance()

        metrics = kensu.extractors.extract_machine_learning_metrics(result,x_train = X_train, y_train = y_train )
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

        attr = [result,'SkLearn.KNeighborsClassifier',metrics,hyperparams]
        self.attr = attr

        return result