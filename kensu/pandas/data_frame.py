import logging
import re
from typing import Optional

import pandas as pd
from pandas._typing import Axes, Dtype
from pandas.core.indexing import _iLocIndexer, _LocIndexer
from pandas.core.strings import StringMethods
from pandas.core.arrays.categorical import CategoricalAccessor

import numpy

from kensu.numpy import ndarray
from kensu.pandas.extractor import KensuPandasSupport
from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs
from kensu.utils.kensu_class_handlers import KensuClassHandlers
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.dsl import mapping_strategies
from kensu.utils.helpers import eventually_report_in_mem, extract_ksu_ds_schema, get_absolute_path

from kensu.client import *
from kensu.utils.wrappers import remove_ksu_wrappers


class KensuPandasDelegator(object):
    SKIP_KENSU_FIELDS = ["_DataFrame__k_df", "INTERCEPTORS"]
    SKIP_KENSU_METHODS = ["get_df", "kensu_init", "k_to_format", "to_string"]

    def __getitem__(self, key):
        ''' Item lookup: returns a Series with the values of the key `key`'''
        result = self.__getitem__(key)
        if isinstance(result, DataFrame) or isinstance(result, pd.DataFrame):
            # this case is handled by the callable property as [[col1, col2, ...]] is converted into `loc`
            return result

        # we assume the type is Series
        if not isinstance(result, pd.Series):
            raise RuntimeError("Type expected is Series, got " + str(type(result)))
        kensu = KensuProvider().instance()

        orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(self, kensu.default_physical_location_ref))
        orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, self))

        result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

        kensu_s = Series.using(result)
        kensu_s.name = key

        if kensu.mapping:
                kensu.add_dependencies_mapping(result_sc.to_guid(),key,orig_sc.to_guid(),key,'__getitem__')

        else:
            kensu.add_dependency((self, orig_ds, orig_sc), (result, result_ds, result_sc),
                               mapping_strategy=mapping_strategies.DIRECT)
        return kensu_s



    def __getattribute__(self, name):
        if name == "__class__":
            attr_value = object.__getattribute__(self, name)
            return attr_value
        elif name in ['_mgr','_data','_flags']:
            attr_value = object.__getattribute__(self.get_df(), name)
            return attr_value
        else:
            attr_value = object.__getattribute__(self, name)

            if hasattr(attr_value, '__call__'):
                return KensuPandasDelegator.handle_callable(self, name, attr_value)

            else:
                return KensuPandasDelegator.handle_field(self, name, attr_value)


    @staticmethod
    def wrap_returned_df(kensu_df, returned, name, original):
        if isinstance(returned, pd.DataFrame) \
                and not isinstance(returned, DataFrame) \
                and original is not returned:

            logging.debug("Wrapping attr access resulting dataframe in KensuDF for property name=" + name)
            tmp = DataFrame.using(returned)
            returned = tmp
        elif isinstance(returned, numpy.ndarray):
            logging.debug("Wrapping attr access resulting numpy.ndarray in KensuDF for property name=" + name)
            tmp = ndarray.using(returned)
            returned = tmp
        return returned

    @staticmethod
    def handle_field(kensu_df, name, attr_value):
        # _DataFrame__k_df => points to DataFrame.__k_df
        if name in KensuPandasDelegator.SKIP_KENSU_FIELDS:
            # return Kensu DF attr value right away
            logging.debug("Kensu attribute name=" + name)
            return attr_value
        else:
            logging.debug("NOT Kensu, let's delegate attribute name=" + name)

            pd_df = kensu_df.get_df()
            df_attr = object.__getattribute__(pd_df, name)
            result = KensuPandasDelegator.wrap_returned_df(kensu_df, df_attr, name, pd_df)

            #adding the datasources, schemas and lineage to the dependencies
            if result is not None and isinstance(result, DataFrame):
                kensu = KensuProvider().instance()
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_df, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds,pd_df))

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

                kensu.add_dependency((pd_df, orig_ds, orig_sc), (result, result_ds, result_sc),
                                   mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)
            elif result is not None and isinstance(result, ndarray):
                kensu = KensuProvider().instance()
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_df, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds,pd_df))

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

                kensu.add_dependency((pd_df, orig_ds, orig_sc), (result, result_ds, result_sc),
                                   mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)


            return result

    @staticmethod
    def handle_callable(kensu_df, name, attr_value):
        if name not in KensuPandasDelegator.SKIP_KENSU_METHODS:
            pd_df = kensu_df.get_df()
            delegated_pd_attr = object.__getattribute__(pd_df, name)
            # for example, `iloc` is subscriptable and is a property, hence call this way: iloc[]
            if isinstance(getattr(type(pd_df), name), property):
                return KensuPandasDelegator.handle_callable_property(kensu_df, name, pd_df, delegated_pd_attr)
            else:
                docstring = delegated_pd_attr.__doc__
                return KensuPandasDelegator.create_function_wrapper(kensu_df, name, docstring)
        else:
            logging.debug("Kensu function name=" + name)

            # return Kensu DF function result right away
            def w(*args, **kwargs):
                return attr_value(*args, **kwargs)
            return w

    @staticmethod
    def create_function_wrapper(kensu_df, name, docstring):
        logging.debug("Kensu wrapping function name=" + name)

        def wrapper(*args, **kwargs):

            pd_df = kensu_df.get_df()
            df_attr = object.__getattribute__(pd_df, name)

            # call method on delegated df
            delegation_config = getattr(kensu_df, 'INTERCEPTORS', None)
            for regex_attr_name in delegation_config:
                result_regex = regex_attr_name.search(name)
                if name == 'to_records':
                    result_regex = None

                if result_regex is not None:
                    # if we pass the regex, there is an interception defined, so we execute it
                    name_of_intercept_method = delegation_config[regex_attr_name]
                    intercept = object.__getattribute__(kensu_df, name_of_intercept_method)
                    intercept(result_regex, *args, **kwargs)

            kensu = KensuProvider().instance()

            # set_axis updates the DataFrame directly (self) and returns None, we loose the initial dataframe
            # so we need to create the Kensu object before
            orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_df, kensu.default_physical_location_ref))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, pd_df))

            new_args=remove_ksu_wrappers(args)
            new_args = tuple(new_args)
            result = df_attr(*new_args, **kwargs)
            original_result = result
            result = KensuPandasDelegator.wrap_returned_df(kensu_df, result, name, pd_df)

            if result is None :
                #set_axis updates the DataFrame directly (self) and returns None, so we reset the result
                if name in ["_set_axis","_set_item"]:
                    result = kensu_df
            #adding the datasources, schemas and lineage to the dependencies
            if (result_regex is None and result is not None and (isinstance(result,DataFrame) or isinstance(result,ndarray))):

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

                if kensu.mapping :
                    if name in ['__getitem__','_slice','_reindex_with_indexers','head',
                                '_take_with_is_copy','fillna','to_records','drop']:
                        for col in [k.name for k in result_sc.pk.fields]:
                            kensu.add_dependencies_mapping(result_sc.to_guid(),col,orig_sc.to_guid(),col,name)
                    if name in ['pivot_table']:
                        index = kwargs['index'] if "index" in kwargs else None
                        columns = kwargs['columns'] if "columns" in kwargs else None
                        values = kwargs['values'] if 'values' in kwargs else None
                        if isinstance(index, list) == False and index is not None:
                            index = list(index)
                        if isinstance(columns, list) == False and columns is not None:
                            columns = [columns]
                        if isinstance(values, list) == False and values is not None:
                            values = [values]

                        for col in result:
                            if values is not None:
                                for val in values:
                                    if len(values) == 1:
                                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(),
                                                                       str(val), name)
                                    if val in str(col):
                                        kensu.add_dependencies_mapping(result_sc.to_guid(),str(col),orig_sc.to_guid(),val,name)

                            elif columns is not None:
                                if index is None:
                                    linked_columns = list(result.index)
                                    for element in linked_columns:
                                        kensu.add_dependencies_mapping(result_sc.to_guid(),str(col),orig_sc.to_guid(),str(element),name)
                                else:
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(),str(col[0]), name)

                            elif index is not None:
                                kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(),
                                                             str(col), name)
                    if name in ['_set_item']:
                        col_dest = [k.name for k in result_sc.pk.fields]
                        col_orig = [k.name for k in orig_sc.pk.fields]

                        try:
                            orig_series = eventually_report_in_mem(kensu.extractors.extract_data_source(item, kensu.default_physical_location_ref))
                            orig_sc_series = eventually_report_in_mem(kensu.extractors.extract_schema(orig_series, item))
                        except:
                            orig_sc_series = None

                        col_series = [k.name for k in orig_sc_series.pk.fields] if orig_sc_series is not None else None
                        col_orig = list(set(col_orig) - set([args[0]]))
                        for col in col_dest:
                            if col in col_orig:
                                kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(),
                                                             str(col), name)
                            else:
                                if col_series:
                                    col_origin = col_series[0]
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc_series.to_guid(),
                                                                 str(col_origin), name)



                    if name in ['rename','_set_axis']:
                        col_dest = [k.name for k in result_sc.pk.fields]
                        col_orig = [k.name for k in orig_sc.pk.fields]
                        for i in range(len(col_dest)):
                            kensu.add_dependencies_mapping(result_sc.to_guid(), str(col_dest[i]), orig_sc.to_guid(),
                                                         str(col_orig[i]), name)

                    if name in ['merge']:
                        left = kensu_df
                        right = kwargs['right'] if 'right' in kwargs else args[0]
                        how = kwargs['how'] if 'how' in kwargs else 'inner'
                        on = kwargs['on'] if 'on' in kwargs else None
                        left_on = kwargs['left_on'] if 'left_on' in kwargs else None
                        right_on = kwargs['right_on'] if 'right_on' in kwargs else None
                        suffixes = kwargs['suffix'] if 'suffix' in kwargs else ("_x", "_y")

                        left_df = left.get_df()
                        right_df = right.get_df()

                        left_ds = orig_ds
                        left_sc = orig_sc

                        right_ds = eventually_report_in_mem(
                            kensu.extractors.extract_data_source(right_df, kensu.default_physical_location_ref,
                                                               logical_naming=kensu.logical_naming))
                        right_sc = eventually_report_in_mem(kensu.extractors.extract_schema(right_ds, right_df))


                        if how == 'inner':
                            result_cols = result.columns
                            columns_left = left_df.columns
                            columns_right = right_df.columns
                            common_columns = [value for value in columns_left if value in columns_right]
                            columns_join = on if isinstance(on, list) else [on]
                            columns_right_join = right_on if isinstance(right_on, list) else [right_on]
                            columns_left_join = left_on if isinstance(left_on, list) else [left_on]
                            suffix_left = suffixes[0]
                            suffix_right = suffixes[1]

                            combined_on = dict(zip(columns_right_join, columns_left_join))

                            for col in result_cols:
                                if col in columns_join:
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(),
                                                                 str(col), "Inner Join")
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(),
                                                                 str(col),
                                                                 "Inner Join")

                                elif col in combined_on:
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(),
                                                                 str(col),
                                                                 "Inner Join")
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(),
                                                                 combined_on[col],
                                                                 "Inner Join")

                                elif col in columns_right and col not in columns_left:
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(),
                                                                 str(col),
                                                                 "Inner Join")

                                elif col in columns_left and col not in columns_right:
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(),
                                                                 str(col),
                                                                 "Inner Join")

                                elif col.rstrip(suffix_left) in columns_left:
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(),
                                                                 col.rstrip(suffix_left),
                                                                 "Inner Join")

                                elif col.rstrip(suffix_right) in columns_right:
                                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(),
                                                                 col.rstrip(suffix_right), "Inner Join")

                else:
                    kensu.add_dependency((pd_df, orig_ds, orig_sc), (result, result_ds, result_sc),
                                   mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            if original_result is None:
                return None
            else: 
                return result

        wrapper.__doc__ = docstring
        return wrapper

    @staticmethod
    def handle_callable_property(kensu_df, name, df, prop_value):
        logging.debug("Kensu wrapping property name=" + name)
        pd_df = kensu_df.get_df()


        if (isinstance(prop_value, _iLocIndexer) or isinstance(prop_value, _LocIndexer)) \
                and isinstance(prop_value.obj, pd.DataFrame) \
                and not isinstance(prop_value.obj, DataFrame):
            logging.debug("Wrapping dataframe in KensuDF for property name=" + name)

            dao = DataFrame.using(prop_value.obj)

            # adding the datasources, schemas and lineage to the dependencies
            if dao is not None and isinstance(dao,DataFrame):
                kensu = KensuProvider().instance()
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_df, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds,pd_df))

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(dao, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, dao))

                if orig_ds.to_guid() != result_ds.to_guid() and orig_sc.to_guid() != result_sc.to_guid():
                    kensu.add_dependency((pd_df, orig_ds, orig_sc), (dao, result_ds, result_sc),
                                       mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            # assigning the Kensu DF to the indexer to continue the tracing, wrapping the internal iloc/loc object
            prop_value.obj = dao
        else:
            # TODO log?
            pass

        return prop_value

class DataFrame(KensuPandasDelegator, pd.DataFrame):
    INTERCEPTORS = {
        re.compile('to_(.*)'): 'k_to_format',
    }


    support = KensuPandasSupport()

    __k_df = None

    def __init__(
            self,
            data=None,
            index: Optional[Axes] = None,
            columns: Optional[Axes] = None,
            dtype: Optional[Dtype] = None,
            copy: bool = False,
    ):

        if isinstance(data,ndarray):
            kensu = KensuProvider().instance()
            orig_data = data
            data = data.get_nd()
            orig_ds = eventually_report_in_mem(
                kensu.extractors.extract_data_source(orig_data, kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, orig_data))

            df = pd.DataFrame(data,index,columns,dtype,copy)

            result_ds = eventually_report_in_mem(
                kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref))
            result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, df))

            for col in [k.name for k in result_sc.pk.fields]:
                kensu.add_dependencies_mapping(result_sc.to_guid(), col, orig_sc.to_guid(), col, 'init')

        elif isinstance(data,dict):
            from kensu.itertools import kensu_list
            kensu = KensuProvider().instance()
            deps ={}
            for key in data.keys():
                item = data[key]

                if isinstance(item,kensu_list):
                    deps[key] = item.deps

                if isinstance(item,ndarray):
                    orig_ds = eventually_report_in_mem(
                        kensu.extractors.extract_data_source(item, kensu.default_physical_location_ref))
                    orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, item))
                    deps[key] = [orig_sc]


            df = pd.DataFrame(data, index, columns, dtype, copy)
            result_ds = eventually_report_in_mem(
                kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref))
            result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, df))

            for key in deps.keys():
                for orig_sc in deps[key]:
                    for col in [k.name for k in orig_sc.pk.fields]:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(key), orig_sc.to_guid(), str(col), 'init')



        else:
            df = pd.DataFrame(data, index, columns, dtype, copy)

        self.kensu_init(df)


    @staticmethod
    def using(df):
        if isinstance(df, DataFrame):
            d = DataFrame.using(df.get_df())
            return d
        else:
            d = DataFrame()
            d.kensu_init(df)
            return d

    def get_df(self):
        # if the current Kensu DataFrame isn't delegating... TODO.. need to have a type for this instead...
        if self.__k_df is None:
            return self
        else:
            return self.__k_df

    def kensu_init(self, df):
        self.__k_df = df


    buffer_param_name_re = re.compile('.*buf(?:fer)?')

    def k_to_format(self, result_regex, *args, **kwargs):
        kensu = KensuProvider().instance()
        orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(self.get_df(), kensu.default_physical_location_ref,logical_naming=kensu.logical_naming))
        orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, self.get_df()))

        # the regex for this method has a group to get the read format
        fmt = result_regex.group(1)

        # look up for buf
        location = None
        for param_name in kwargs.keys():
            if self.buffer_param_name_re.search(param_name) is not None:
                location = kwargs[param_name]

        #FIXME
        table = None
        if fmt == 'gbq':
            fmt = 'BigQuery Table'
            if 'BigQuery' not in kensu.data_collectors:
                from google.cloud import bigquery
                client = bigquery.Client(credentials=kwargs['credentials'])
                kensu.data_collectors['BigQuery'] = client
            else:
                from google.cloud import bigquery
                client = kensu.data_collectors['BigQuery']

            table = client.get_table(args[0])
            path = table.path
            location = "bigquery:/" + path

        if location is None and location != 'BigQuery Table' and len(args) > 0:

            location = get_absolute_path(args[0])

        if location is not None and fmt is not None:
            df = self.get_df()

            #FIXME generify for written target ds (BigQuery, mysql, postgre...), same for location and format
            ds = kensu.extractors.extract_data_source(self.get_df(), kensu.default_physical_location_ref, location=location, format=fmt,logical_naming=kensu.logical_naming)._report()
            if fmt == 'BigQuery Table':
                sc = kensu.extractors.extract_schema(ds, table)._report()
            else:
                sc = kensu.extractors.extract_schema(ds, self.get_df())._report()

            kensu.real_schema_df[sc.to_guid()] = df

            # add dep between original data source and written one
            if kensu.mapping :
                for col in df:
                    kensu.add_dependencies_mapping(sc.to_guid(),str(col),orig_sc.to_guid(),str(col),'Write')
            else:
                kensu.add_dependency((df, orig_ds, orig_sc), (df, ds, sc), mapping_strategy=mapping_strategies.DIRECT)

            if kensu.mapping:
                kensu.report_with_mapping()

            else:
                def process_dag(out):

                    deps = kensu.get_dependencies()

                    def process_dag_layer(out, layer="-"):
                        for [i, o, strategy] in iter(deps):
                            in_ds_id = KensuClassHandlers.guid(i[1])
                            logging.debug(layer +"dep.in.datasource.id {}".format(str(in_ds_id)))
                            out_ds_id = KensuClassHandlers.guid(o[1])
                            logging.debug(layer +"dep.out.datasource.id {}".format(str(out_ds_id)))
                            current_ds_id = KensuClassHandlers.guid(out[1])
                            logging.debug(layer +"current.datasource.id {}".format(str(current_ds_id)))
                            in_sc_id = KensuClassHandlers.guid(i[2])
                            logging.debug(layer +"dep.in.schema.id {}".format(str(in_sc_id)))
                            out_sc_id = KensuClassHandlers.guid(o[2])
                            logging.debug(layer +"dep.out.schema.id {}".format(str(out_sc_id)))
                            current_sc_id = KensuClassHandlers.guid(out[2])
                            logging.debug(layer +"current.schema.id {}".format(str(current_sc_id)))
                            logging.debug("-------------------")
                            if out_ds_id == current_ds_id and out_sc_id == current_sc_id:
                                if isinstance(i[0], DataFrame):
                                    i = (i[0].get_df(), i[1], i[2])
                                if isinstance(o[0], DataFrame):
                                    o = (o[0].get_df(), o[1], o[2])
                                lin = kensu.s.n.with_input(i) \
                                    .with_output(o) \
                                    .with_strategy(strategy) \
                                    .e
                                lin.e()

                                # try process previous layer
                                # FIXME.. need to handle loops => I guess this needs to be solved in the dependencies itself
                                process_dag_layer(i, "  " + layer)
                        return
                    process_dag_layer(out)
                    return
                process_dag((self.get_df(), ds, sc))

