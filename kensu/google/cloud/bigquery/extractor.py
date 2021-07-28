from hashlib import sha256

import pandas as pd
import google
from google.cloud.bigquery import Table
import datetime

import kensu
from kensu.client import *
from kensu.google.cloud.bigquery import Client
from kensu.utils.dsl.extractors import ExtractorSupport
from kensu.utils.helpers import singleton
from kensu.utils.kensu_provider import KensuProvider


@singleton
class KensuBigQuerySupport(ExtractorSupport):  # should extends some KensuSupport class

    def is_supporting(self, table):
        return isinstance(table, google.cloud.bigquery.table.Table) or isinstance(df, google.cloud.bigquery.table.RowIterator)
    def is_machine_learning(self, df):
        return False

    def skip_wr(self, df):
        return df

    # return list of FieldDef
    def extract_schema_fields(self, df):
        if isinstance(df, google.cloud.bigquery.table.Table) or isinstance(df, google.cloud.bigquery.table.RowIterator):
            return [FieldDef(name=str(k.name), field_type=k.field_type, nullable=k.is_nullable) for k in df.schema]


    def extract_location(self, df, location):
        # FIXME => what to do for RowIterator?
        if isinstance(df, google.cloud.bigquery.table.Table):
            return "bigquery:/" + df.path
        else:
            return location


    def extract_format(self, df, fmt):
        # FIXME => should do something about RowIterator...
        return "BigQuery Table"

    def tk(self, k, k1): return k + '.' + k1

    def extract_table_stats(self, table: Table):
        r = {
            "nrows": table.num_rows,
        }
        kensu = KensuProvider().instance()
        client: Client = kensu.data_collectors['BigQuery']
        try:
            import requests
            url = kensu.conf.get("sql.util.url")
            metadata = {"tables": []}
            table_id = "`"+table.full_table_id.replace(":",".")+"`"
            table_md = {
                "id": table_id,
                "schema": {
                    "fields" : [ { "name": f.name, "type": f.field_type } for f in table.schema]
                }
            }
            metadata["tables"].append(table_md)
            stats_aggs = requests.post(url + "/stats-criterions", json={"sql": "SQL_NOT_USED_NOR_AVAILABLE_HERE_YET", "metadata": metadata}).json()
            stats_aggs = stats_aggs[table.get_real_name()]
        except:
            stats_aggs = {}
            for f in table.schema:
                # f.field_type is
                # ["STRING", "BYTES",
                # "INTEGER", "INT64",
                # "FLOAT", "FLOAT64",
                # "BOOLEAN", "BOOL",
                # "TIMESTAMP", "DATE", "TIME", "DATETIME", "GEOGRAPHY", "NUMERIC", "BIGNUMERIC",
                # "RECORD", "STRUCT",]
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

        selector = ",".join([v+" "+c+"_"+s for c, vs in stats_aggs.items() for s, v in vs.items()])
        sts = client.query(f"select {selector} from `{str(table.reference)}`")
        sts_result = sts.result()
        stats = None
        for row in sts_result:
            stats = row # there is only one anyway
        for k, vs in stats_aggs.items():
            for s in vs.keys():
                v = stats[k + "_" + s]
                if v.__class__ in [datetime.date, datetime.datetime, datetime.time]:
                    v = int(v.strftime("%s")+"000")
                r[k + "." + s] = v
        return r

    # return dict of doubles (stats)
    def extract_stats(self, df):
        # df = self.skip_wr(df)
        if isinstance(df, google.cloud.bigquery.table.Table):
            return self.extract_table_stats(df)
        elif isinstance(df, google.cloud.bigquery.table.RowIterator):
            # FIXME -> TODO
            return None

    def extract_data_source(self, df, pl, **kwargs):
        logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None

        location = self.extract_location(df, kwargs.get("location"))
        fmt = self.extract_format(df, kwargs.get("format"))

        if location is None or fmt is None:
            raise Exception(
                "cannot report new pandas dataframe without location ({}) a format provided ({})!".format(location, fmt))

        ds_pk = DataSourcePK(location=location, physical_location_ref=pl)
        name = ('/').join(location.split('/')[-2:])
        if logical_naming == 'File':
            logical_category = location.split('/')[-1]
            ds = DataSource(name=name, format=fmt, categories=['logical::'+logical_category], pk=ds_pk)
        else:
            ds = DataSource(name=name, format=fmt, categories=[], pk=ds_pk)
        return ds

    def extract_schema(self, data_source, df):
        fields = self.extract_schema_fields(df)
        sc_pk = SchemaPK(data_source.to_ref(), fields=fields)
        schema = Schema(name="schema:"+data_source.name, pk=sc_pk)
        return schema

    def extract_data_source_and_schema(self, df, pl, **kwargs):
        ds = self.extract_data_source(df, pl, **kwargs)
        sc = self.extract_schema(ds, df)
        return ds, sc