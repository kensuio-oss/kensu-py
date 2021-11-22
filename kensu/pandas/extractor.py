import logging
from hashlib import sha256

import pandas as pd
import numpy as np

import kensu
from kensu.client import *
from kensu.utils.dsl.extractors import ExtractorSupport, get_or_set_rand_location
from kensu.utils.helpers import singleton, to_datasource


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
            if df.name is None:
                return [FieldDef(name='value', field_type=str(df.dtypes), nullable=True)]
            else:
                return [FieldDef(name=df.name, field_type=str(df.dtypes), nullable=True)]

    def extract_location(self, df, location):
        
        if location is not None:
            return location
        else:
            df = self.skip_wr(df)
            from kensu.pandas import DataFrame
            if isinstance(df,DataFrame):
                df = df.get_df()
            # FIXME: or should it be added as prop to the ksu wrapper instead?!
            return get_or_set_rand_location(df)

    def extract_format(self, df, fmt):
        if fmt is not None:
            return fmt
        else:
            df = self.skip_wr(df)
            return df.__class__.__name__

    def tk(self, k, k1): return str(k) + '.' + k1

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
            #Extract datetime for timeliness
            date_df = df.select_dtypes(['datetime', 'datetimetz'])
            date_dict = {}
            # if not checked, when there's no Datetime types,
            # it would throw `ValueError: Cannot describe a DataFrame without columns`
            if not (date_df.ndim == 2 and date_df.columns.size == 0):
                date_describe = date_df.describe().to_dict()
                for col in date_describe:
                    first = date_describe[col]['first'].timestamp()*1000
                    last = date_describe[col]['last'].timestamp()*1000
                    date_dict[col + '.first'] = first
                    date_dict[col + '.last'] = last

            stats_dict = {**stats_dict,**date_dict}

            #Add missing value computation
            count = len(df)
            stats_dict['nrows'] = count
            for col in df:
                try:
                    stats_dict[col + '.nullrows'] =  count - stats_dict[col + '.count']
                except:
                    logging.debug('Unable to get NA count for ' + str(col))

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

        return to_datasource(ds_pk=ds_pk, format=fmt, location=location, logical_naming=logical_naming, name=name)

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