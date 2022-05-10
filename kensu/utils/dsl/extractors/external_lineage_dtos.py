import logging

from kensu.client.models import Schema


class KensuDatasourceAndSchema:
    def __init__(self,
                 ksu_ds,
                 ksu_schema,
                 f_get_stats=lambda: None,
                 f_publish_stats=lambda lineage_run_id: {}):
        """
        :param kensu.client.DataSource ksu_ds: Datasource info which was extracted from external system
        :param kensu.client.Schema ksu_schema: Schema info for the datasource
        :param () -> typing.Union[typing.Dict[string, float], None] f_get_stats: [Optional] a function to retrieve DataStats for this DataSource
        :param (str) -> () f_publish_stats : [Optional] a function publishing the statistics given a lineage run guid
        """

        self.ksu_ds = ksu_ds
        self.ksu_schema = ksu_schema
        # this allows expensive delaying computation of stats until they are needed (if at all)
        self.f_get_stats = f_get_stats
        # this allows remote computation of stats to be published by the remote processor (if at all)
        self.f_publish_stats = f_publish_stats

    def field_names(self):
        return [f.name for f in self.ksu_schema.pk.fields]

    @staticmethod
    def for_path_with_opt_schema(ksu, ds_path, format=None, categories=None, maybe_schema=None, ds_name=None, f_get_stats=lambda: {}):
        from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
        pl_ref = ksu.UNKNOWN_PHYSICAL_LOCATION.to_ref()
        ds_pk = DataSourcePK(location=ds_path, physical_location_ref=pl_ref)
        ds = DataSource(name=ds_name or ds_path, format=format, categories=categories, pk=ds_pk)
        if maybe_schema is None:
            maybe_schema = [("unknown", "unknown"), ]
        # logging.debug(str(maybe_schema))
        fields = list([
            FieldDef(name=str(name), field_type=str(dtype), nullable=True)
            for (name, dtype) in maybe_schema
        ])
        schema = Schema(name="schema:" + ds.name,
                        pk=SchemaPK(ds.to_ref(), fields=fields))
        return KensuDatasourceAndSchema(ksu_ds=ds, ksu_schema=schema, f_get_stats=f_get_stats)

    def __repr__(self):
        return 'KensuDatasourceAndSchema(ksu_ds={}, ksu_schema={})'.format(str(self.ksu_ds), str(self.ksu_schema))


