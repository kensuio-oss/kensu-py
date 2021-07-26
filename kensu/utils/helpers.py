import json
import re
from hashlib import sha1

from numpy.random import RandomState


def to_snake_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def singleton(cls, *args, **kw):
    instances = {}

    def _singleton():
        if cls not in instances:
            instances[cls] = cls(*args, **kw)
        return instances[cls]

    return _singleton


def to_hash_key(o):
    return sha1(str(o).encode()).hexdigest()


def eventually_report_in_mem(o):
    from kensu.utils.kensu_provider import KensuProvider
    kensu = KensuProvider().instance()
    if kensu.report_in_mem:
        o._report()
    return o


def get_absolute_path(path):
    import os
    for prefix in ["abfss", "/abfss", "dbfs", "/dbfs"]:
        if path.startswith(prefix):
            path = path.replace(prefix, '')
            prefix = prefix.replace('/', '')
            return prefix + ':' + path
    return 'file:' + str(os.path.abspath(path))


def maybe_report(o, report):
    from kensu.utils.kensu_provider import KensuProvider
    dam = KensuProvider().instance()
    if report:
        o._report()
    return o


def extract_ksu_ds_schema(kensu, orig_variable, report=False, register_orig_data=False):
    ds = kensu.extractors.extract_data_source(orig_variable, kensu.default_physical_location_ref, logical_naming=kensu.logical_naming)
    schema = kensu.extractors.extract_schema(ds, orig_variable)
    maybe_report(ds, report=report)
    maybe_report(schema, report=report)
    if register_orig_data:
        kensu.real_schema_df[schema.to_guid()] = orig_variable
    return ds, schema


def new_arg(list_or_args):
    from kensu.pandas import Series, DataFrame
    from kensu.numpy import ndarray
    def new_args(list_or_args):
        new_args = []
        for item in list_or_args:
            if isinstance(item, Series):
                new_args.append(item.get_s())
            elif isinstance(item,DataFrame):
                new_args.append(item.get_df())
            elif isinstance(item, ndarray):
                new_args.append(item.get_nd())
            else:
                new_args.append(item)
        return new_args

    if isinstance(list_or_args, list):
            list_or_args[0] = new_args(list_or_args[0])
            new_args = list_or_args
    else:
        new_args = new_args(list_or_args)

    new_args = tuple(new_args)
    return new_args