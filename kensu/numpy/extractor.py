from hashlib import sha256

import numpy

import kensu
from kensu.client import FieldDef, SchemaPK, Schema, DataSource, DataSourcePK
from kensu.utils.dsl.extractors import ExtractorSupport
from kensu.utils.helpers import singleton

@singleton
class ndarraySupport(ExtractorSupport):  # should extends some KensuSupport class

    def is_supporting(self, nd):
        return isinstance(nd, numpy.ndarray)

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
        return [FieldDef(name="value", field_type=str(nd.dtype), nullable=True)]

    def extract_location(self, nd, location):
        if location is not None:
            return location
        else:
            nd = self.skip_wr(nd)
            return "in-mem://AN_ID" + sha256(str(nd.tolist()).encode("utf-8")).hexdigest()

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
        nd = self.skip_wr(nd)
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
        nd = self.skip_wr(nd)
        ds = self.extract_data_source(nd, pl, **kwargs)
        sc = self.extract_schema(ds, nd)
        return ds, sc
