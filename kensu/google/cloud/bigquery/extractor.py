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
from kensu.utils.helpers import singleton, to_datasource
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
            schema_field = []
            def convert_fields(fields,heritage=[]):
                for k in fields:
                    if k.fields != ():
                        convert_fields(k.fields,heritage + [k.name])
                    else:
                        if heritage !=[]:
                            prefix = ".".join(heritage)+'.'
                        else:
                            prefix=''
                        schema_field.append(FieldDef(name=prefix+str(k.name), field_type=k.field_type, nullable=k.is_nullable))
            convert_fields(df.schema)
            return schema_field

    def extract_unnest(self, df):
        if isinstance(df, google.cloud.bigquery.table.Table) or isinstance(df, google.cloud.bigquery.table.RowIterator):
            unnest = []

            def convert_fields(fields, heritage=[]):
                for k in fields:
                    if k.field_type == 'RECORD' and k.is_nullable == False:
                        #if ".".join(heritage) not in unnest_candidate:
                        if len(heritage)<1:
                            unnest.append(".".join(heritage+[k.name]))
                        #unnest_candidate.append(".".join(heritage+[k.name]))
                        convert_fields(k.fields,  heritage + [k.name])
                    elif  k.field_type == 'RECORD':
                        convert_fields(k.fields, heritage + [k.name])
                    else:
                        None

            convert_fields(df.schema)
            return unnest

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

    # return dict of doubles (stats)
    def extract_stats(self, df):
        # stats definitions are computed directly in wrapper in more efficient fashion, see `query.py`
        return None

    def extract_data_source(self, df, pl, **kwargs):
        # FIXME: is this not used?
        df=self.skip_wr(df)
        logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None

        location = self.extract_location(df, kwargs.get("location"))
        fmt = self.extract_format(df, kwargs.get("format"))

        if location is None or fmt is None:
            raise Exception(
                "cannot report new bigquery dataframe without location ({}) a format provided ({})!".format(location, fmt))

        ds_pk = DataSourcePK(location=location, physical_location_ref=pl)
        name = ('/').join(location.split('/')[-2:])
        return to_datasource(ds_pk=ds_pk, format=fmt, location=location, logical_naming=logical_naming, name=name)


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