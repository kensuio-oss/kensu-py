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
