from kensu.pandas import DataFrame,Series
from kensu.utils.kensu_provider import KensuProvider
import requests.models as md
from kensu.utils.helpers import eventually_report_in_mem
from kensu.numpy import ndarray

import builtins
# Extended subclass
class ksu_str(str):
    ksu_metadata = None

class Response(md.Response):

    ksu_schema = None
    ksu_short_schema = None
    ksu_stats = None

    @property
    def text(self) -> str:
        result = super(Response, self).text
        ksu_result = ksu_str(result)
        ksu_result.metadata = {"short_schema":self.ksu_short_schema, "real_schema":self.ksu_schema, "ds_location":self.ds_location, "stats":self.ksu_stats}
        return ksu_result



