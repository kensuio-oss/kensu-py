from kensu.client import SchemaLineageDependencyDef

class EndedBuilderElement(object):
    def __init__(self, builder):
        self.builder = builder
        self.input = self.builder.input
        self.input_schema = self.builder.input_schema
        self.output = self.builder.output
        self.output_schema = self.builder.output_schema

    def toSchemaLineageDependencyDef(self):
        return SchemaLineageDependencyDef(from_schema_ref=self.builder.input_schema.to_ref(),
                                          to_schema_ref=self.builder.output_schema.to_ref(),
                                          column_data_dependencies=self.builder.data,
                                          column_control_dependencies=self.builder.control)
