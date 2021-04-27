class WithOutputBuilderElement(object):
    def __init__(self, builder):
        self.builder = builder

    def with_output(self, o):
        if self.builder.output is None:
            if isinstance(o, tuple):
                value = o[0]
                data_source = o[1]
                schema = o[2]
            else:
                value = o
                kensu = self.builder.kensu
                data_source = kensu.extractors.extract_data_source(value, kensu.default_physical_location_ref)
                schema = kensu.extractors.extract_schema(data_source, value)

            self.builder.output = value
            self.builder.output_data_source = data_source._report()
            self.builder.output_schema = schema._report()
            self.builder.output_fields_name = [f.name for f in self.builder.output_schema.pk.fields]

        from kensu.utils.dsl.add_deps_builder_element import AddDepsBuilderElement
        return AddDepsBuilderElement(self.builder)
