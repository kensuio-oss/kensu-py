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
