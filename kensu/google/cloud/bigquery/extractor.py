import logging
from hashlib import sha256

import pandas as pd
import google
from google.cloud.bigquery import Table
import datetime

import kensu
from kensu.client import *
from kensu.google.cloud.bigquery import Client
from kensu.google.cloud.bigquery.job.bigquery_stats import compute_bigquery_stats
from kensu.utils.dsl.extractors import ExtractorSupport
from kensu.utils.helpers import singleton
from kensu.utils.kensu_provider import KensuProvider


@singleton
class KensuBigQuerySupport(ExtractorSupport):  # should extends some KensuSupport class

    def is_supporting(self, table):
        return isinstance(table, google.cloud.bigquery.table.Table) or \
               isinstance(table, google.cloud.bigquery.table.RowIterator)

    def is_machine_learning(self, df):
        return False

    def skip_wr(self, df):
        if hasattr(df, 'ksu_dest'):
            return getattr(df, 'ksu_dest')
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
        # FIXME: this is dummy default in case ANSI SQL parsing failed, and possibly should be just disabled?
        kensu = KensuProvider().instance()
        client: Client = kensu.data_collectors['BigQuery']
        return compute_bigquery_stats(table, client, stats_aggs=None, input_filters=None)

    # return dict of doubles (stats)
    def extract_stats(self, df):
        df = self.skip_wr(df)
        if isinstance(df, google.cloud.bigquery.table.Table):
            return self.extract_table_stats(df)
        elif isinstance(df, google.cloud.bigquery.table.RowIterator):
            # FIXME?
            return None

    def extract_data_source(self, df, pl, **kwargs):
        df=self.skip_wr(df)
        logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None

        location = self.extract_location(df, kwargs.get("location"))
        fmt = self.extract_format(df, kwargs.get("format"))

        if location is None or fmt is None:
            raise Exception(
                "cannot report new pandas dataframe without location ({}) a format provided ({})!".format(location, fmt))

        ds_pk = DataSourcePK(location=location, physical_location_ref=pl)
        # fixme: copy-paste!
        name = ('/').join(location.split('/')[-2:])
        if logical_naming == 'File':
            logical_category = location.split('/')[-1]
            ds = DataSource(name=name, format=fmt, categories=['logical::'+logical_category], pk=ds_pk)
        else:
            ds = DataSource(name=name, format=fmt, categories=[], pk=ds_pk)
        return ds

    def extract_schema(self, data_source, df):
        df = self.skip_wr(df)
        fields = self.extract_schema_fields(df)
        sc_pk = SchemaPK(data_source.to_ref(), fields=fields)
        schema = Schema(name="schema:"+data_source.name, pk=sc_pk)
        return schema

    def extract_data_source_and_schema(self, df, pl, **kwargs):
        ds = self.extract_data_source(df, pl, **kwargs)
        sc = self.extract_schema(ds, df)
        return ds, sc