from hashlib import sha256

import numpy

import kensu
from kensu.client import FieldDef, SchemaPK, Schema, DataSource, DataSourcePK
from kensu.utils.dsl.extractors import ExtractorSupport, get_or_set_rand_location, get_rand_location
from kensu.utils.helpers import singleton

@singleton
class ndarraySupport(ExtractorSupport):  # should extends some KensuSupport class

    def is_supporting(self, nd):
        return isinstance(nd, numpy.ndarray) or isinstance(nd, kensu.numpy.ndarray)

    def is_machine_learning(self, nd):
        return False

    def skip_wr(self, nd):
        if isinstance(nd, kensu.numpy.ndarray):
            return nd.get_nd()
        else:
            return nd

    # return list of FieldDef
    def extract_schema_fields(self, nd):
        nd = self.skip_wr(nd)
        if nd.dtype.names == None :
            return [FieldDef(name="value", field_type=str(nd.dtype), nullable=True)]
        else:
            d = list()
            for key, item in nd.dtype.fields.items():
                d.append(FieldDef(name=key, field_type=str(item[0]), nullable=True))
            return d

    def extract_location(self, nd, location):
        if location is not None:
            return location
        else:
            if not isinstance(nd, kensu.numpy.ndarray):
                # not wrapped numpy.ndarray do not (easily) allow to set extra attributes,
                # so return a random uuid even if we expect a stable one
                # otherwise - AttributeError: numpy.ndarray' object has no attribute '_ksu_loc_id'
                print('WARN: kensu ndarraySupport.extract_location got unexpected arg type: '+str(type(nd)))
                try:
                    raise Exception("no error, just marking stack trace for debugging")
                except Exception:  # thrown by default extract_data_source/extract_schema
                    import traceback
                    traceback.print_stack()
                return get_rand_location()
            else:
                return get_or_set_rand_location(nd)

    def extract_format(self, nd, fmt):
        if fmt is not None:
            return fmt
        else:
            nd = self.skip_wr(nd)
            return nd.__class__.__name__

    def tk(self, k, k1): return k + '.' + k1

    # return dict of doubles (stats)
    def extract_stats(self, nd):
        nd = self.skip_wr(nd)
        #TODO use scipy.stats?
        #return {self.tk(k, k1): v for k, o in nd.describe().to_dict().items() for k1, v in o.items()}
        return {"count": len(nd)}

    def extract_data_source(self, nd, pl, **kwargs):
        location = self.extract_location(nd, kwargs.get("location"))
        fmt = self.extract_format(nd, kwargs.get("format"))

        if location is None or fmt is None:
            raise Exception(
                "cannot report new pandas dataframe without location ({}) a format provided ({})!".format(location, fmt))

        ds_pk = DataSourcePK(location=location, physical_location_ref=pl)
        name = location
        ds = DataSource(name=name, format=fmt, categories=[], pk=ds_pk)
        return ds

    def extract_schema(self, data_source, nd):
        nd = self.skip_wr(nd)
        fields = self.extract_schema_fields(nd)
        sc_pk = SchemaPK(data_source.to_ref(), fields=fields)
        schema = Schema(name="schema:"+data_source.name, pk=sc_pk)
        return schema

    def extract_data_source_and_schema(self, nd, pl, **kwargs):
        ds = self.extract_data_source(nd, pl, **kwargs)
        sc = self.extract_schema(ds, nd)
        return ds, sc
