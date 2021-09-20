import logging

import os
# disable Kensu collector when requested to do so (e.g. inside Apache Spark executor nodes)
if "KSU_DISABLE_PY_COLLECTOR" in os.environ:
    from numpy import *
else:

    from numpy import *
    import numpy as np
    from kensu.utils.kensu_provider import KensuProvider
    from kensu.utils.dsl import mapping_strategies
    from kensu.utils.helpers import eventually_report_in_mem, get_absolute_path
    from kensu.utils.wrappers import remove_ksu_wrappers


    class ndarrayDelegator(object):
        SKIP_KENSU_FIELDS = ["_ndarray__k_nd", "INTERCEPTORS", "_ksu_loc_id"]
        SKIP_KENSU_METHODS = ["get_nd", "kensu_init", "to_string"]


        def __getattribute__(self, name):
            attr_value = object.__getattribute__(self, name)
            if name == "_ndarray__k_nd":
                return attr_value
            elif name == "__class__":
                return attr_value
            elif name in ['mean','std']:
                # fixme: lin lost?
                attr_value = object.__getattribute__(self.get_nd(), name)
                return attr_value
            elif name in ['round','reshape']:
                attr_value = object.__getattribute__(self.get_nd(), name)
                return ndarrayDelegator.handle_callable(self, name, attr_value)
            elif hasattr(attr_value, '__call__'):
                #return ndarrayDelegator.handle_callable(self, name, attr_value)
                return attr_value
            else:
                return ndarrayDelegator.handle_field(self, name, attr_value)

        @staticmethod
        def handle_callable(kensu_nd, name, attr_value):
            nd = kensu_nd.get_nd()
            delegated_pd_attr = object.__getattribute__(nd, name)


            docstring = delegated_pd_attr.__doc__
            return ndarrayDelegator.create_function_wrapper(kensu_nd, name, docstring)

        @staticmethod
        def create_function_wrapper(kensu_nd, name, docstring):
            from kensu.pandas.data_frame import Series, DataFrame
            logging.debug("Kensu wrapping function name=" + name)

            def wrapper(*args, **kwargs):

                nd = kensu_nd.get_nd()
                df_attr = object.__getattribute__(nd, name)

                kensu = KensuProvider().instance()

                # set_axis updates the DataFrame directly (self) and returns None, we loose the initial dataframe
                # so we need to create the Kensu object before
                orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(kensu_nd, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, kensu_nd))

                new_args=remove_ksu_wrappers(args)
                new_args = tuple(new_args)
                result = df_attr(*new_args, **kwargs)
                original_result = result
                result = ndarrayDelegator.wrap_returned_df(kensu_nd, result, name, nd)

                #adding the datasources, schemas and lineage to the dependencies
                if (result is not None and (isinstance(result,DataFrame) or isinstance(result,ndarray))):
                    numpy_report(kensu_nd, result, name)


                if original_result is None:
                    return None
                else:
                    return result

            wrapper.__doc__ = docstring
            return wrapper

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

                kensu = KensuProvider().instance()
                # adding the datasources, schemas and lineage to the dependencies


                if result is not None and isinstance(result, ndarray):
                    if kensu.mapping:
                        numpy_report(kensu_df,result,name)



                    else:
                        orig_ds = kensu.extractors.extract_data_source(kensu_df, kensu.default_physical_location_ref)._report()
                        orig_sc = kensu.extractors.extract_schema(orig_ds, kensu_df)._report()

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

        def __getitem__(self, item):
            returned = self.get_nd()[item]
            # fixme: input lineage lost
            if isinstance(returned,str):
                return returned
            else:
                return ndarray.using(returned)

        def __repr__(self):
            nd = self.get_nd()
            return nd.__repr__()

        @staticmethod
        def remove_np_wrapper(other):
            if isinstance(other, ndarray):
                other_np = other.get_nd()
            else:
                other_np = other
            return other_np

        def wrapped_ndarray_binary_op(self, other_input, wrapped_fn, op_title=None):
            op_title = op_title or 'Numpy ' + str(wrapped_fn.__name__)
            input_kensu_nd = self
            other_np = ndarray.remove_np_wrapper(other_input)
            result = ndarray.using(wrapped_fn(other_np))
            numpy_report(input_kensu_nd, result, op_title)
            if isinstance(other_input, ndarray):
                numpy_report(other_input, result, op_title)
            return result

        def __sub__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__sub__)

        def __add__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__add__)

        def __mul__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__mul__)

        def __divmod__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__divmod__)

        def __truediv__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__truediv__)

        def __cmp__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__cmp__)

        def __eq__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__eq__)

        def __ne__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__ne__)

        def __lt__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__lt__)

        def __gt__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__gt__)

        def __le__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__le__)

        def __ge__(self, other):
            return self.wrapped_ndarray_binary_op(other, self.get_nd().__ge__)

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

    savetxt = wrap_save(np.savetxt)


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
            kensu_result = ndarray.using(result)

            # Note: must pass a kensu wrapped result
            result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(kensu_result, kensu.default_physical_location_ref,
                                                           logical_naming=kensu.logical_naming))
            result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, kensu_result))

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

            return kensu_result

        wrapper.__doc__ = method.__doc__
        return wrapper

    where = wrap_where(np.where)

    def wrap_unique(method):
        def wrapper(*args, **kwargs):

            kensu = KensuProvider().instance()

            new_args = remove_ksu_wrappers(args)
            new_args = tuple(new_args)

            result = method(*new_args, **kwargs)
            original_result = result
            # with extra kwargs unique sometimes return tuples...
            if isinstance(original_result, np.ndarray):
                ksu_result = ndarray.using(original_result)
                numpy_report(args, ksu_result, "Numpy unique")
            elif isinstance(original_result, tuple) and all([isinstance(x, np.ndarray) for x in original_result]):
                ksu_result = tuple([ndarray.using(x) for x in original_result])
                for ksu_result_item in ksu_result:
                    numpy_report(args, ksu_result_item, "Numpy unique")
            else:
                msg = "Kensu numpy.unique got an unexpected result which may be not fully tracked"
                logging.warning(msg)
                ksu_result = original_result
            return ksu_result

        wrapper.__doc__ = method.__doc__
        return wrapper

    unique = wrap_unique(np.unique)

    def wrap_abs(method):
        def wrapper(*args, **kwargs):
            new_args = remove_ksu_wrappers(args)
            new_args = tuple(new_args)

            original_result = method(*new_args, **kwargs)
            ksu_result = ndarray.using(original_result)
            numpy_report(args,ksu_result,"Numpy abs")

            return ksu_result

        wrapper.__doc__ = method.__doc__
        return wrapper

    abs = wrap_abs(np.abs)

    def wrap_round(method):
        def wrapper(*args, **kwargs):
            new_args = remove_ksu_wrappers(args)
            new_args = tuple(new_args)

            original_result = method(*new_args, **kwargs)
            ksu_result = ndarray.using(original_result)
            numpy_report(args,ksu_result,"Numpy abs")
            return ksu_result

        wrapper.__doc__ = method.__doc__
        return wrapper

    round = wrap_round(np.round)

    def wrap_concat(method):
        def wrapper(*args, **kwargs):
            new_args = remove_ksu_wrappers(args)
            new_args = tuple(new_args)

            original_result = method(*new_args, **kwargs)
            ksu_result = ndarray.using(original_result)
            for input_nd in args:
                numpy_report(input_nd,ksu_result,"Numpy concat")
            return ksu_result

        wrapper.__doc__ = method.__doc__
        return wrapper

    concatenate = wrap_concat(np.concatenate)


    def array(method):
        def wrapper(*args, **kwargs):
            args = list(args)
            obj = args[0]
            if isinstance(obj,list):
                args[0] = remove_ksu_wrappers(obj)
                new_args = args
            else:
                new_args = remove_ksu_wrappers(args)

            new_args = tuple(new_args)

            original_result = method(*new_args, **kwargs)
            ksu_result = ndarray.using(original_result)
            numpy_report(obj, ksu_result, "Numpy array")
            return ksu_result

        wrapper.__doc__ = method.__doc__
        return wrapper

    array = array(np.array)

    def extract_sc(kensu, nd):
        try:
            orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(nd, kensu.default_physical_location_ref,
                                                                                logical_naming=kensu.logical_naming))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, nd))
        except Exception:  # thrown by default extract_data_source/extract_schema
            msg = "Kensu numpy.array got an unexpected argument which can not be fully tracked (yet): " + str(type(nd))
            logging.warning(msg)
            #import traceback
            #traceback.print_stack()
            orig_sc = None

        return orig_sc


    def numpy_report(nd,result,name):
        orig_sc_list = []

        kensu = KensuProvider().instance()
        from kensu.itertools import kensu_list

        if isinstance(nd,kensu_list):
            orig_sc_list = nd.deps
        elif isinstance(nd, tuple) or isinstance(nd, list):
            # FIXME: fail tolerance for unexpected arguments
            for input_nd in nd:
                if isinstance(input_nd, kensu_list):
                    for x in input_nd.deps:
                        orig_sc_list.append(x)
                else:
                    orig_sc_list.append(extract_sc(kensu, input_nd))
        else:
            orig_sc_list.append(extract_sc(kensu, nd))

        result_ds = eventually_report_in_mem(
            kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref,
                                                 logical_naming=kensu.logical_naming))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

        if kensu.mapping:
            for orig_sc in orig_sc_list:
                if orig_sc is not None:
                    for col in [s.name for s in result_sc.pk.fields]:
                        for col_orig in [s.name for s in orig_sc.pk.fields]:
                            kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col_orig),
                                                           name)