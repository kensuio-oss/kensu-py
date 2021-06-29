from kensu.client import *
from kensu.utils.dsl.extractors import ExtractorSupport
from kensu.utils.helpers import singleton
from hashlib import sha256


@singleton
class KensuSKLearnSupport(ExtractorSupport):
    def is_supporting(self, m):
        return m.__class__.__module__.startswith("sklearn") or m.__class__.__module__.startswith("kensu.sklearn")

    def is_machine_learning(self, df):
        return True  # FIXME... this is quite abusive

    # return dict of doubles (stats)
    def extract_stats(self, m):
        # todo (ideas): hist coefs. Or batch several runs and keep stats per coeff
        return {}

    def extract_machine_learning_info(self, m):
        return {
            "name": m.__class__.__module__ + "." + m.__class__.__name__
        }

    # FIXME: this is only for LinearRegression...
    def extract_schema(self, data_source, model):
        fields = [
            FieldDef(name="intercept_", field_type="float", nullable=False),
            FieldDef(name="coef_", field_type="array<float>", nullable=False)
        ]
        sc_pk = SchemaPK(data_source.to_ref(), fields=fields)
        schema = Schema(name="schema:" + data_source.name, pk=sc_pk)
        return schema



    def extract_location(self, model, location):

        if location is not None:
            return location
        else:
            try:
                return "in-mem://model/" + sha256(str(model.coef_).encode("utf-8")).hexdigest() + '/in-mem-transformation'
            except:
                return "in-mem://model/" + sha256(
                    str(model.leaf_size).encode("utf-8")).hexdigest() + '/in-mem-transformation'



    def extract_data_source(self, model, pl, **kwargs):
        logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None

        location = self.extract_location(model, kwargs.get("location"))
        fmt = kwargs["format"] if 'format' in kwargs else 'Model'

        if location is None or fmt is None:
            raise Exception(
                "cannot report new model dataframe without location ({}) a format provided ({})!".format(location,
                                                                                                          fmt))

        ds_pk = DataSourcePK(location=location, physical_location_ref=pl)
        name = ('/').join(location.split('/')[-3:])
        if logical_naming == 'File':
            logical_category = location.split('/')[-1]
            ds = DataSource(name=name, format=fmt, categories=['logical::' + logical_category], pk=ds_pk)
        else:
            ds = DataSource(name=name, format=fmt, categories=[], pk=ds_pk)
        return ds


    # FIXME
    #  THIS can be extended, refactored, ...
    def extract_machine_learning_metrics(self, m, **kwargs):
        from sklearn import metrics
        from kensu.sklearn.metrics import classification_report

        def compute_metrics(X_name,y_name,prefix='train.'):
            ml_metrics = {}
            if 'classification' in kwargs:
                classification = kwargs['classification']
            else:
                classification = False

            if y_name in kwargs and X_name in kwargs:
                x = kwargs[X_name]
                y = kwargs[y_name]

                if classification:
                    import pandas
                    pred_y = m.predict(x)
                    e=classification_report(y,pred_y,output_dict=True)
                    df = pandas.json_normalize(e, sep='.')
                    ml_metrics = (df.to_dict(orient='records')[0])
                    return ml_metrics

                else:
                    # FIXME... what is m has no predict function
                    pred_y = m.predict(x).get_nd()
                    # This pretty much for regression
                    # regression : http://scikit-learn.org/stable/modules/model_evaluation.html
                    try :
                        ml_metrics = {
                        #prefix+"score": m.score(x, y),
                        prefix+"explained_variance": metrics.explained_variance_score(pred_y, y),
                        prefix+"neg_mean_absolute_error": metrics.mean_absolute_error(pred_y, y),
                        prefix+"neg_mean_squared_error": metrics.mean_squared_error(pred_y, y),
                        prefix+"neg_mean_squared_log_error": metrics.mean_squared_log_error(pred_y, y),
                        prefix+"neg_median_absolute_error": metrics.median_absolute_error(pred_y, y),
                        prefix+"r2": metrics.r2_score(pred_y, y)
                        }
                    except :
                        ml_metrics = None
                    return ml_metrics

        m1= compute_metrics('x_test','y_test',prefix='test')
        m2= compute_metrics('x_train', 'y_train')
        m_total = {}

        if bool(m1):
            m_total.update(m1)
        if bool(m2):
            m_total.update(m2)
        return m_total


    def extract_machine_learning_hyper_parameters(self, m):
        return m.get_params()