class ExtDependencyEntry:
    def __init__(
            self,
            input_ds=None,  # type: KensuDatasourceAndSchema
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

    def __repr__(self):
        return 'ExtDependencyEntry(input_ds={}, lineage={})'.format(str(self.input_ds), str(self.lineage))


def filter_matching_fields(fields, other_fields):
    """return fields which are same as in other_fields list, ignoring the case"""
    other_fields_lowercase = set([f.lower() for f in other_fields])
    return [f for f in fields if f.lower() in other_fields_lowercase]


def to_lds_info(path):
    # FIXME: LDS location support is not yet merged, so we must set LDS name to the path!
    return [
        f"logical::{path}",
        f"logicalLocation::{path}"
    ]

class GenericComputedInMemDs:
    def __init__(
            self,
            inputs=None,  # type: list[KensuDatasourceAndSchema]
            lineage=None  # type: list[ExtDependencyEntry]
    ):
        if inputs is None and lineage is not None:
            inputs = [item.input_ds for item in lineage]
        self.lineage = lineage or []
        self.inputs = inputs or []

    def __repr__(self):
        return 'GenericComputedInMemDs(lineage={})'.format(str(self.lineage))


    @staticmethod
    def build_approx_lineage(
            source_uris,  # type: list[str]
            source_format,  # type: str
            result_schema  # type: Schema
    ):
        from kensu.utils.kensu_provider import KensuProvider
        ksu = KensuProvider().instance()
        ksu_inputs = []
        for src_uri in source_uris:
            ksu_input = KensuDatasourceAndSchema.for_path_with_opt_schema(
                ksu=ksu,
                ds_path=src_uri,
                format=source_format,
                maybe_schema=[(f.name, f.field_type) for f in result_schema.pk.fields]
            )
            ksu_inputs.append(ksu_input)

        lineage = GenericComputedInMemDs.for_direct_or_full_mapping(
            all_inputs=ksu_inputs,
            out_field_names=[f.name for f in result_schema.pk.fields]
        )
        return ksu_inputs, lineage

    @staticmethod
    def for_direct_or_full_mapping(
            all_inputs,  # type: list[KensuDatasourceAndSchema]
            out_field_names # type: list[str]
                                   ):
        inputs_with_matching_fields = [(i, filter_matching_fields(i.field_names(), out_field_names))
                                       for i in all_inputs
                                       if len(filter_matching_fields(i.field_names(), out_field_names)) > 0]

        global_lineage = []

        if len(inputs_with_matching_fields) > 0:
            # direct lineage only for matching fields/DSes
            for input, matching_input_fields in inputs_with_matching_fields:
                matching_output_fields = filter_matching_fields(out_field_names, matching_input_fields)
                lin_entry = ExtDependencyEntry(
                    input_ds=input,
                    # lineage: dict[str-output field, list[str]-input fields]
                    lineage=dict(
                        [(out_field_name, filter_matching_fields(input.field_names(), [out_field_name]))
                         for out_field_name in matching_output_fields])
                )
                global_lineage.append(lin_entry)
        else:
            # all-to-all lineage between all output fields & all input DSes fields
            for input in all_inputs:
                lin_entry = ExtDependencyEntry(
                    input_ds=input,
                    # lineage: dict[str-output field, list[str]-input fields]
                    lineage=dict(
                        [(out_field_name, [v.name for v in input.field_names()])
                         for out_field_name in out_field_names])
                )
                global_lineage.append(lin_entry)
        return GenericComputedInMemDs(lineage=global_lineage)



    # FIXME: rename register_output_orig_data -> output_is_not_in_mem ?
    def report(self, ksu, df_result, operation_type, report_output=False, register_output_orig_data=False):
        from kensu.utils.helpers import extract_ksu_ds_schema
        from kensu.utils.dsl import mapping_strategies
        for input_ds in self.inputs:
            extract_ksu_ds_schema(ksu, input_ds, report=True, register_orig_data=True)
        # report output (if needed)
        if isinstance(df_result,Schema):
            result_ds = None
            result_schema = df_result._report()
            ksu.real_schema_df[result_schema.to_guid()] = df_result
        else:
            result_ds, result_schema = extract_ksu_ds_schema(ksu, df_result, report=report_output, register_orig_data=register_output_orig_data)
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
    def report_copy_with_opt_schema(src, dest, operation_type, maybe_schema=None, dest_name=None, src_name=None,
                                    src_categories=None, dest_categories=None):
        from kensu.utils.kensu_provider import KensuProvider
        ksu = KensuProvider().instance()
        if src_categories is None:
            src_categories = to_lds_info(src)
        if dest_categories is None:
            dest_categories = to_lds_info(dest)
        input_ds = KensuDatasourceAndSchema.for_path_with_opt_schema(ksu=ksu, ds_path=src, maybe_schema=maybe_schema, ds_name=src_name, categories=src_categories)
        output_ds = KensuDatasourceAndSchema.for_path_with_opt_schema(ksu=ksu, ds_path=dest, maybe_schema=maybe_schema, ds_name=dest_name, categories=dest_categories)
        if maybe_schema is None:
            maybe_schema = [("unknown", "unknown")]
        lineage_info = [ExtDependencyEntry(
            input_ds=input_ds,
            # FIXME: kensu-py lineage do not work without schema as well...
            lineage=dict([(str(fieldname), [str(fieldname)])
                          for (fieldname, dtype) in maybe_schema]))]
        inputs_lineage = GenericComputedInMemDs(inputs=[input_ds], lineage=lineage_info)
        # register lineage in KensuProvider
        inputs_lineage.report(ksu=ksu, df_result=output_ds, operation_type=operation_type, report_output=True, register_output_orig_data=True)
        # actuly report the lineage and the write operation
        ksu.report_with_mapping()