class KensuSeriesDelegator(object):
    SKIP_KENSU_FIELDS = ["_Series__k_s", "INTERCEPTORS"]
    SKIP_KENSU_METHODS = ["get_s", "kensu_init", "k_to_format", "to_string"]

    def __getattribute__(self, name):
        if name in ['str',"to_string"]:
            attr_value = object.__getattribute__(self.get_s(), name)
        else:
            attr_value = object.__getattribute__(self, name)

        if name == "_Series__k_s":
            return attr_value
        if name == "__class__":
            return attr_value
        if hasattr(attr_value, '__call__'):
            return KensuSeriesDelegator.handle_callable(self, name, attr_value)
        else:
            return KensuSeriesDelegator.handle_field(self, name, attr_value)

    @staticmethod
    def wrap_returned_df(kensu_s, returned, name, original):
        if isinstance(returned, pd.Series) \
                and not isinstance(returned, Series) \
                and original is not returned:
            logging.debug("Wrapping attr access resulting pd.Series in KensuS for property name=" + name)
            tmp = Series.using(returned)
            returned = tmp

        elif isinstance(returned, numpy.ndarray):
            logging.debug("Wrapping attr access resulting numpy.ndarray in KensuS for property name=" + name)
            tmp = ndarray.using(returned)
            returned = tmp

        return returned

    @staticmethod
    def handle_field(kensu_s, name, attr_value):
        # _Series__k_s => points to Series.__k_s
        if name in KensuSeriesDelegator.SKIP_KENSU_FIELDS:
            # return Kensu DF attr value right away
            logging.debug("Kensu attribute name=" + name)
            return attr_value
        else:
            logging.debug("NOT Kensu, let's delegate attribute name=" + name)

            pd_s = kensu_s.get_s()
            s_attr = object.__getattribute__(pd_s, name)
            result = KensuSeriesDelegator.wrap_returned_df(kensu_s, s_attr, name, pd_s)


            #adding the datasources, schemas and lineage to the dependencies
            if result is not None and isinstance(result, Series):
                kensu = KensuProvider().instance()
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_s, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds,pd_s))

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

                kensu.add_dependency((pd_s, orig_ds, orig_sc), (result, result_ds, result_sc),
                                   mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            elif result is not None and isinstance(result, ndarray):
                kensu = KensuProvider().instance()
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_s, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds,pd_s))

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

                if kensu.mapping:
                    result_col = [k.name for k in result_sc.pk.fields][0]
                    orig_col = [k.name for k in orig_sc.pk.fields][0]
                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(result_col), orig_sc.to_guid(),
                                                   str(orig_col), name)

                else:
                    kensu.add_dependency((pd_s, orig_ds, orig_sc), (result, result_ds, result_sc),
                                   mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            elif result is not None and isinstance(result, StringMethods):

                class Kensu_StringMethods(StringMethods):

                    def __getitem__(self, key):
                        if isinstance(key, slice):
                            original_result = self.slice(start=key.start, stop=key.stop, step=key.step)
                        else:
                            original_result = self.get(key)

                        orig_series = self._parent

                        kensu = KensuProvider().instance()

                        orig_ds = kensu.extractors.extract_data_source(orig_series, kensu.default_physical_location_ref)
                        orig_sc = kensu.extractors.extract_schema(orig_ds, orig_series)
                        res_ds = kensu.extractors.extract_data_source(original_result,
                                                                      kensu.default_physical_location_ref)
                        res_sc = kensu.extractors.extract_schema(res_ds, original_result)
                        result_cols = [k.name for k in res_sc.pk.fields]
                        for col in result_cols:
                            kensu.add_dependencies_mapping(res_sc.to_guid(), str(col), orig_sc.to_guid(), str(col), '__getitem__')

                        return Series.using(original_result)
                result.__class__ = Kensu_StringMethods

            elif result is not None and isinstance(result,CategoricalAccessor):
                class Kensu_CategoricalAccessor(CategoricalAccessor):
                    origin = None
                    def set_origin(self,orig):
                        self.origin = orig

                    def get_origin(self):
                        return self.origin

                    @property
                    def codes(self):
                        """
                        Return Series of codes as well as the index.
                        """
                        kensu = KensuProvider().instance()
                        result = pd.Series(self._parent.codes, index=self._index)

                        origin = self.get_origin()

                        orig_ds = kensu.extractors.extract_data_source(origin, kensu.default_physical_location_ref)
                        orig_sc = kensu.extractors.extract_schema(orig_ds, origin)

                        res_ds = kensu.extractors.extract_data_source(result,
                                                                      kensu.default_physical_location_ref)
                        res_sc = kensu.extractors.extract_schema(res_ds, result)
                        result_col = [k.name for k in res_sc.pk.fields][0]
                        orig_col = [k.name for k in orig_sc.pk.fields][0]
                        kensu.add_dependencies_mapping(res_sc.to_guid(), str(result_col), orig_sc.to_guid(),
                                                       str(orig_col), 'code')

                        return Series.using(result)


                result.__class__ = Kensu_CategoricalAccessor
                result.set_origin(kensu_s)

            return result

    @staticmethod
    def handle_callable(kensu_s, name, attr_value):
        if name not in KensuSeriesDelegator.SKIP_KENSU_METHODS:
            pd_s = object.__getattribute__(kensu_s, "get_s")()
            # for example, `iloc` is subscriptable and is a property, hence call this way: iloc[]
            if isinstance(getattr(type(pd_s), name), property):
                delegated_pd_attr = object.__getattribute__(pd_s, name)
                return KensuSeriesDelegator.handle_callable_property(kensu_s, name, pd_s, delegated_pd_attr)
            else:
                delegated_pd_attr = object.__getattribute__(pd_s, name)
                docstring = delegated_pd_attr.__doc__
                return KensuSeriesDelegator.create_function_wrapper(kensu_s, name, docstring)
        else:
            logging.debug("Kensu function name=" + name)

            # return Kensu DF function result right away
            def w(*args, **kwargs):
                return attr_value(*args, **kwargs)
            return w

    @staticmethod
    def create_function_wrapper(kensu_s, name, docstring):
        logging.debug("Kensu wrapping function name=" + name)

        def wrapper(*args, **kwargs):
            # call method on delegated df
            delegation_config = getattr(kensu_s, 'INTERCEPTORS', None)

            for regex_attr_name in delegation_config:
                result_regex = regex_attr_name.search(name)
                if result_regex is not None:
                    # if we pass the regex, there is an interception defined, so we execute it
                    name_of_intercept_method = delegation_config[regex_attr_name]
                    intercept = object.__getattribute__(kensu_s, name_of_intercept_method)
                    intercept(result_regex, *args, **kwargs)

            pd_s = kensu_s.get_s()

            inplace = False
            if 'inplace' in kwargs:
                if kwargs['inplace']:
                    inplace = True
                    cacher = getattr(pd_s, "_cacher", None)
                    if cacher is not None:
                        kensu = KensuProvider().instance()
                        origin_ds = cacher[1]()
                        orig_ds = kensu.extractors.extract_data_source(origin_ds, kensu.default_physical_location_ref)
                        orig_sc = kensu.extractors.extract_schema(orig_ds, origin_ds)
                        origin_cols = [k.name for k in orig_sc.pk.fields]



            s_attr = object.__getattribute__(pd_s, name)

            result = s_attr(*args, **kwargs)
            original_result = result

            result = KensuSeriesDelegator.wrap_returned_df(kensu_s, result, name, pd_s)

            if result is None :
                #set_axis updates the Series directly (self) and returns None, so we reset the result
                if name in ["fillna"]:
                    result = kensu_s

            if inplace:
                cacher = getattr(pd_s, "_cacher", None)
                if cacher is not None:
                    result_ds = cacher[1]()
                    res_ds = kensu.extractors.extract_data_source(result_ds, kensu.default_physical_location_ref)
                    res_sc = kensu.extractors.extract_schema(res_ds, result_ds)
                    result_cols = [k.name for k in res_sc.pk.fields]

                    for col in result_cols:
                        kensu.add_dependencies_mapping(res_sc.to_guid(), str(col), orig_sc.to_guid(), str(col), name)

                    return original_result

            #adding the datasources, schemas and lineage to the dependencies
            if result_regex is None and result is not None and (isinstance(result,DataFrame) or isinstance(result,Series)):
                kensu = KensuProvider().instance()
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_s, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds,pd_s))

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

                if kensu.mapping:
                    if name in ['fillna','replace','astype','_get_with']:
                        for col in [k.name for k in result_sc.pk.fields]:
                            kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col), name)

                else:
                    kensu.add_dependency((pd_s, orig_ds, orig_sc), (result, result_ds, result_sc),
                                       mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            if original_result is None:
                return None
            else:
                return result

        wrapper.__doc__ = docstring
        return wrapper

    @staticmethod
    def handle_callable_property(kensu_s, name, s, prop_value):
        logging.debug("Kensu wrapping property name=" + name)
        pd_s = kensu_s.get_s()

        # FIXME what shall we do here? => There is some lineage to build. Example: iloc
        # FIXME: _LocationIndexer only? limitations?

        if (isinstance(prop_value, _iLocIndexer) or isinstance(prop_value, _LocIndexer)) \
                and isinstance(prop_value.obj, pd.DataFrame) \
                and not isinstance(prop_value.obj, DataFrame):
            logging.debug("Wrapping dataframe in KensuDF for property name=" + name)
            dao = DataFrame.using(prop_value.obj)
            # adding the datasources, schemas and lineage to the dependencies
            if dao is not None and isinstance(dao,DataFrame):
                kensu = KensuProvider().instance()
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(pd_s, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, pd_s))

                result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(dao, kensu.default_physical_location_ref))
                result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, dao))

                if orig_ds.to_guid() != result_ds.to_guid() and orig_sc.to_guid() != result_sc.to_guid():
                    kensu.add_dependency((pd_s, orig_ds, orig_sc), (dao, result_ds, result_sc),
                                       mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            # assigning the Kensu DF to the indexer to continue the tracing
            prop_value.obj = dao
        else:
            # TODO log?
            pass

        return prop_value

class Series(KensuSeriesDelegator, pd.Series):
    INTERCEPTORS = {
        re.compile('to_(.*)'): 'k_to_format',
    }

    # TODO support = KensuPandasSupport()

    __k_s = None


    @staticmethod
    def using(s):
        if isinstance(s, Series):
            cs = Series.using(s.get_s())
            return cs
        else:
            cs = Series()
            cs.kensu_init(s)
            return cs

    def get_s(self):
        # if the current Kensu Series isn't delegating... TODO.. need to have a type for this instead...
        if self.__k_s is None:
            return self
        else:
            return self.__k_s

    def kensu_init(self, s):
        self.__k_s = s

    buffer_param_name_re = re.compile('.*buf(?:fer)?')

    def __add__(self, other):
        #FIXME Something similar to ops/__init.py -> _arith_method_SERIES should be done t avoid code duplication
        left = self.get_s()
        right = other.get_s()
        result = left+right

        '''
        kensu = KensuProvider().instance()

        orig_ds = eventually_report_in_mem(
            kensu.extractors.extract_data_source(self.get_s(), kensu.default_physical_location_ref,
                                               logical_naming=kensu.logical_naming))

        orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, self.get_s()))
        '''

        #TODO Link

        if isinstance(result, Series):
            result = Series.using(result)
        elif isinstance(result,ndarray):
            result = ndarray.using(result)
        else:
            result = result
            #TODO log
        return result

    def k_to_format(self, result_regex, *args, **kwargs):
        kensu = KensuProvider().instance()

        orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(self.get_s(), kensu.default_physical_location_ref,logical_naming=kensu.logical_naming))

        orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, self.get_s()))

        # the regex for this method has a group to get the read format
        fmt = result_regex.group(1)

        # look up for buf
        location = None
        for param_name in kwargs.keys():
            if self.buffer_param_name_re.search(param_name) is not None:
                location = kwargs[param_name]

        if location is None and len(args) > 0:

            location = get_absolute_path(args[0])

        if location is not None and fmt is not None:
            s = self.get_s()

            ds = kensu.extractors.extract_data_source(self.get_s(), kensu.default_physical_location_ref, location=location, format=fmt,logical_naming=kensu.logical_naming)._report()

            sc = kensu.extractors.extract_schema(ds, self.get_s())._report()

            if kensu.mapping :
                kensu.add_dependencies_mapping(sc.to_guid(),self.get_s().name,orig_sc.to_guid(),self.get_s().name,'Write')
                kensu.real_schema_df[sc.to_guid()]=self.get_s()
                kensu.report_with_mapping()
            else:
                # add dep between original data source and written one
                kensu.add_dependency((s, orig_ds, orig_sc), (s, ds, sc), mapping_strategy=mapping_strategies.DIRECT)

                def process_dag(out):
                    deps = kensu.get_dependencies()

                    def process_dag_layer(out, layer="-"):
                        for [i, o, strategy] in iter(deps):
                            in_ds_id = KensuClassHandlers.guid(i[1])
                            logging.debug(layer +"dep.in.datasource.id {}".format(str(in_ds_id)))
                            out_ds_id = KensuClassHandlers.guid(o[1])
                            logging.debug(layer +"dep.out.datasource.id {}".format(str(out_ds_id)))
                            current_ds_id = KensuClassHandlers.guid(out[1])
                            logging.debug(layer +"current.datasource.id {}".format(str(current_ds_id)))
                            in_sc_id = KensuClassHandlers.guid(i[2])
                            logging.debug(layer +"dep.in.schema.id {}".format(str(in_sc_id)))
                            out_sc_id = KensuClassHandlers.guid(o[2])
                            logging.debug(layer +"dep.out.schema.id {}".format(str(out_sc_id)))
                            current_sc_id = KensuClassHandlers.guid(out[2])
                            logging.debug(layer +"current.schema.id {}".format(str(current_sc_id)))
                            logging.debug("-------------------")
                            if out_ds_id == current_ds_id and out_sc_id == current_sc_id:
                                if isinstance(i[0], DataFrame):
                                    i = (i[0].get_df(), i[1], i[2])
                                elif isinstance(i[0], Series):
                                    i = (i[0].get_s(), i[1], i[2])
                                if isinstance(o[0], DataFrame):
                                    o = (o[0].get_df(), o[1], o[2])
                                elif isinstance(o[0], Series):
                                    o = (o[0].get_s(), o[1], o[2])
                                lin = kensu.s.n.with_input(i) \
                                    .with_output(o) \
                                    .with_strategy(strategy) \
                                    .e
                                lin.e()

                                # try process previous layer
                                # FIXME.. need to handle loops => I guess this needs to be solved in the dependencies itself
                                process_dag_layer(i, "  " + layer)
                        return
                    process_dag_layer(out)
                return
                process_dag((self.get_s(), ds, sc))

