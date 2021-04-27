
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.dsl import mapping_strategies


def wrap_pandas_gbq_write(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        df_result = method(*args, **kwargs)
        df = args[0]  # see get_dummies definition (first arg is `data`)

        orig_ds = kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming)._report()
        orig_sc = kensu.extractors.extract_schema(orig_ds, df)._report()

        result_ds = kensu.extractors.extract_data_source(df_result, kensu.default_physical_location_ref,
                                                       logical_naming=kensu.logical_naming)._report()
        result_sc = kensu.extractors.extract_schema(result_ds, df_result)._report()

        df_result_kensu = DataFrame.using(df_result)

        kensu.add_dependency((df, orig_ds, orig_sc), (df_result, result_ds, result_sc),
                           mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

        return df_result_kensu

    wrapper.__doc__ = method.__doc__
    return wrapper