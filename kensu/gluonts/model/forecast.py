import gluonts.model.forecast as spf
from kensu.utils.helpers import eventually_report_in_mem
from kensu.utils.kensu_provider import KensuProvider


class SampleForecast(spf.SampleForecast):
    dependencies = None

    def create_deps(self, result):
        deps = self.dependencies

        kensu = KensuProvider().instance()
        for orig_sc in deps:

            result_ds = eventually_report_in_mem(
                kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming))
            result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, result))

            for result_col in [k.name for k in result_sc.pk.fields]:
                for orig_col in [k.name for k in orig_sc.pk.fields]:
                    kensu.add_dependencies_mapping(result_sc.to_guid(), str(result_col), orig_sc.to_guid(), str(orig_col),
                                                   "Model")



    @property
    def mean(self):
        import numpy as np
        from kensu.numpy import ndarray
        if self._mean is not None:
            return self._mean
        else:
            result = ndarray.using(np.mean(self.samples, axis=0))
            self.create_deps(result)
            return result