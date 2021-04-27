class Strategy(object):

    @staticmethod
    def from_dict(d):
        """
        Create a Strategy based on a dict where
        - Keys are the output field names
        - Values an array of the inputs fields names used to create the output
        :param d: a dict of output -> [input]
        :return a Strategy using the dict to build the mappings
        """
        return Strategy(lambda i, o: o in d.keys() and i in d[o])

    def __init__(self, mapping_function):
        self.mapping_function = mapping_function

    def map(self, add_deps_builder_element, type="data"):
        c = add_deps_builder_element.builder.control
        if type == "data":
            c = add_deps_builder_element.builder.data

        for o in add_deps_builder_element.builder.output_fields_name:
            for i in add_deps_builder_element.builder.input_fields_name:
                if self.mapping_function(i, o):
                    if o not in c:
                        c[o] = []
                    c[o].append(i)

        return add_deps_builder_element

    def or_else(self, next_strategy):
        """
        Chains current Strategy with a next one in case an input and output aren't mapping in the current one.
        This allows to define general strategies followed by more specific ones,
        like DIRECT.or_else(map_2_specific_fields_only_strategy)
        :param next_strategy: the next Strategy to be used if the current doesn't pass
        :return: a Strategy combining the mapping of the current one and the next one
        """

        def f(i, o):
            return self.mapping_function(i, o) or next_strategy.mapping_function(i, o)

        s = Strategy(f)
        return s


FULL = Strategy(lambda i, o: True)
DIRECT = Strategy(lambda i, o: i == o)
def from_simple_io_dict(di):
    return Strategy(lambda i, o: di[i]==o)
OUT_STARTS_WITH_IN = Strategy(lambda i,o: o[0:len(i)] == i)

