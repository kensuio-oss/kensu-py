from kensu.utils.dsl.with_output_builder_element import WithOutputBuilderElement


class ProcessLineageDepsBuilder(object):
    def __init__(self, kensu, lineage_builder):
        self.kensu = kensu
        self.lineage_builder = lineage_builder

        self.input = None
        self.input_data_source = None
        self.input_schema = None
        self.input_fields_name = None

        self.output = None
        self.output_data_source = None
        self.output_schema = None
        self.output_fields_name = None

        self.data = {}
        self.control = {}

    def with_input(self, i):  # input => pandas df for example
        if self.input is None:
            if isinstance(i, tuple):
                value = i[0]
                data_source = i[1]
                schema = i[2]
            else:
                value = i
                kensu = self.builder.kensu
                data_source = kensu.extractors.extract_data_source(value, kensu.default_physical_location_ref)
                schema = kensu.extractors.extract_schema(data_source, value)

            self.input = value
            self.input_data_source = data_source._report()
            self.input_schema = schema._report()
            self.input_fields_name = [f.name for f in self.input_schema.pk.fields]

        return WithOutputBuilderElement(self)