def wrap_pandas_reader(reader):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()

        if reader.__name__.startswith("read_"):
            fmt = reader.__name__[len("read_"):]
        else:
            fmt = "unknown"

        df = reader(*args, **kwargs)
        read_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref,logical_naming=kensu.logical_naming))
        read_sc = eventually_report_in_mem(kensu.extractors.extract_schema(read_ds, df))


        # TODO... I think other param names are expected here for other reader functions
        # prepare original data source
        #TODO: handle url,s3,etc
        if "filepath_or_buffer" in kwargs:
            location = get_absolute_path(kwargs["filepath_or_buffer"])
        elif args[0].startswith('http://') or args[0].startswith('https://'):
            location = args[0]
        else:
            location = get_absolute_path(args[0])

        df_kensu = DataFrame.using(df)

        ds = kensu.extractors.extract_data_source(df_kensu, kensu.default_physical_location_ref, location=location, format=fmt,logical_naming=kensu.logical_naming)._report()

        sc = kensu.extractors.extract_schema(ds, df_kensu)._report()
        kensu.real_schema_df[sc.to_guid()] = df
        if kensu.mapping == True:
            for col in df:
                kensu.add_dependencies_mapping(read_sc.to_guid(), str(col), sc.to_guid(), str(col),
                                             "Read")
        else:
            kensu.add_dependency((df, ds, sc), (df, read_ds, read_sc),mapping_strategy = mapping_strategies.OUT_STARTS_WITH_IN)

        return df_kensu

    wrapper.__doc__ = reader.__doc__
    return wrapper

