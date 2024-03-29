import itertools

from kensu.requests.models import ksu_str



from kensu.numpy import ndarray
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.helpers import eventually_report_in_mem
class chain(itertools.chain):
    deps = []

    @classmethod
    def from_iterable(self,iterables):
        # chain('ABC', 'DEF') --> A B C D E F
        for it in iterables:
            kensu = KensuProvider().instance()
            if isinstance(it,ndarray):
                orig_it = it
                it = it.get_nd()
                orig_ds = eventually_report_in_mem(
                    kensu.extractors.extract_data_source(orig_it, kensu.default_physical_location_ref))
                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, orig_it))
                self.deps.append(orig_sc)

            for element in it:
                yield element
            if self.deps != []:
                yield self.deps




class kensu_list(list):
    ksu_metadata = {}
    deps=[]
    def __init__(self, *args):
        list.__init__(self, *args)
        self.add_deps()

    def add_deps(self):
        from kensu.client.models.schema import Schema
        if isinstance(self[-1],list):
            if isinstance(self[-1][0],Schema):
                self.deps = self[-1]
                del self[-1]

    def __getitem__(self, item):
        from kensu.boto3 import ksu_dict
        result = super(kensu_list, self).__getitem__(item)
        if isinstance(result,str):
            ksu_result = ksu_str(result)
        elif isinstance(result,list):
            ksu_result = kensu_list(result)
        elif isinstance(result,dict):
            ksu_result = ksu_dict(result)
        else:
            ksu_result = result

        if hasattr(ksu_result,'ksu_metadata'):
            ksu_result.ksu_metadata = self.ksu_metadata
        return ksu_result