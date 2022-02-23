import logging
from hashlib import sha256

import matplotlib.pyplot as plt


import kensu
from kensu.client import *
from kensu.utils.dsl.extractors import ExtractorSupport, get_or_set_rand_location
from kensu.utils.helpers import singleton, save_stats_json, to_datasource
from kensu.utils.kensu_provider import KensuProvider

@singleton
class PlotSupport(ExtractorSupport):  # should extends some KensuSupport class

    def is_supporting(self, fig):
        return isinstance(fig,  plt.Figure)

    def is_machine_learning(self, df):
        return False

    # return list of FieldDef
    def extract_schema_fields(self, fig):
        k=KensuProvider().instance()
        fields = []
        for ax in fig.axes:
            for df in ax.inheritance:
                fields_ax_df = k.extractors.extract_schema_fields(df)
                fields = fields + fields_ax_df
        return fields

    # return dict of doubles (stats)
    def extract_stats(self, fig):
        kensu = KensuProvider().instance()
        stats = {}
        ax_num = 0
        for ax in fig.axes:
            source_num = 0
            for df in ax.inheritance:
                #TODO : extract ax name if any instead of generic number
                inherited_stats = {'Ax'+str(ax_num)+'.Source'+str(source_num)+'.'+key : value for key,value in kensu.extractors.extract_stats(df).items()}
                stats = {**stats,**inherited_stats}
                source_num+=1
            ax_num += 1
        return stats

    def extract_data_source(self, fig, pl, **kwargs):

        logical_naming = kwargs["logical_naming"] if "logical_naming" in kwargs else None
        location = kwargs["location"] if "location" in kwargs else None
        fmt = 'matplotlib image'

        if location is None or fmt is None:
            raise Exception(
                "cannot report new matplotlib data source without location ({}) a format provided ({})!".format(location,
                                                                                                          fmt))

        ds_pk = DataSourcePK(location=location, physical_location_ref=pl)


        name = ('/').join(location.split('/')[-2:])

        ds=to_datasource(ds_pk, fmt, location, logical_naming, name)
        return ds

    def extract_schema(self, data_source, fig):
        fields = self.extract_schema_fields(fig)
        sc_pk = SchemaPK(data_source.to_ref(), fields=fields)
        schema = Schema(name="schema:" + data_source.name, pk=sc_pk)
        return schema

    def extract_data_source_and_schema(self, df, pl, **kwargs):
        df = self.skip_wr(df)
        ds = self.extract_data_source(df, pl, **kwargs)
        sc = self.extract_schema(ds, df)
        return ds, sc