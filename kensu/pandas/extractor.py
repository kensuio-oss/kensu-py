from hashlib import sha256

import pandas as pd
import numpy as np

import kensu
from kensu.client import *
from kensu.utils.dsl.extractors import ExtractorSupport
from kensu.utils.helpers import singleton

@singleton
class KensuPandasSupport(ExtractorSupport):  # should extends some KensuSupport class

    def is_supporting(self, df):
        return isinstance(df, pd.DataFrame) or isinstance(df, pd.Series)

    def is_machine_learning(self, df):
        return False

    def skip_wr(self, df):
        if isinstance(df, kensu.pandas.DataFrame):
            return df.get_df()
        elif isinstance(df, kensu.pandas.Series):
            return df.get_s()
        else:
            return df

    # return list of FieldDef
    def extract_schema_fields(self, df):
        df = self.skip_wr(df)
        if isinstance(df, pd.DataFrame):
            return [FieldDef(name=str(k), field_type=v.name, nullable=True) for (k, v) in df.dtypes.to_dict().items()]
        elif isinstance(df, pd.Series):
            return [FieldDef(name=df.name, field_type=str(df.dtypes), nullable=True)]

    def extract_location(self, df, location):
        
        if location is not None:
            return location
        else:
            df = self.skip_wr(df)
            return "in-mem://AN_ID" + sha256(str(df.to_dict()).encode("utf-8")).hexdigest() +'/in-mem-transformation'
            

    def extract_format(self, df, fmt):
        if fmt is not None:
            return fmt
        else:
            df = self.skip_wr(df)
            return df.__class__.__name__

    def tk(self, k, k1): return k + '.' + k1

    # return dict of doubles (stats)
    def extract_stats(self, df):
        df = self.skip_wr(df)
        if isinstance(df, pd.DataFrame):
            stats_dict = {self.tk(k, k1): v for k, o in df.describe().to_dict().items() for k1, v in o.items() if type(v) in [int,float,np.int64]}
            for key,item in stats_dict.copy().items():
                if type(item) == np.int64:
                    stats_dict[key] = int(item)
                if np.isnan(item):
                    del stats_dict[key]
            return stats_dict
        elif isinstance(df, pd.Series):
            return {k: v for k, v in df.describe().to_dict().items() if type(v) in [int,float] }

    def extract_data_source(self, df, pl, **kwargs):

        logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None

        df = self.skip_wr(df)
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
        df = self.skip_wr(df)
        fields = self.extract_schema_fields(df)
        sc_pk = SchemaPK(data_source.to_ref(), fields=fields)
        schema = Schema(name="schema:"+data_source.name, pk=sc_pk)
        return schema

    def extract_data_source_and_schema(self, df, pl, **kwargs):
        df = self.skip_wr(df)
        ds = self.extract_data_source(df, pl, **kwargs)
        sc = self.extract_schema(ds, df)
        return ds, sc