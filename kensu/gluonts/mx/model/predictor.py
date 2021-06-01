import gluonts.mx.model.predictor as pred
from kensu.utils.helpers import eventually_report_in_mem
from kensu.pandas.data_frame import DataFrame,Series
from kensu.numpy import ndarray
from gluonts.dataset.common import ListDataset
from kensu.utils.kensu_provider import KensuProvider
from kensu.gluonts.model.forecast import SampleForecast

class RepresentableBlockPredictor(pred.RepresentableBlockPredictor):

    def predict(self, Y, *args, **kwargs):
        dep_fields = []
        if isinstance(Y, ListDataset):
            new_Field = []
            old_Field = Y.list_data

            for element in Y.list_data:
                new_dict = {}

                for key in element.keys():
                    item = element[key]

                    if isinstance(item, DataFrame):
                        new_item = item.get_df()
                        dep_fields.append(new_item)
                    elif isinstance(item, Series):
                        new_item = item.get_s()
                        dep_fields.append(new_item)
                    elif isinstance(item, ndarray):
                        new_item = item.get_nd()
                        dep_fields.append(new_item)
                    else:
                        new_item = item
                    new_dict[key] = new_item
                new_Field.append(new_dict)
            Y.list_data = new_Field

        original_result = list(super(RepresentableBlockPredictor, self).predict(dataset=Y, *args, **kwargs))


        if isinstance(Y, ListDataset):
            Y.list_data = old_Field

        deps = []
        kensu = KensuProvider().instance()

        for element in dep_fields:
            orig_ds = eventually_report_in_mem(
                kensu.extractors.extract_data_source(element, kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming))
            orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, element))
            deps.append(orig_sc)

        def e(iterable):
            for b in iterable:
                b.__class__ = SampleForecast
                b.dependencies = deps
                yield b

        result = e(original_result)

        return result

