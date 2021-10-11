from kensu.mlflow.tracking import MlflowClient
from kensu.pandas import DataFrame
from kensu.utils.helpers import eventually_report_in_mem
from kensu.utils.kensu_provider import KensuProvider
import mlflow.pyfunc as mlp
import mlflow
from mlflow.pyfunc import *
from kensu.client import DataSourcePK, DataSource, Schema, SchemaPK, FieldDef

def wrap_log_model(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        result = method(*args, **kwargs)

        if 'python_model' in kwargs:
            model_list = []
            python_model = kwargs['python_model']
            python_model_dict = python_model.__dict__
            for attribute in python_model_dict:
                potential_model = python_model_dict[attribute]
                if ('kensu.sklearn') in str(potential_model.__class__):
                    model_list.append(potential_model)

            run_id = mlflow.tracking.fluent._get_or_start_run().info.run_id
            model_log_location = 'runs:/' + run_id + '/' + args[0]
            model_log_location = mlflow.get_artifact_uri(args[0])

            i = 0
            for model in model_list:
                i += 1
                if ('kensu.sklearn') in str(potential_model.__class__):
                    fmt = 'Sklearn Model'

                    orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(model.attr[0], kensu.default_physical_location_ref,
                                                                 logical_naming=kensu.logical_naming,format=fmt))
                    orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, model.attr[0]))

                    location = model_log_location +'/part-'+str(i)

                    result_ds = kensu.extractors.extract_data_source(model.attr[0], kensu.default_physical_location_ref, location = location,
                                                                   logical_naming=kensu.logical_naming,format=fmt)._report()
                    result_sc = kensu.extractors.extract_schema(result_ds, model.attr[0])._report()

                    kensu.register_alias(ref_guid=orig_sc.to_guid(), alias_guid=result_sc.to_guid())
                    kensu.real_schema_df[result_sc.to_guid()] = model
                    kensu.model[result_sc.to_guid()] = model.attr

                    #TODO create mlflow extractor
                    from mlflow.pyfunc import PythonModel
                    if python_model.__class__ in PythonModel.__subclasses__():
                        ds_pk = DataSourcePK(location=model_log_location,
                                             physical_location_ref=kensu.default_physical_location_ref)
                        name = args[0]
                        fields = [
                            FieldDef(name="intercept_", field_type="float", nullable=False),
                            FieldDef(name="coef_", field_type="array<float>", nullable=False)
                        ]
                        logged_ds = DataSource(name=name,categories=['logical::'+name], format='MLFlow', pk=ds_pk)._report()
                        sc_pk = SchemaPK(logged_ds.to_ref(),
                                         fields=fields)
                        logged_sc = Schema(name="schema:" + logged_ds.name, pk=sc_pk)._report()
                        kensu.real_schema_df[logged_sc.to_guid()] = None

                        columns_ins = [k.name for k in result_sc.pk.fields]
                        columns_out = [k.name for k in logged_sc.pk.fields]

                        for col_in in columns_ins:
                            for col_out in columns_out:
                                kensu.add_dependencies_mapping(logged_sc.to_guid(), col_out, result_sc.to_guid(),
                                                                str(col_in), "LOG model")

            kensu.report_with_mapping()

        return result

    wrapper.__doc__ = method.__doc__
    return wrapper
log_model = wrap_log_model(mlp.log_model)

def wrap_load_model(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        result = method(*args, **kwargs)
        client = MlflowClient()
        run_id = result.metadata.to_dict()['run_id']
        model_uri = client.get_run(run_id).info.artifact_uri

        if args[0].startswith('models'):
            model_env = args[0].split('/')[-1].lower()
            model_name = args[0].split('/')[-2].lower()
            for el in client.get_registered_model(model_name).latest_versions:
                if el.source.startswith(model_uri):
                    version = el.version

                    model_uri = [model_uri]
                    model_uri.append(model_name)
                    model_uri.append('version' + str(version))
                    model_uri.append(str(model_env).lower())
                    model_ds_location = ('/').join(model_uri)
        else:
            model_ds_location = model_uri

        result.__class__ =PyFuncModel
        result.kensu_model_origin = model_ds_location
        return result
    wrapper.__doc__ = method.__doc__
    return wrapper
load_model = wrap_load_model(mlp.load_model)

class PyFuncModel(mlp.PyFuncModel):
    kensu_model_origin = None

    def predict(self, data: PyFuncInput) -> PyFuncOutput:
        if isinstance(data,DataFrame):
            data = data.get_df()
        result = super(PyFuncModel, self).predict(data)

        kensu = KensuProvider().instance()
        X_test_ds = eventually_report_in_mem(
            kensu.extractors.extract_data_source(data, kensu.default_physical_location_ref))
        X_test_sc = eventually_report_in_mem(kensu.extractors.extract_schema(X_test_ds, data))

        result_ds = kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref)
        result_sc = kensu.extractors.extract_schema(result_ds, result)

        ds_pk = DataSourcePK(location=self.kensu_model_origin,
                             physical_location_ref=kensu.default_physical_location_ref)

        fields = [
            FieldDef(name="intercept_", field_type="float", nullable=False),
            FieldDef(name="coef_", field_type="array<float>", nullable=False)
        ]
        model_ds = DataSource(name=self.kensu_model_origin.split('/')[-3],format="MLFlow",pk=ds_pk)._report()
        sc_pk = SchemaPK(model_ds.to_ref(),
                         fields=fields)
        model_sc = Schema(name="schema:" + model_ds.name, pk=sc_pk)._report()

        if kensu.mapping:
            for result_col in [s.name for s in result_sc.pk.fields]:
                for col in [s.name for s in X_test_sc.pk.fields]:
                    kensu.add_dependencies_mapping(result_sc.to_guid(), result_col, X_test_sc.to_guid(), col,
                                                   'Model Predict')
                if model_sc is not None:
                    for col in [s.name for s in model_sc.pk.fields]:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), result_col, model_sc.to_guid(), col,
                                                       'Model Predict')
        kensu.real_schema_df[model_sc.to_guid()] = None
        return result