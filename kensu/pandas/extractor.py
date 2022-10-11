import logging
from hashlib import sha256

import pandas as pd
import numpy as np

import kensu
from kensu.client import *
from kensu.utils.dsl.extractors import ExtractorSupport, get_or_set_rand_location
from kensu.utils.helpers import singleton, save_stats_json, to_datasource


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
            try:
                df_desc_numbers = df.describe(include=['number']).to_dict().items()
            except:
                df_desc_numbers = {}

            stats_dict = {self.tk(k, k1): v for k, o in df_desc_numbers for k1, v in o.items()}

            # add all counts
            all_count = df.describe(include='all').loc[['count']].to_dict().items()
            count_dict= {self.tk(k, k1): v for k, o in all_count for k1, v in o.items()}


            #Extract datetime for timeliness
            date_df = df.select_dtypes(['datetime', 'datetimetz'])
            date_dict = {}
            # if not checked, when there's no Datetime types,
            # it would throw `ValueError: Cannot describe a DataFrame without columns`
            if not (date_df.ndim == 2 and date_df.columns.size == 0):
                date_describe = date_df.describe(datetime_is_numeric=False).to_dict()
                for col in date_describe:
                    first = date_describe[col]['first'].timestamp()*1000
                    last = date_describe[col]['last'].timestamp()*1000
                    date_dict[col + '.first'] = first
                    date_dict[col + '.last'] = last
            
            #Extract categories and boolean as categorical series
            cat_names = df.select_dtypes(['category', 'boolean']).columns
            cat_dict = {}
            for cat_col in cat_names:
                vc = df[cat_col].value_counts()
                vc_dict = vc.to_dict()
                for k, v in vc_dict.items():
                    if not np.isnan(v):
                        cat_dict[self.tk(cat_col, str(k))] = v
                count_names = ["nrows", "count", "len", "numrows"]
                count_name = None
                for n in count_names:
                    if n in vc_dict:
                        pass
                    else:
                        count_name = n
                        break
                if count_name is None:
                    logging.warning("Because the categorical value has many category names matches 'nrows', 'count', and alike, the count stat is set to 'kensu.nrows' for " + cat_col)
                    count_name = "kensu.nrows"
                cat_dict[self.tk(cat_col, count_name)] = vc.sum()
                
                distinct_count_name = "num_categories"
                if distinct_count_name in vc_dict:
                    logging.warning("Because the categorical value has a category names 'num_categories', the number of categories stat is set to 'kensu.num_categories' for " + cat_col)
                    distinct_count_name = self.tk("kensu", distinct_count_name)
                cat_dict[self.tk(cat_col, distinct_count_name)] = len(vc_dict)
                
                # TODO do we need nulls and such?

            stats_dict = {**stats_dict,**count_dict, **date_dict, **cat_dict}

            #Add missing value computation
            count = len(df)
            stats_dict['nrows'] = count

            for col in df:
                try:
                    stats_dict[col + '.nullrows'] =  count - stats_dict[col + '.count']
                except:
                    try:
                        stats_dict[col + '.nullrows'] = count - stats_dict[col + '.nrows']
                    except:
                        logging.debug('Unable to get NA count for ' + str(col))

            for key, item in stats_dict.copy().items():
                if isinstance(item,str):
                    del stats_dict[key]
                elif np.isnan(item):
                    del stats_dict[key]
                elif isinstance(item, np.number):
                    stats_dict[key] = item.item()
                
            return stats_dict
        elif isinstance(df, pd.Series):
            return {k: v for k, v in df.describe().to_dict().items() if type(v) in [int,float] }

    def extract_data_source(self, df, pl, **kwargs):

        logical_naming = kwargs["logical_data_source_naming_strategy"] if "logical_data_source_naming_strategy" in kwargs else None

        df = self.skip_wr(df)
        location = self.extract_location(df, kwargs.get("location"))
        fmt = self.extract_format(df, kwargs.get("format"))

        if location is None or fmt is None:
            raise Exception(
                "cannot report new pandas dataframe without location ({}) a format provided ({})!".format(location, fmt))

        ds_pk = DataSourcePK(location=location, physical_location_ref=pl)
        name = ('/').join(location.split('/')[-2:])

        return to_datasource(ds_pk=ds_pk, format=fmt, location=location, logical_data_source_naming_strategy=logical_naming, name=name)

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