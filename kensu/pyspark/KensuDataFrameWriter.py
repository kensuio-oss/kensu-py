import sys
from typing import cast, overload, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING, Union

from py4j.java_gateway import JavaClass, JavaObject

from pyspark import RDD, since
from pyspark.sql.column import _to_seq, _to_java_column, Column
from pyspark.sql.types import StructType
from pyspark.sql import utils
from pyspark.sql.utils import to_str

from pyspark.sql.dataframe import DataFrameWriter

if TYPE_CHECKING:
    from pyspark.sql._typing import OptionalPrimitiveType, ColumnOrName
    from pyspark.sql.session import SparkSession
    from pyspark.sql.dataframe import DataFrame
    from pyspark.sql.streaming import StreamingQuery

__all__ = ["KensuDataFrameWriter"]

PathOrPaths = Union[str, List[str]]
TupleOrListOfString = Union[List[str], Tuple[str, ...]]


# limitation: partition columns are not supported for LDS name for remote config

class KensuDataFrameWriter:
    """
    Interface used to write a :class:`DataFrame` to external storage systems
    (e.g. file systems, key-value stores, etc). Use :attr:`DataFrame.write`
    to access this.

    .. versionadded:: 1.4.0

    .. versionchanged:: 3.4.0
        Supports Spark Connect.
    """

    def __init__(self, df: "DataFrame"):
        self._df = df
        self._spark = df.sparkSession
        self._df_writer = DataFrameWriter(df)  # mutable as we modify df at last moment before write
        self._delayed_calls = []

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


    def mode(self, saveMode: Optional[str]) -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.mode(saveMode))
        return self

    def format(self, source: str) -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.format(source))
        return self

    def option(self, key: str, value: "OptionalPrimitiveType") -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.option(key, to_str(value)))
        return self

    def options(self, **options: "OptionalPrimitiveType") -> "KensuDataFrameWriter":
        self._delay_fn_call(lambda: self._df_writer.options(**options))
        return self

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

    def _handle_simple_format_save(self,
                                   path: Optional[str] = None,
                                   format: Optional[str] = None
                                   ):
        # is format needed?
        if path is not None:
            # FIXME: impl observe
            pass
        df = self._df
        try:
            from kensu.pyspark.spark_connector import addOutputObservationsWithRemoteConf
            kensu_efficient_write_compute_count_distinct = False  # FIXME: configure in a different way, if needed
            import logging
            logging.info("KENSU: DataFrameWriter for output path={} format={}, will be automatically updated with Kensu observations via .observe() using remote config if enabled".format(path, format))
            df = addOutputObservationsWithRemoteConf(df,
                                                     path=path,
                                                     qualified_table_name=None,
                                                     compute_count_distinct=kensu_efficient_write_compute_count_distinct)
            logging.info("KENSU: DataFrameWriter for output path={} format={}, was updated with Kensu observations via .observe() using remote config if enabled".format(path, format))
        except:
            import traceback
            import logging
            logging.info(
                "KENSU: unexpected issue when adding output observations, are you using old kensu Jar?: {}".format(
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
        self._handle_simple_format_save(path, format)
        return self._df_writer.save(path=path, format=format, mode=mode, partitionBy=partitionBy, **options)


    def insertInto(self, tableName: str, overwrite: Optional[bool] = None) -> None:
        # fixme: impl observe
        return self._df_writer.insertInto(tableName, overwrite)

    def saveAsTable(
        self,
        name: str,
        format: Optional[str] = None,
        mode: Optional[str] = None,
        partitionBy: Optional[Union[str, List[str]]] = None,
        **options: "OptionalPrimitiveType",
    ) -> None:
        # fixme: impl observe
        return self._df_writer.saveAsTable(name=name, format=format, mode=mode, partitionBy=partitionBy, **options)

    def json(self, path: str, *args, **kwargs) -> None:
        self._handle_simple_format_save(path, format="json")
        return self._df_writer.json(path, *args, **kwargs)

    def parquet(self, path: str, *args, **kwargs) -> None:
        self._handle_simple_format_save(path, format="parquet")
        return self._df_writer.parquet(path=path, *args, **kwargs)

    def text(self, path: str, *args, **kwargs) -> None:
        self._handle_simple_format_save(path, format="text")
        return self._df_writer.text(path=path, compression=compression, lineSep=lineSep)

    def csv(self, path: str, *args, **kwargs) -> None:
        self._handle_simple_format_save(path, format="csv")
        return self._df_writer.csv(path, *args, **kwargs)

    def orc(self, path: str, *args, **kwargs) -> None:
        self._handle_simple_format_save(path, format="orc")
        return self._df_writer.orc(path, *args, **kwargs)

    def jdbc(
        self,
        url: str,
        table: str,
        mode: Optional[str] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> None:
        # FIXME: impl observe
        return self._df_writer.jdbc(url=url, table=table, mode=mode, properties=properties)
