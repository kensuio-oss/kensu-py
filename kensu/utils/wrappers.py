from kensu.utils.kensu_provider import KensuProvider


def remove_ksu_wrapper(arg):
    # FIXME: fix possible import issues if dependency libs not installed...
    from kensu.pandas import DataFrame
    from kensu.pandas import Series
    from kensu.numpy import ndarray

    if isinstance(arg, DataFrame):
        return arg.get_df()
    elif isinstance(arg, Series):
        return arg.get_s()
    elif isinstance(arg, ndarray):
        return arg.get_nd()
    else:
        return arg


def remove_ksu_wrappers(args):
    new_args = []
    for arg in args:
        new_args.append(remove_ksu_wrapper(arg))
    return new_args

def remove_ksu_kwargs_wrappers(kwargs):
    new_kwargs = {}
    for item in kwargs:
        new_kwargs[item]=remove_ksu_wrapper(kwargs[item])
    return new_kwargs

def kensu_wrapper(method):
    def wrapper(*args, **kwargs):
        new_args = remove_ksu_wrappers(args)
        new_kwargs = remove_ksu_kwargs_wrappers(kwargs)

        result = method(*new_args, **new_kwargs)
        return result

    wrapper.__doc__ = method.__doc__
    return wrapper

def kensu_wrapper_and_report(method,obj):

    from kensu.pandas import DataFrame
    from kensu.pandas import Series
    from kensu.numpy import ndarray

    def wrapper(*args, **kwargs):
        new_args = remove_ksu_wrappers(args)
        new_kwargs = remove_ksu_kwargs_wrappers(kwargs)

        for arg in args:
            if isinstance(arg, DataFrame) or isinstance(arg, Series) or isinstance(arg, ndarray) :
                obj.add_inheritance(arg)
        for kwarg in kwargs:
            if isinstance(kwargs[kwarg],list):
                for item in kwargs[kwarg]:
                    if isinstance(item, DataFrame) or isinstance(item, Series) or isinstance(item, ndarray) :
                        obj.add_inheritance(item)
            elif isinstance(kwargs[kwarg], DataFrame) or isinstance(kwargs[kwarg], Series) or isinstance(kwargs[kwarg], ndarray) :
                obj.add_inheritance(kwargs[kwarg])

        result = method(*new_args, **new_kwargs)
        return result

    wrapper.__doc__ = method.__doc__
    return wrapper