import sklearn.metrics as mk
from kensu.numpy import ndarray
from kensu.pandas import DataFrame,Series
from kensu.utils.wrappers import remove_ksu_wrappers


def wrap_classification(method):
    def wrapper(*args, **kwargs):
        new_args=remove_ksu_wrappers(args)
        result = method(*new_args, **kwargs)
        return result

    wrapper.__doc__ = method.__doc__
    return wrapper


classification_report = wrap_classification(mk.classification_report)
