import numpy
import sklearn.metrics as skm
from kensu.utils.helpers import eventually_report_in_mem
from kensu.utils.wrappers import remove_ksu_wrappers
from kensu.utils.kensu_provider import KensuProvider
from kensu.numpy import ndarray
from kensu.pandas import DataFrame,Series
from kensu.client.models import DataSource,DataSourcePK,Schema,SchemaPK,FieldDef

def wrap_roc_auc_score(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        from kensu.utils.helpers import new_arg
        new_args = new_arg(args)
        result = method(*new_args, **kwargs)

        location = "in-memory-data://metrics"
        fmt = "Metric"

        ds_pk = DataSourcePK(location=location, physical_location_ref=kensu.default_physical_location_ref)
        name = "Metrics"
        result_ds = DataSource(name=name, format=fmt, pk=ds_pk)._report()
        sc_pk = SchemaPK(result_ds.to_ref(), fields=[FieldDef(name='ROC', field_type='np.float', nullable=True)])
        result_sc = Schema(name="schema:" + result_ds.name, pk=sc_pk)._report()
        kensu.real_schema_df[result_sc.to_guid()] = {'AUC':result}


        for df in args:
            input_ds = eventually_report_in_mem(
                kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming))
            input_sc = eventually_report_in_mem(kensu.extractors.extract_schema(input_ds, df))

            #if numpy.array_equal(df,new_args[1]):
                # input_ds._report()
                # input_sc._report()
                # kensu.real_schema_df[input_sc.to_guid()] = df


            result_col = 'AUC'
            columns_ins = [k.name for k in input_sc.pk.fields]

            for col in columns_ins:
                    kensu.add_dependencies_mapping(result_sc.to_guid(), result_col, input_sc.to_guid(),
                                                       str(col), "Metric computation")

        return result

    wrapper.__doc__ = method.__doc__
    return wrapper


def wrap_classification(method):
    def wrapper(*args, **kwargs):
        new_args=remove_ksu_wrappers(args)
        result = method(*new_args, **kwargs)
        return result

    wrapper.__doc__ = method.__doc__
    return wrapper

roc_auc_score = wrap_roc_auc_score(skm.roc_auc_score)

classification_report = wrap_classification(skm.classification_report)