def wrap_pandas_get_dummies(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        df_result = method(*args, **kwargs)
        df = args[0] # see get_dummies definition (first arg is `data`)

        orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref,logical_naming=kensu.logical_naming))
        orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, df))

        result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(df_result, kensu.default_physical_location_ref,logical_naming=kensu.logical_naming))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, df_result))



        df_result_kensu = DataFrame.using(df_result)

        if kensu.mapping:
            col_dest = [k.name for k in result_sc.pk.fields]
            col_orig = [k.name for k in orig_sc.pk.fields]
            prefix = kwargs['prefix'] if 'prefix' in kwargs else None
            prefix_sep = kwargs['prefix_sep'] if 'prefix_sep' in kwargs else "_"
            columns = kwargs['columns'] if 'columns' in kwargs else None

            for col in col_dest:
                if col in col_orig:
                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col),
                                                 "Dummy")
                else:
                    origin_col = col.split(prefix_sep)[0]
                    if prefix:
                        if isinstance(prefix,list):
                            index = prefix.index(origin_col)
                            origin_col = columns[index]

                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(origin_col),
                                                 "Dummy")

        else:
            kensu.add_dependency((df,orig_ds,orig_sc),(df_result,result_ds,result_sc),mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

        return df_result_kensu

    wrapper.__doc__ = method.__doc__
    return wrapper


def wrap_merge(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()

        new_args = []
        for item in args:
            if isinstance(item, DataFrame):
                new_args.append(item.get_df())
            elif isinstance(item, Series):
                new_args.append(item.get_s())
            else:
                new_args.append(item)
        new_args = tuple(new_args)

        new_kwargs = {}
        for item in kwargs:
            if isinstance(kwargs[item], DataFrame):
                new_kwargs[item]=kwargs[item].get_df()
            elif isinstance(item, Series):
                new_kwargs[item]=kwargs[item].get_s()
            else:
                new_kwargs[item]=kwargs[item]

        df_result = method(*new_args, **new_kwargs)

        left = kwargs['left'] if 'left' in kwargs else args[0]
        right = kwargs['right'] if 'right' in kwargs else args[1]
        how =  kwargs['how'] if 'how' in kwargs else 'inner'
        on = kwargs['on'] if 'on' in kwargs else None
        left_on = kwargs['left_on'] if 'left_on' in kwargs else None
        right_on = kwargs['right_on'] if 'right_on' in kwargs else None
        suffixes = kwargs['suffix'] if 'suffix' in kwargs else ("_x", "_y")

        left_df = left.get_df()
        right_df = right.get_df()

        left_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(left_df, kensu.default_physical_location_ref,
                                                                              logical_naming=kensu.logical_naming))
        left_sc = eventually_report_in_mem(kensu.extractors.extract_schema(left_ds, left_df))

        right_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(right_df, kensu.default_physical_location_ref,
                                                                              logical_naming=kensu.logical_naming))
        right_sc = eventually_report_in_mem(kensu.extractors.extract_schema(right_ds, right_df))


        result_ds = eventually_report_in_mem(
            kensu.extractors.extract_data_source(df_result, kensu.default_physical_location_ref,
                                               logical_naming=kensu.logical_naming))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, df_result))

        df_result_kensu = DataFrame.using(df_result)

        if kensu.mapping:
            if how == 'inner':
                result_cols = df_result.columns
                columns_left = left_df.columns
                columns_right = right_df.columns
                common_columns = [value for value in columns_left if value in columns_right]
                columns_join = on if isinstance(on,list) else [on]
                columns_right_join = right_on if isinstance(right_on,list) else [right_on]
                columns_left_join = left_on if isinstance(left_on, list) else [left_on]
                suffix_left = suffixes[0]
                suffix_right = suffixes[1]

                combined_on = dict(zip(columns_right_join,columns_left_join))

                for col in result_cols:
                    if col in columns_join:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(), str(col), "Inner Join")
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(), str(col),
                                                     "Inner Join")

                    elif col in combined_on:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(), str(col),
                                                     "Inner Join")
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(), combined_on[col],
                                                     "Inner Join")

                    elif col in columns_right and col not in columns_left:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(), str(col),
                                                     "Inner Join")

                    elif col in columns_left and col not in columns_right:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(), str(col),
                                                     "Inner Join")

                    elif col.rstrip(suffix_left) in columns_left:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), left_sc.to_guid(), col.rstrip(suffix_left),
                                                    "Inner Join")

                    elif col.rstrip(suffix_right) in columns_right:
                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), right_sc.to_guid(),
                                                     col.rstrip(suffix_right),"Inner Join")

        return df_result_kensu

    wrapper.__doc__ = method.__doc__
    return wrapper


