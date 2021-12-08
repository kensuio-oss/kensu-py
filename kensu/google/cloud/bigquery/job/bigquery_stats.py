import decimal
import logging
import datetime
import re

logger = logging.getLogger(__name__)

from kensu.google.cloud.bigquery import Client
from kensu.utils.kensu_provider import KensuProvider


def compute_bigquery_stats(table_ref=None, table=None, client=None, stats_aggs=None, input_filters=None, query=None):
    if None == query == table_ref:
        raise Exception("compute_bigquery_stats requires either a table_ref or a query")
    r = {}
    kensu = KensuProvider().instance()
    client: Client = client or kensu.data_collectors['BigQuery']
    if stats_aggs is None:
        logger.debug('Got empty statistic listing from remote service, proceeding with fallback statistic list')
        stats_aggs = generate_fallback_stats_queries(table)

    from kensu.google.cloud.bigquery.extractor import KensuBigQuerySupport

    unnest = KensuBigQuerySupport().extract_unnest(client.get_table(table_ref))

    # TODO Add nullvalue computation for REPEATED
    schema = KensuBigQuerySupport().extract_schema_fields(client.get_table(table_ref))
    non_nullable = [k.name for k in schema if k.nullable == False]
    unsupported_stats = [k.name for k in schema if k.name.count(".")>0]

    for key in non_nullable + unsupported_stats:
        if key in stats_aggs:
            stats_aggs.pop(key)


    # "dots in schemas are not supported in BigQuery,
    # as a workaround we flatten the schema and replace the infix dots with a "ksu" string.
    # once the stats computation has done is job we convert back to the dotted notation for displaying stats"

    selector = ",".join([sql_aggregation + " " + col.replace(".","__ksu__") + "_" + stat_name
                         for col, stats_for_col in stats_aggs.items()
                         for stat_name, sql_aggregation in stats_for_col.items()])

    for nested in sorted(unnest,key=len,reverse=True):
        if "." in nested:
            selector=selector.replace(nested,nested.replace(".","__ksu__"))

    filters = ''
    if input_filters is not None and len(input_filters) > 0:
        filters = f"WHERE {' AND '.join(input_filters)}"
    if unnest != []:
        list_unnest =[]
        for el in unnest:
            list_unnest.append(f",UNNEST({el}) AS {el.replace('.','__ksu__')}")

    #This needs to be adapted i we need RECORD stats
    #i.e. with unnest = "".join(list_unnest) if unnest != [] else ''

    unnest =''
    if query:
        stats_query = f"select {selector}, sum(1) as nrows from ({query}){unnest}"
    elif table_ref:
        stats_query = f"select {selector}, sum(1) as nrows from `{str(table_ref)}`{unnest} {filters}"
    #TODO extract this and add to dim-sql and fallback stats
    stats_query = stats_query.replace("sum(case","COUNTIF(").replace("when null then 1 else 0 end)","IS NULL)").replace("when true then 1 else 0 end)","IS TRUE)")

    logger.debug(f"stats query for table {table_ref}: {stats_query}")
    from google.cloud.bigquery.job import QueryJobConfig
    job_conf = QueryJobConfig(labels = {'kensu':'kensu_stats_computation'})
    for row in client.query(stats_query, job_config = job_conf ).result():
        # total num rows (independent of column)
        #FIXME : What about this?
        if row.get('nrows'):
            r['nrows'] = row['nrows']
        # extract column specific stats
        for col, stat_names in stats_aggs.items():
            for stat_name in stat_names.keys():
                v = row[col.replace(".","__ksu__") + "_" + stat_name]
                if v.__class__ in [datetime.date, datetime.datetime, datetime.time]:
                    v = int(v.strftime("%s") + "000")
                if v.__class__ in [decimal.Decimal]:
                    v = float(v)
                if v is None:
                    v = 0
                r[(col + "." + stat_name).replace("__ksu__",".")] = v
        break  # there should be only one row here
    return r


def generate_fallback_stats_queries(table):
    stats_aggs = {}

    from kensu.google.cloud.bigquery.extractor import KensuBigQuerySupport
    schema = KensuBigQuerySupport().extract_schema_fields(table)

    for f in schema:
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
        elif f.field_type in ["STRING"]:
            stats_aggs[f.name] = {"levels": f"count(distinct {f.name})",
                                  "nullrows": f"sum(case {f.name} when null then 1 else 0 end)"}

    return stats_aggs
