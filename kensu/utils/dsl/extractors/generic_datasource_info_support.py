from kensu.utils.dsl.extractors import ExtractorSupport
from kensu.utils.helpers import singleton

from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema


@singleton
class GenericDatasourceInfoSupport(ExtractorSupport):  # should extends some DamSupport class

    def is_supporting(self, df):
        return isinstance(df, KensuDatasourceAndSchema)

    def is_machine_learning(self, df):
        return False

    # return dict of doubles (stats)
    # stats are reported inside spark itself (?)
    def extract_stats(self, df):
        print('starting waiting for datastats for {}'.format(df.ksu_ds.name))
        stats = df.f_get_stats()
        print('done waiting for datastats for {}'.format(df.ksu_ds.name))
        return stats

    def extract_data_source(self,
                            ds,  # type: KensuDatasourceAndSchema
                            pl,
                            **kwargs):
        return ds.ksu_ds

    def extract_schema(
            self,
            data_source,
            df  # type: KensuDatasourceAndSchema
    ):
        return df.ksu_schema

    def extract_data_source_and_schema(self, df, pl, **kwargs):
        ds = self.extract_data_source(df, pl, **kwargs)
        sc = self.extract_schema(ds, df)
        return ds, sc
