import logging

import numpy as np

from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.dsl import mapping_strategies
from kensu.utils.helpers import eventually_report_in_mem

class ndarrayDelegator(object):
    SKIP_KENSU_FIELDS = ["_ndarray__k_nd", "INTERCEPTORS"]
    SKIP_KENSU_METHODS = ["get_nd", "kensu_init", "to_string"]

    def __getattribute__(self, name):
        attr_value = object.__getattribute__(self, name)
        if name == "_ndarray__k_nd":
            return attr_value
        elif name == "__class__":
            return attr_value
        elif hasattr(attr_value, '__call__'):
            # return ndarrayDelegator.handle_callable(self, name, attr_value)
            return attr_value
        else:
            return ndarrayDelegator.handle_field(self, name, attr_value)

    @staticmethod
    def wrap_returned_df(kensu_s, returned, name, original):
        if isinstance(returned, np.ndarray) \
                and not isinstance(returned, ndarray) \
                and original is not returned:
            logging.debug("Wrapping attr access resulting ndarray in KensuDF for property name=" + name)
            tmp = ndarray.using(returned)
            returned = tmp
        return returned

    @staticmethod
    def handle_field(kensu_df, name, attr_value):
        # _DataFrame__k_df => points to DataFrame.__k_df
        if name in ndarrayDelegator.SKIP_KENSU_FIELDS:
            # return Kensu DF attr value right away
            logging.debug("Kensu attribute name=" + name)
            return attr_value
        else:
            logging.debug("NOT Kensu, let's delegate attribute name=" + name)

            nd = kensu_df.get_nd()
            nd_attr = object.__getattribute__(nd, name)
            result = ndarrayDelegator.wrap_returned_df(kensu_df, nd_attr, name, nd)

            # adding the datasources, schemas and lineage to the dependencies
            if result is not None and isinstance(result, ndarray):
                kensu = KensuProvider().instance()
                orig_ds = kensu.extractors.extract_data_source(nd, kensu.default_physical_location_ref)._report()
                orig_sc = kensu.extractors.extract_schema(orig_ds, nd)._report()

                result_ds = kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref)._report()
                result_sc = kensu.extractors.extract_schema(result_ds, result)._report()

                kensu.add_dependency((nd, orig_ds, orig_sc), (result, result_ds, result_sc),
                                   mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            return result


class ndarray(ndarrayDelegator, np.ndarray):
    __k_nd = None

    # https://numpy.org/doc/stable/user/basics.subclassing.html
    def __new__(subtype, shape, dtype=float, buffer=None, offset=0, strides=None, order=None):
        obj = super(ndarray, subtype).__new__(subtype, shape, dtype, buffer, offset, strides, order)
        return obj

    def __array_finalize__(self, obj):
        if obj is None: return
        self.__k_nd = getattr(obj, '__k_nd', None)

    @staticmethod
    def using(o):
        if isinstance(o, ndarray):
            d = ndarray.using(o.get_nd())
            return d
        else:
            d = ndarray(o.shape,o.dtype)
            d.kensu_init(o)
            return d

    def get_nd(self):
        # if the current Kensu ndarray isn't delegating... TODO.. need to have a type for this instead...
        if self.__k_nd is None:
            return self
        else:
            return self.__k_nd

    def kensu_init(self, d):
        self.__k_nd = d


def wrap_save(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        result = method(*args, **kwargs)


        loc = args[0]
        df = args[1]
        def get_absolute_path(path):
            import os
            return 'file:'+str(os.path.abspath(path))

        if df.__class__ == ndarray:

            location = get_absolute_path(loc)

            orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref,
                                                         logical_naming=kensu.logical_naming))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, df))


            result_ds = kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref, location = location,
                                                           logical_naming=kensu.logical_naming)._report()
            result_sc = kensu.extractors.extract_schema(result_ds,df)._report()

            kensu.real_schema_df[result_sc.to_guid()] = result
            

            if kensu.mapping == True:
                for col in [s.name for s in result_sc.pk.fields]:
                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col),
                                                 "save")
                kensu.report_with_mapping()


        return result

    wrapper.__doc__ = method.__doc__
    return wrapper

savetext = wrap_save(np.savetxt)


def wrap_where(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()

        origins = []
        new_args = []
        condition = [args[0]]
        for item in args:
            from kensu.pandas import Series
            if isinstance(item,Series):
                new_args.append(item.get_s())
            else:
                new_args.append(item)
        for item in args[1:]:
            if isinstance(item,Series):
                origins.append(item)
        new_args = tuple(new_args)

        result = method(*new_args, **kwargs)

        result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref,
                                                       logical_naming=kensu.logical_naming))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

        for element in origins:
            df = element.get_s()

            orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref,
                                                                                  logical_naming=kensu.logical_naming))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, df))

            if kensu.mapping == True:
                for col in [s.name for s in result_sc.pk.fields] :
                    for col_orig in [s.name for s in orig_sc.pk.fields]:

                        kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col_orig),
                                                     "Numpy Where")
        result = ndarray.using(result)
        return result

    wrapper.__doc__ = method.__doc__
    return wrapper


where = wrap_where(np.where)