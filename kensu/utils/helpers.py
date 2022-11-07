import logging
import re
from hashlib import sha1
import os

# fixme: circular import, so need to inline in each fn?
# from kensu.utils.kensu_provider import KensuProvider

from kensu.client import FieldDef, SchemaPK, Schema, DataSource


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
    if path.startswith('gs:/'):
        return path
    for prefix in ["abfss", "/abfss", "dbfs", "/dbfs"]:
        if path.startswith(prefix):
            path = path.replace(prefix, '')
            prefix = prefix.replace('/', '')
            return prefix + ':' + path
    location = 'file:' + str(os.path.abspath(path))
    return location


def maybe_report(o, report):
    from kensu.utils.kensu_provider import KensuProvider
    kensu = KensuProvider().instance()
    if report:
        o._report()
    return o


def extract_ksu_ds_schema(kensu, orig_variable, report=False, register_orig_data=False):
    ds = kensu.extractors.extract_data_source(orig_variable, kensu.default_physical_location_ref, logical_data_source_naming_strategy=kensu.logical_naming)
    schema = kensu.extractors.extract_schema(ds, orig_variable)
    maybe_report(ds, report=report)
    maybe_report(schema, report=report)
    if register_orig_data:
        kensu.real_schema_df[schema.to_guid()] = orig_variable
    return ds, schema


def report_all2all_lineage(in_obj, out_obj, op_type, in_inmem=True, out_inmem=True):
    from kensu.utils.kensu_provider import KensuProvider
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


def report_simple_copy_with_guessed_schema(input_uri,  # type: str
                                           output_absolute_uri,  # type: str
                                           read_schema_from_filename,  # type: str
                                           operation_type,  # type: str
                                           ):
    from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs
    try:
        maybe_schema = None
        logging.info(f"report_simple_copy_with_guessed_schema input={input_uri} output={output_absolute_uri}")
        if read_schema_from_filename.endswith('.csv'):
            try:
                import kensu.pandas as pd
                # FIXME: how to handle multiple possibilities for CSV separators? e.g. sep=";"
                maybe_pandas_df = pd.read_csv(read_schema_from_filename)
                from kensu.utils.kensu_provider import KensuProvider
                ksu = KensuProvider().instance()
                _, schema = extract_ksu_ds_schema(ksu, maybe_pandas_df, report=False, register_orig_data=False)
                maybe_schema = [(f.name, f.field_type) for f in schema.pk.fields]
            except Exception as ex:
                logging.warning("unable to guess schema of .csv() file", ex)
        GenericComputedInMemDs.report_copy_with_opt_schema(
            src=input_uri,
            dest=output_absolute_uri,
            operation_type=operation_type,
            maybe_schema=maybe_schema
        )
    except Exception as e:
        logging.warning(f"caught exception in dumb_parse_curl", e)


def flatten(d, parent_key='', sep='.'):
    items = []
    if isinstance(d,list):
        for element in d:
            items.extend(flatten(element, parent_key='[]', sep=sep).items())
    else:
        for k, v in d.items():
            new_key = parent_key + sep + k if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                if isinstance(v[0], dict):
                    new_key = new_key + '[]'
                    for i in v:
                        items.extend(flatten(i, new_key, sep=sep).items())
            else:
                items.append((new_key, type(v).__name__))
    return dict(items)

def logical_naming_batch(string):
    from itertools import groupby, chain
    grouped = groupby(string, str.isdigit)
    return ''.join(chain.from_iterable("<number>" if k else g for k,g in grouped))


def to_datasource(ds_pk, format, location, logical_data_source_naming_strategy, name):
    if logical_data_source_naming_strategy == 'File':
        logical_category = location.split('/')[-1]
        ds = DataSource(name=name, format=format, categories=['logical::' + logical_category], pk=ds_pk)

    elif logical_data_source_naming_strategy == 'Folder':
        logical_category = location.split('/')[-2]
        ds = DataSource(name=name, format=format, categories=['logical::' + logical_category], pk=ds_pk)

    elif logical_data_source_naming_strategy == 'AnteFolder':
        logical_category = location.split('/')[-3]
        ds = DataSource(name=name, format=format, categories=['logical::' + logical_category], pk=ds_pk)

    elif logical_data_source_naming_strategy == 'ReplaceNumbers':
        logical_category = logical_naming_batch(name)
        ds = DataSource(name=name, format=format, categories=['logical::' + logical_category], pk=ds_pk)

    elif callable(logical_data_source_naming_strategy):
        # TODO create to_datasource for all extractors - limited to pandas DataFrame and BigQuery for now
        try:
            logical_category = logical_data_source_naming_strategy(location)
        except Exception as e:
            logging.warning("data source logical_data_source_naming_strategy function passed to initKensu or KensuProvider instance"
                            " returned an exception, "
                            "using default data source naming convention. \n {}".format(e))
            logical_category = location.split('/')[-1]
        ds = DataSource(name=name, format=format, categories=['logical::' + logical_category], pk=ds_pk)

    else:
        ds = DataSource(name=name, format=format, categories=[], pk=ds_pk)
    return ds

def save_stats_json(schemaID,stats):
    from kensu.utils.kensu_provider import KensuProvider
    kensu = KensuProvider().instance()
    kensu.schema_stats[schemaID]=stats

def extract_short_json_schema(result, result_ds):
    fields_set = set()
    if isinstance(result, list):
        for element in result:
            if isinstance(element,dict):
                for e in element.keys():
                    fields_set.add(('[].' + str(e), type((element[e])).__name__))
            else:
                fields_set.add(('value', 'unknown'))
    elif isinstance(result, dict):
        for e in result.keys():
            fields_set.add((e, type(result[e]).__name__))
    else:
        fields_set.add(('value', 'unknown'))
    fields = [FieldDef(name=k[0], field_type=k[1], nullable=True) for k in fields_set]

    sc_pk = SchemaPK(result_ds.to_ref(),fields=fields)

    short_result_sc = Schema(name="short-schema:" + result_ds.name, pk=sc_pk)
    return short_result_sc


def extract_config_property(key, default, arg=None, kw=None, conf=None, tpe=None):
    """
    Looks for a property value following this precedence:
      env_var > arg > kwargs > conf > default
    The default value is used to determine the type of the conf value (it can be overridden by tpe).
    The environment variable will be looked up based on the pattern of `KSU_<upper-key>`.
    """
    env_var_key = "KSU_" + key.upper()
    if os.environ.get(env_var_key) is not None:
        env_var = os.environ.get(env_var_key)
        if tpe is not None:
            env_var = tpe(env_var)
        return env_var
    elif arg is not None:
        return arg
    elif key in kw and kw[key] is not None:
        return kw[key]
    elif key in conf and conf.get(key) is not None:
        if default is not None and tpe is None:
            tpe = type(default)
        r = conf.get(key)
        if tpe is list:
            r = r.replace(" ", "").split(",")
        elif tpe is bool:
            r = conf.getboolean(key)
        elif tpe is not None:
            r = tpe(r)
        return r
    else:
        return default


def get_conf_path(default = "conf.ini"):
    return os.environ["KSU_CONF_FILE"] if "KSU_CONF_FILE" in os.environ else default