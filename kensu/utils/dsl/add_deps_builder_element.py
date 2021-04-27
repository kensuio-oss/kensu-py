from kensu.utils.dsl.ended_builder_element import EndedBuilderElement


class AddDepsBuilderElement(object):
    def __init__(self, builder):
        self.builder = builder

    def link(self, output_field_name, input_fields_name_array, type):
        c = self.builder.control
        if type == "data": c = self.builder.data
        c[output_field_name] = input_fields_name_array
        return self

    def filter_io(self, outs, ins):
        if outs is None:
            kept_outs = self.builder.output_fields_name
        else:
            kept_outs = [n for n in self.builder.output_fields_name if n in outs]

        if ins is None:
            kept_ins = self.builder.input_fields_name
        else:
            kept_ins = [n for n in self.builder.input_fields_name if n in ins]

        return (kept_outs, kept_ins)

    def with_strategy(self, mapping_strategy, type="data"):
        return mapping_strategy.map(self, type)

    def direct(self, outs=None, ins=None, type="data"):
        c = self.builder.control
        if type == "data": c = self.builder.data

        (kept_outs, kept_ins) = self.filter_io(outs, ins)
        for f in kept_outs:
            if f in kept_ins:
                c[f] = [f]
        return self

    def full(self, outs=None, ins=None, type="data"):
        c = self.builder.control
        if type == "data": c = self.builder.data

        (kept_outs, kept_ins) = self.filter_io(outs, ins)

        for f in kept_outs:
            c[f] = kept_ins
        return self

    @property
    def e(self):
        return self.end_dependency()

    def end_dependency(self):
        self.builder.lineage_builder.add_deps(EndedBuilderElement(self.builder))
        return self.builder.lineage_builder