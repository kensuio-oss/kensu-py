import sklearn.metrics as mk
from kensu.numpy import ndarray
from kensu.pandas import DataFrame,Series

def wrap_classification(method):
    def wrapper(*args, **kwargs):

        new_args=[]
        for arg in args:
            if isinstance(arg,DataFrame):
                new_args.append(arg.get_df())
            elif isinstance(arg,Series):
                new_args.append(arg.get_s())
            elif isinstance(arg, ndarray):
                new_args.append(arg.get_nd())
            else:
                new_args.append(arg)

        result = method(*new_args, **kwargs)

        return result

    wrapper.__doc__ = method.__doc__
    return wrapper


classification_report = wrap_classification(mk.classification_report)
