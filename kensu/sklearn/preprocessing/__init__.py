import logging

from functools import reduce
import re

import sklearn.preprocessing as pp

from kensu.numpy import ndarray
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.dsl import mapping_strategies

class StandardScalerDelegator(object):
    SKIP_KENSU_FIELDS = ["_StandardScaler__k_sc", "INTERCEPTORS"]
    SKIP_KENSU_METHODS = ["get_sc", "kensu_init", "to_string"]

    def __getattribute__(self, name):
        attr_value = object.__getattribute__(self, name)
        if name == "_StandardScaler__k_sc":
            return attr_value
        elif name == "__class__":
            return attr_value
        elif hasattr(attr_value, '__call__'):
            return StandardScalerDelegator.handle_callable(self, name, attr_value)
        else:
            #StandardScalerDelegator.handle_field(self, name, attr_value)
            return attr_value

    @staticmethod
    def wrap_returned_df(kensu_sc, returned, name, original):
        if isinstance(returned, pp.StandardScaler) \
                and not isinstance(returned, StandardScaler) \
                and original is not returned:
            logging.debug("Wrapping attr access resulting StandardScaler in KensuDF for property name=" + name)
            tmp = StandardScaler.using(returned)
            returned = tmp
        return returned

    @staticmethod
    def handle_callable(kensu_sc, name, attr_value):
        if name not in StandardScalerDelegator.SKIP_KENSU_METHODS:
            sc = object.__getattribute__(kensu_sc, "get_sc")()
            if isinstance(getattr(type(sc), name), property):
                delegated_pd_attr = object.__getattribute__(sc, name)
                # todo ? -> StandardScalerDelegator.handle_callable_property(kensu_sc, name, sc, delegated_pd_attr)
                return delegated_pd_attr
            else:
                delegated_pd_attr = object.__getattribute__(sc, name)
                docstring = delegated_pd_attr.__doc__
                return StandardScalerDelegator.create_function_wrapper(kensu_sc, name, docstring)
        else:
            logging.debug("Kensu function name=" + name)

            # return Kensu DF function result right away
            def w(*args, **kwargs):
                return attr_value(*args, **kwargs)
            return w

    @staticmethod
    def create_function_wrapper(kensu_sc, name, docstring):
        logging.debug("Kensu wrapping function name=" + name)

        def wrapper(*args, **kwargs):
            # call method on delegated df
            delegation_config = getattr(kensu_sc, 'INTERCEPTORS', None)

            for regex_attr_name in delegation_config:
                result_regex = regex_attr_name.search(name)
                if result_regex is not None:
                    # if we pass the regex, there is an interception defined, so we execute it
                    name_of_intercept_method = delegation_config[regex_attr_name]
                    intercept = object.__getattribute__(kensu_sc, name_of_intercept_method)
                    intercept(result_regex, *args, **kwargs)

            sc = kensu_sc.get_sc()
            s_attr = object.__getattribute__(sc, name)

            result = s_attr(*args, **kwargs)
            result = StandardScalerDelegator.wrap_returned_df(kensu_sc, result, name, sc)

            #adding the datasources, schemas and lineage to the dependencies
            if result_regex is None \
                    and result is not None:
                if name == "fit_transform":
                    kensu = KensuProvider().instance()
                    orig_o = args[0]
                    orig_ds = kensu.extractors.extract_data_source(orig_o, kensu.default_physical_location_ref)._report()
                    orig_sc = kensu.extractors.extract_schema(orig_ds, orig_o)._report()

                    if not isinstance(result, ndarray):
                        result = ndarray.using(result)

                    result_ds = kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref)._report()
                    result_sc = kensu.extractors.extract_schema(result_ds, result)._report()

                    kensu.add_dependency((orig_o, orig_ds, orig_sc), (result, result_ds, result_sc),
                                       mapping_strategy=mapping_strategies.OUT_STARTS_WITH_IN)

            return result

        wrapper.__doc__ = docstring
        return wrapper

class StandardScaler(StandardScalerDelegator, pp.StandardScaler):
    INTERCEPTORS = {
        re.compile('to_(.*)'): 'k_to_format'
    }

    __k_sc = None

    @staticmethod
    def using(o):
        if isinstance(o, StandardScaler):
            d = StandardScaler.using(o.get_sc())
            return d
        else:
            d = StandardScaler()
            d.kensu_init(o)
            return d

    def get_sc(self):
        # if the current Kensu StandardScaler isn't delegating... TODO.. need to have a type for this instead...
        if self.__k_sc is None:
            return self
        else:
            return self.__k_sc

    def kensu_init(self, d):
        self.__k_sc = d
