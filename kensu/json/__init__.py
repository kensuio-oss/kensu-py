import json as js
from json import *

from kensu.boto3 import ksu_dict
from kensu.botocore.response import ksu_bytes
from kensu.itertools import kensu_list

def wrap_loads(method):
    def wrapper(*args, **kwargs):

        result = method(*args, **kwargs)

        data = args[0]
        if isinstance(result,dict):
            result = ksu_dict(result)
        elif isinstance(result,list):
            result = kensu_list(result)
        if isinstance(data,ksu_bytes):
            result.ksu_metadata = data.ksu_metadata

        return result

    wrapper.__doc__ = method.__doc__
    return wrapper

loads = wrap_loads(js.loads)