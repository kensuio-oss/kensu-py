import logging
import datetime

from kensu.google.cloud.bigquery import Client
from kensu.utils.kensu_provider import KensuProvider


def compute_bigquery_stats(table_ref, table, client, stats_aggs, input_filters=None):
    r = {}
    kensu = KensuProvider().instance()
    client: Client = client or kensu.data_collectors['BigQuery']
    if stats_aggs is None:
        logging.debug('Got empty statistic listing from remote service, proceeding with fallback statistic list')
        stats_aggs = generate_fallback_stats_queries(table)

    selector = ",".join([sql_aggregation + " " + col + "_" + stat_name
                         for col, stats_for_col in stats_aggs.items()
                         for stat_name, sql_aggregation in stats_for_col.items()])
    filters = ''
    if input_filters is not None and len(input_filters) > 0:
        filters = f"WHERE {' AND '.join(input_filters)}"
    stats_query = f"select {selector}, sum(1) as nrows from `{str(table_ref)}` {filters}"
    logging.debug(f"stats query for table {table_ref}: {stats_query}")
    for row in client.query(stats_query).result():
        # total num rows (independent of column)
        r['nrows'] = row['nrows']
        # extract column specific stats
        for col, stat_names in stats_aggs.items():
            for stat_name in stat_names.keys():
                v = row[col + "_" + stat_name]
                if v.__class__ in [datetime.date, datetime.datetime, datetime.time]:
                    v = int(v.strftime("%s") + "000")
                r[col + "." + stat_name] = v
        break  # there should be only one row here
    return r


def generate_fallback_stats_queries(table):
    stats_aggs = {}
    for f in table.schema:
        # f.field_type is
        # ["STRING", "BYTES",
        # "INTEGER", "INT64",
        # "FLOAT", "FLOAT64",
        # "BOOLEAN", "BOOL",
        # "TIMESTAMP", "DATE", "TIME", "DATETIME", "GEOGRAPHY", "NUMERIC", "BIGNUMERIC",
        # "RECORD", "STRUCT",]
        # FIXME: decimal
        if f.field_type in ["INTEGER", "INT", "FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"]:
            stats_aggs[f.name] = {"min": f"min({f.name})",
                                  "max": f"max({f.name})",
                                  "mean": f"avg({f.name})",
                                  "nullrows": f"sum(case {f.name} when null then 1 else 0 end)"}
        elif f.field_type in ["TIMESTAMP", "DATE", "TIME", "DATETIME"]:
            stats_aggs[f.name] = {"min": f"min({f.name})",
                                  "max": f"max({f.name})",
                                  "nullrows": f"sum(case {f.name} when null then 1 else 0 end)"}
        elif f.field_type in ["BOOLEAN", "BOOL"]:
            stats_aggs[f.name] = {"true": f"sum(case {f.name} when true then 1 else 0 end)",
                                  "nullrows": f"sum(case {f.name} when null then 1 else 0 end)"}
    return stats_aggs
