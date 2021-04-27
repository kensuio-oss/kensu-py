from hashlib import sha256

import pandas as pd
import google

import kensu
from kensu.client import *
from kensu.utils.dsl.extractors import ExtractorSupport
from kensu.utils.helpers import singleton

@singleton
class KensuBigQuerySupport(ExtractorSupport):  # should extends some KensuSupport class

    def is_supporting(self, table):
        return isinstance(table, google.cloud.bigquery.table.Table)

    def is_machine_learning(self, df):
        return False

    def skip_wr(self, df):
        return df

    # return list of FieldDef
    def extract_schema_fields(self, df):
        if isinstance(df, google.cloud.bigquery.table.Table):
            return [FieldDef(name=str(k.name), field_type=k.field_type, nullable=k.is_nullable) for k in df.schema]


    def extract_location(self, df, location):
        return location


    def extract_format(self, df, fmt):
        return "BigQuery Table"

    def tk(self, k, k1): return k + '.' + k1

    # return dict of doubles (stats)
    def extract_stats(self, df):
        df = self.skip_wr(df)
        if isinstance(df, pd.DataFrame):
            return {self.tk(k, k1): v for k, o in df.describe().to_dict().items() for k1, v in o.items()}
        elif isinstance(df, pd.Series):
            return {k: v for k, v in df.describe().to_dict().items()}

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