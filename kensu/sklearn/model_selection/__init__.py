import logging

from functools import reduce
import pandas as pd
from sklearn import model_selection

from kensu.pandas import DataFrame,Series
from kensu.numpy import ndarray
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.dsl import mapping_strategies
from kensu.utils.helpers import eventually_report_in_mem


def train_test_split(*arrays, **options):
    kensu = KensuProvider().instance()
    are_all_ok = reduce(lambda x, y: x and (isinstance(y, DataFrame) or isinstance(y, ndarray) or isinstance(y, Series)), arrays, True)

    a = []
    b = []
    for element in arrays:
        if isinstance(element, DataFrame):
            a.append(element.get_df())
            b.append(element.get_df())
            b.append(element.get_df())
        elif isinstance(element, Series):
            a.append(element.get_s())
            b.append(element.get_s())
            b.append(element.get_s())
    arrays = tuple(a)

    results = model_selection.train_test_split(*arrays, **options)



    if are_all_ok:

        for df, df_result in list(zip(b, results)):
            orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, df))

            result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(df_result, kensu.default_physical_location_ref))
            result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, df_result))
            if kensu.mapping:
                if isinstance(df_result,pd.Series):
                    col = df_result.name
                    kensu.add_dependencies_mapping(result_sc.to_guid(), col, orig_sc.to_guid(), col, 'split_train_test')

                else:
                    for col in df_result:
                        kensu.add_dependencies_mapping(result_sc.to_guid(),col,orig_sc.to_guid(),col,'split_train_test')
            else:
                kensu.add_dependency((df, orig_ds, orig_sc), (df_result, result_ds, result_sc),
                               mapping_strategy=mapping_strategies.DIRECT)
    else:
        logging.debug("Unsupported types in : " + ", ".join(map(lambda x: x.__class__.__name__, arrays)))
        print("Unsupported types in : " + ", ".join(map(lambda x: x.__class__.__name__, arrays)))


    new_results = []
    for x in results:
        if isinstance(x,pd.DataFrame):
            new_results.append(DataFrame.using(x))
        elif isinstance(x,pd.Series):
            new_results.append(Series.using(x))
        else:
            new_results.append(x)

    return new_results

train_test_split.__doc__ = model_selection.train_test_split.__doc__