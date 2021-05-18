class KensuDatasourceAndSchema:
    def __init__(self,
                 ksu_ds,
                 ksu_schema,
                 f_get_stats=lambda: {}):
        """
        :param kensu.client.DataSource ksu_ds: Datasource info which was extracted from external system
        :param kensu.client.Schema ksu_schema: Schema info for the datasource
        :param () -> typing.Dict[string, float] f_get_stats: [Optional] a function to retrieve DataStats for this DataSource
        """
        self.ksu_ds = ksu_ds
        self.ksu_schema = ksu_schema
        # this allows expensive delaying computation of stats until they are needed (if at all)
        self.f_get_stats = f_get_stats

    @staticmethod
    def for_path_without_schema(ksu, ds_path, format=None, categories=None):
        from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
        pl_ref = ksu.UNKNOWN_PHYSICAL_LOCATION.to_ref()
        ds_pk = DataSourcePK(location=ds_path, physical_location_ref=pl_ref)
        ds = DataSource(name=ds_path, format=format, categories=categories, pk=ds_pk)
        fields = [
            FieldDef(name=str("unknown"), field_type="unknown", nullable=True),
        ]
        schema = Schema(name="schema:" + ds.name,
                        pk=SchemaPK(ds.to_ref(), fields=fields))
        return KensuDatasourceAndSchema(ksu_ds=ds, ksu_schema=schema)


class ExtDependencyEntry:
    def __init__(
            self,
            input_ds,  # type: KensuDatasourceAndSchema
            # {out_column: [input_column1, input_column2, ...]}
            lineage=None  # type: dict[str, list[str]]
    ):
        """
        :param KensuDatasourceAndSchema input_ds:
        :param typing.Dict[str, typing.List[str]]  lineage: format is  `{out_column: [input_column1, input_column2, ...]}`
        """
        self.input_ds = input_ds
        if lineage is None:
            lineage = {}
        self.lineage = lineage


class GenericComputedInMemDs:
    def __init__(
            self,
            inputs,  # type: list[KensuDatasourceAndSchema]
            lineage  # type: list[ExtDependencyEntry]
    ):
        self.lineage = lineage
        self.inputs = inputs

    def report(self, ksu, df_result, operation_type):
        from kensu.utils.helpers import extract_ksu_ds_schema
        from kensu.utils.dsl import mapping_strategies
        for input_ds in self.inputs:
            extract_ksu_ds_schema(ksu, input_ds, report=True, register_orig_data=True)
        # report output (if needed)
        result_ds, result_schema = extract_ksu_ds_schema(ksu, df_result, report=ksu.report_in_mem, register_orig_data=True)
        # register the lineage
        for dep in self.lineage:
            input_ds = dep.input_ds
            # at column level
            if ksu.mapping:
                # lineage = { out_column: [input_column1, ...] }
                for out_col, input_cols in dep.lineage.items():
                    for in_col in input_cols:
                        # FIXME: maybe there's an issue here is that result_schema DO NOT physically exist?
                        ksu.add_dependencies_mapping(guid=result_schema.to_guid(),
                                                     col=str(out_col),
                                                     from_guid=input_ds.ksu_schema.to_guid(),
                                                     from_col=str(in_col),
                                                     type=operation_type)
            # at datasource level (not column lineage info known)
            else:
                i=(input_ds, input_ds.ksu_ds, input_ds.ksu_schema)
                o=(df_result, result_ds, result_schema)
                ksu.add_dependency(i=i,
                                   o=o,
                                   mapping_strategy=mapping_strategies.FULL)


    @staticmethod
    def report_copy_without_schema(src, dest, operation_type):
        from kensu.utils.kensu_provider import KensuProvider
        ksu = KensuProvider().instance()
        input_ds = KensuDatasourceAndSchema.for_path_without_schema(ksu=ksu, ds_path=src)
        output_ds = KensuDatasourceAndSchema.for_path_without_schema(ksu=ksu, ds_path=dest)
        lineage_info = [ExtDependencyEntry(
            input_ds=input_ds,
            # FIXME: kensu-py lineage do not work without schema as well...
            lineage={
                "unknown": ["unknown"],
            })]
        inputs_lineage = GenericComputedInMemDs(inputs=[input_ds], lineage=lineage_info)
        # register lineage in KensuProvider
        inputs_lineage.report(ksu=ksu, df_result=output_ds, operation_type="sftp.put()")
        # actuly report the lineage and the write operation
        ksu.report_with_mapping()