def wrap_external_to_pandas_transformation(method, get_inputs_lineage_fn):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()

        ext_inputs_lineage = get_inputs_lineage_fn(kensu, *args, **kwargs)  # type: GenericComputedInMemDs
        df_result = method(*args, **kwargs)

        ext_inputs_lineage.report(ksu=kensu,
                                  df_result=df_result,
                                  operation_type="sparkDf.toPandas()",
                                  report_output=kensu.report_in_mem)
        result_ksu_pandas_df = DataFrame.using(df_result)
        return result_ksu_pandas_df

    wrapper.__doc__ = method.__doc__
    return wrapper

def wrap_to_datetime(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()

        new_args = []
        for item in args:
            if isinstance(item, DataFrame):
                new_args.append(item.get_df())
            elif isinstance(item, Series):
                new_args.append(item.get_s())
            else:
                new_args.append(item)
        new_args = tuple(new_args)

        new_kwargs = {}
        for item in kwargs:
            if isinstance(kwargs[item], DataFrame):
                new_kwargs[item]=kwargs[item].get_df()
            elif isinstance(item, Series):
                new_kwargs[item]=kwargs[item].get_s()
            else:
                new_kwargs[item]=kwargs[item]

        df_result = method(*new_args, **new_kwargs)


        result_ds = eventually_report_in_mem(
            kensu.extractors.extract_data_source(df_result, kensu.default_physical_location_ref,
                                               logical_naming=kensu.logical_naming))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, df_result))

        for orig_df in args:
            orig_ds = eventually_report_in_mem(
                kensu.extractors.extract_data_source(orig_df, kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, orig_df))

            for col in [k.name for k in orig_sc.pk.fields]:
                kensu.add_dependencies_mapping(result_sc.to_guid(), col, orig_sc.to_guid(), col, 'to_datetime')

        df_result_kensu = Series.using(df_result)

        return df_result_kensu

    wrapper.__doc__ = method.__doc__
    return wrapper