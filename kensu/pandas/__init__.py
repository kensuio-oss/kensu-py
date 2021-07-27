import os
# disable Kensu collector when requested to do so (e.g. inside Apache Spark executor nodes)
if "KSU_DISABLE_PY_COLLECTOR" in os.environ:
    from pandas import *
else:
    import pandas as pd
    from pandas import *

    from .data_frame import DataFrame
    from .data_frame import Series
    from .data_frame import wrap_pandas_reader, wrap_pandas_get_dummies, wrap_merge, wrap_to_datetime
    from .extractor import KensuPandasSupport

    if hasattr(pd, "read_clipboard"):
        read_clipboard = wrap_pandas_reader(pd.read_clipboard)
    if hasattr(pd, "read_csv"):
        read_csv = wrap_pandas_reader(pd.read_csv)
    if hasattr(pd, "read_excel"):
        read_excel = wrap_pandas_reader(pd.read_excel)
    if hasattr(pd, "read_feather"):
        read_feather = wrap_pandas_reader(pd.read_feather)
    if hasattr(pd, "read_fwf"):
        read_fwf = wrap_pandas_reader(pd.read_fwf)
    if hasattr(pd, "read_gbq"):
        read_gbq = wrap_pandas_reader(pd.read_gbq)
    if hasattr(pd, "read_hdf"):
        read_hdf = wrap_pandas_reader(pd.read_hdf)
    if hasattr(pd, "read_html"):
        read_html = wrap_pandas_reader(pd.read_html)
    if hasattr(pd, "read_json"):
        read_json = wrap_pandas_reader(pd.read_json)
    if hasattr(pd, "read_parquet"):
        read_parquet = wrap_pandas_reader(pd.read_parquet)
    if hasattr(pd, "read_pickle"):
        read_pickle = wrap_pandas_reader(pd.read_pickle)
    if hasattr(pd, "read_sas"):
        read_sas = wrap_pandas_reader(pd.read_sas)
    if hasattr(pd, "read_sql"):
        read_sql = wrap_pandas_reader(pd.read_sql)
    if hasattr(pd, "read_sql_query"):
        read_sql_query = wrap_pandas_reader(pd.read_sql_query)
    if hasattr(pd, "read_sql_table"):
        read_sql_table = wrap_pandas_reader(pd.read_sql_table)
    if hasattr(pd, "get_dummies"):
        get_dummies = wrap_pandas_get_dummies(pd.get_dummies)
    if hasattr(pd, "merge"):
        merge = wrap_merge(pd.merge)
    if hasattr(pd, 'to_datetime'):
        to_datetime = wrap_to_datetime(pd.to_datetime)
