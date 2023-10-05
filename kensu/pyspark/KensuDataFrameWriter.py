import sys
from typing import overload, Dict, List, Optional, Tuple, TYPE_CHECKING, Union

from pyspark.sql.utils import to_str

from pyspark.sql.dataframe import DataFrameWriter

if TYPE_CHECKING:
    from pyspark.sql._typing import OptionalPrimitiveType
    from pyspark.sql.dataframe import DataFrame

__all__ = ["KensuDataFrameWriter"]

PathOrPaths = Union[str, List[str]]
TupleOrListOfString = Union[List[str], Tuple[str, ...]]


# limitation: partition columns are not supported for LDS name for remote config

class KensuDataFrameWriter:

    def __init__(self, df: "DataFrame"):
        self._df = df
        self._spark = df.sparkSession
        self._df_writer = DataFrameWriter(df)  # mutable as we modify df at last moment before write
        self._delayed_calls = []
        self._options = {}

    # FIXME: implement  __getattr__(self, item) for unknown field names to defer to self._df_writer

    def _delay_fn_call(self, fn):
        self._delayed_calls.append(fn)
        return self

    def _update_df(self, new_df):
        self._df = new_df
        self._df_writer = DataFrameWriter(new_df)

    def _call_deferred_fns(self):
        # always returns same self, so it's fine
        for fn in self._delayed_calls:
            fn()

    @staticmethod
    def _path_from_args(args, kwargs):
        """
        Allow to call methods:
        - .parquet("abc.parquet") - args
        - .parquet("abc.parquet", mode="overwrite") - args + kwargs
        - .parquet(path="abc.parquet") - kwargs
        - .parquet(mode="overwrite", path="abc.parquet") - kwargs in weird order - wouldn't work with `def parquet(path, *args, **kwrags)`

        :return: path for first arg or from kwargs
        """
        return kwargs.get('path') or (args and args[0])

    def mode(self, saveMode: Optional[str]) -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.mode(saveMode))
        return self

    def format(self, source: str) -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.format(source))
        return self

    def option(self, key: str, value: "OptionalPrimitiveType") -> "KensuDataFrameWriter":
        self._options[key] = value
        self._delay_fn_call(lambda: self._df_writer.option(key, to_str(value)))
        return self

    def options(self, **options: "OptionalPrimitiveType") -> "KensuDataFrameWriter":
        self._options.update(options)
        self._delay_fn_call(lambda: self._df_writer.options(**options))
        return self

    def _path_from_options(self):
        return self._options.get('path')

    def _format_from_options(self):
        return self._options.get('format')

    @overload
    def partitionBy(self, *cols: str) -> "KensuDataFrameWriter":
        ...

    @overload
    def partitionBy(self, *cols: List[str]) -> "KensuDataFrameWriter":
        ...

    def partitionBy(self, *cols: Union[str, List[str]]) -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.partitionBy(*cols))
        return self

    @overload
    def bucketBy(self, numBuckets: int, col: str, *cols: str) -> "KensuDataFrameWriter":
        ...

    @overload
    def bucketBy(self, numBuckets: int, col: TupleOrListOfString) -> "KensuDataFrameWriter":
        ...

    def bucketBy(
        self, numBuckets: int, col: Union[str, TupleOrListOfString], *cols: Optional[str]
    ) -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.bucketBy(numBuckets, col, *cols))
        return self

    @overload
    def sortBy(self, col: str, *cols: str) -> "KensuDataFrameWriter":
        ...

    @overload
    def sortBy(self, col: TupleOrListOfString) -> "KensuDataFrameWriter":
        ...

    def sortBy(
        self, col: Union[str, TupleOrListOfString], *cols: Optional[str]
    ) -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.sortBy(col, *cols))
        return self

    def _handle_simple_save(self,
                            path: Optional[str] = None,
                            format: Optional[str] = None,
                            table_name: Optional[str] = None
                            ):
        if path is None:
            path = self._path_from_options()
        if path is not None:
            df = self._df
            try:
                from kensu.pyspark.spark_connector import addOutputObservationsWithRemoteConf
                kensu_efficient_write_compute_count_distinct = False  # FIXME: configure in a different way, if needed
                import logging
                logging.info("KENSU: DataFrameWriter for output path={} table_name={} format={}, will be automatically updated with Kensu observations via .observe() using remote config if enabled".format(path, table_name, format))
                df = addOutputObservationsWithRemoteConf(df,
                                                         path=path,
                                                         table_name=table_name,
                                                         format=format,
                                                         compute_count_distinct=kensu_efficient_write_compute_count_distinct)
                logging.info("KENSU: DataFrameWriter for output path={}  table_name={} format={}, was updated with Kensu observations via .observe() using remote config if enabled".format(path, table_name, format))
            except:
                import traceback
                import logging
                logging.info(
                    "KENSU: unexpected issue when adding output observations to output path={}  table_name={} format={}, are you using old kensu Jar?: {}".format(
                        path, table_name, format,
                        traceback.format_exc()))
            self._update_df(df)
        self._call_deferred_fns()

    def save(
        self,
        path: Optional[str] = None,
        format: Optional[str] = None,
        mode: Optional[str] = None,
        partitionBy: Optional[Union[str, List[str]]] = None,
        **options: "OptionalPrimitiveType",
    ) -> None:
        self._handle_simple_save(path, format or self._format_from_options())
        return self._df_writer.save(path=path, format=format, mode=mode, partitionBy=partitionBy, **options)

    def insertInto(self, tableName: str, overwrite: Optional[bool] = None) -> None:
        self._handle_simple_save(path=None, table_name=tableName)
        return self._df_writer.insertInto(tableName, overwrite)

    def saveAsTable(
        self,
        name: str,
        format: Optional[str] = None,
        mode: Optional[str] = None,
        partitionBy: Optional[Union[str, List[str]]] = None,
        **options: "OptionalPrimitiveType",
    ) -> None:
        self._handle_simple_save(path=None, table_name=name, format=format or self._format_from_options())
        return self._df_writer.saveAsTable(name=name, format=format, mode=mode, partitionBy=partitionBy, **options)

    def json(self, *args, **kwargs) -> None:
        self._handle_simple_save(path=self._path_from_args(args, kwargs), format="json")
        return self._df_writer.json(*args, **kwargs)

    def parquet(self, *args, **kwargs) -> None:
        self._handle_simple_save(path=self._path_from_args(args, kwargs), format="parquet")
        return self._df_writer.parquet(*args, **kwargs)

    def text(self, *args, **kwargs) -> None:
        self._handle_simple_save(path=self._path_from_args(args, kwargs), format="text")
        return self._df_writer.text(*args, **kwargs)

    def csv(self, *args, **kwargs) -> None:
        self._handle_simple_save(path=self._path_from_args(args, kwargs), format="csv")
        return self._df_writer.csv(*args, **kwargs)

    def orc(self, *args, **kwargs) -> None:
        self._handle_simple_save(path=self._path_from_args(args, kwargs), format="orc")
        return self._df_writer.orc(*args, **kwargs)

    def jdbc(
        self,
        url: str,
        table: str,
        mode: Optional[str] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> None:
        # FIXME: impl observe
        return self._df_writer.jdbc(url=url, table=table, mode=mode, properties=properties)
