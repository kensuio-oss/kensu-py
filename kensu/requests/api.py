from kensu.client import DataSourcePK, DataSource, SchemaPK, Schema, FieldDef
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.helpers import eventually_report_in_mem,flatten

import requests as req

def wrap_get(method):
    def wrapper(*args, **kwargs):
        result = method(*args, **kwargs)

        kensu = KensuProvider().instance()

        result_pk = DataSourcePK(location=result.url,
                                 physical_location_ref=kensu.default_physical_location_ref)
        result_ds = DataSource(name=result.url, format='API',
                               pk=result_pk)._report()


        fields_dict = flatten(result.json())

        fields = [FieldDef(name = k,  field_type=fields_dict[k], nullable=True ) for k in  fields_dict]
        sc_pk = SchemaPK(result_ds.to_ref(),
                         fields=fields)

        result_sc = Schema(name="schema:" + result_ds.name, pk=sc_pk)._report()
        return result

    wrapper.__doc__ = method.__doc__
    return wrapper

get = wrap_get(req.get)