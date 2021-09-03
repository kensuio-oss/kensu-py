from kensu.pandas import DataFrame,Series
from kensu.utils.kensu_provider import KensuProvider
import requests.models as md
from kensu.utils.helpers import eventually_report_in_mem
from kensu.numpy import ndarray


class Response(md.Response):
    ksu_schema = None




