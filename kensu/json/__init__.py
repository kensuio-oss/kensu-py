import json as js
from json import *

from kensu.boto3 import ksu_dict
from kensu.botocore.response import ksu_bytes
from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
from kensu.itertools import kensu_list
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema
from kensu.utils.helpers import logical_naming_batch
from kensu.utils.kensu_provider import KensuProvider


def wrap_loads(method):
    def wrapper(*args, **kwargs):

        result = method(*args, **kwargs)

        kensu = KensuProvider().instance()

        data = args[0]
        if isinstance(result,dict):
            result = ksu_dict(result)
        elif isinstance(result,list):
            result = kensu_list(result)
        if isinstance(data,ksu_bytes):
            result.ksu_metadata = data.ksu_metadata

            origin_location = result.ksu_metadata['origin_location']
            origin_name = result.ksu_metadata['origin_name']

            if kensu.logical_naming == 'ReplaceNumbers':
                logical = logical_naming_batch(origin_name)
            else:
                logical = origin_name

            #FIXME we should put this in extractors
            result_pk = DataSourcePK(location=origin_location,
                                     physical_location_ref=kensu.default_physical_location_ref)
            result_ds = DataSource(name=origin_name, categories=['logical::' + logical], format=origin_name.split('.')[-1],
                                   pk=result_pk)._report()

            fields_set = set()

            if isinstance(result, list):
                for element in result:
                    for e in element.keys():
                        fields_set.add(('[].' + str(e), type(e).__name__))
            elif isinstance(result, dict):
                for e in result.keys():
                    fields_set.add((e, type(e).__name__))
            else:
                fields_set.add(('value', 'unknown'))

            fields = [FieldDef(name=k[0], field_type=k[1], nullable=True) for k in fields_set]

            sc_pk = SchemaPK(result_ds.to_ref(),
                             fields=fields)

            short_result_sc = Schema(name="short-schema:" + result_ds.name, pk=sc_pk)._report()

            kensu.real_schema_df[short_result_sc.to_guid()] = None

            kensu.add_input_ref(KensuDatasourceAndSchema(ksu_ds=result_ds, ksu_schema=short_result_sc))

        return result

    wrapper.__doc__ = method.__doc__
    return wrapper

loads = wrap_loads(js.loads)