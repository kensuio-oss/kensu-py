import gluonts.mx.model.predictor as pred

from kensu.gluonts.ksu_utils.dataset_helpers import make_dataset_reliable
from kensu.utils.helpers import eventually_report_in_mem
from gluonts.dataset.common import ListDataset
from kensu.utils.kensu_provider import KensuProvider
from kensu.gluonts.model.forecast import SampleForecast

class RepresentableBlockPredictor(pred.RepresentableBlockPredictor):

    def predict(self, Y, *args, **kwargs):
        Y, old_Field, dep_fields = make_dataset_reliable(Y)

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

