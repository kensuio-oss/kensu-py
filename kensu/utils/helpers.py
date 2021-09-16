import re
from hashlib import sha1

from kensu.utils.kensu_provider import KensuProvider


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


def report_all2all_lineage(in_obj, out_obj, op_type, in_inmem=True, out_inmem=True):
    kensu = KensuProvider().instance()
    in_ds, in_schema = extract_ksu_ds_schema(kensu,
                                             in_obj,
                                             report=kensu.report_in_mem or not in_inmem,
                                             register_orig_data=not in_inmem)
    out_ds, out_schema = extract_ksu_ds_schema(kensu,
                                               out_obj,
                                               report=kensu.report_in_mem or not out_inmem,
                                               register_orig_data=not out_inmem)
    logging.debug("in_schema=" + str(in_schema) + "\nout_schema=" + str(out_schema))
    if kensu.mapping:
        for col in out_obj:
            if col in [v.name for v in in_schema.pk.fields]:
                kensu.add_dependencies_mapping(guid=out_schema.to_guid(),
                                               col=str(col),
                                               from_guid=in_schema.to_guid(),
                                               from_col=str(col),
                                               type=op_type)