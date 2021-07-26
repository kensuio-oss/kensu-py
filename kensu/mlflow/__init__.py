import mlflow as ml
from mlflow import *


import kensu.mlflow.pyfunc as pyfunc
from kensu.client import DataSourcePK, FieldDef, DataSource, SchemaPK, Schema
from kensu.pandas import DataFrame

from kensu.utils.helpers import eventually_report_in_mem
from kensu.utils.kensu_provider import KensuProvider


def wrap_register(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        result = method(*args, **kwargs)
        model_name = args[1]
        orig_ds_location = result.source

        ds_pk = DataSourcePK(location=orig_ds_location,
                             physical_location_ref=kensu.default_physical_location_ref)
        name = result.source.split('/')[-1]

        fields = [
            FieldDef(name="intercept_", field_type="float", nullable=False),
            FieldDef(name="coef_", field_type="array<float>", nullable=False)
        ]

        orig_ds = DataSource(name=name,categories=['logical::'+name], format='MLFlow', pk=ds_pk)._report()
        sc_pk = SchemaPK(orig_ds.to_ref(),
                         fields=fields)
        orig_sc = Schema(name="schema:" + orig_ds.name, pk=sc_pk)._report()
        kensu.real_schema_df[orig_sc.to_guid()] = None

        #We create a file location based on the run location and the new model artifact
        model_artifact_loc = result.source.split('/')[:-1]
        model_artifact_loc.append(model_name)
        model_artifact_loc.append('version'+str(result.version))
        model_ds_location = ('/').join(model_artifact_loc)

        result_pk = DataSourcePK(location=model_ds_location,
                             physical_location_ref=kensu.default_physical_location_ref)
        result_ds = DataSource(name=model_name,categories=['logical::'+model_name],format = 'MLFlow',pk=result_pk)._report()
        sc_pk = SchemaPK(result_ds.to_ref(),
                         fields=fields)
        result_sc = Schema(name="schema:" + result_ds.name, pk=sc_pk)._report()

        columns_ins = [k.name for k in orig_sc.pk.fields]
        columns_out = [k.name for k in result_sc.pk.fields]

        kensu.real_schema_df[result_sc.to_guid()] = None

        for col_in in columns_ins:
            kensu.add_dependencies_mapping(result_sc.to_guid(), col_in, orig_sc.to_guid(),
                                                str(col_in), "Register model")

        kensu.report_with_mapping()

        return result

    wrapper.__doc__ = method.__doc__
    return wrapper
register_model = wrap_register(ml.register_model)

