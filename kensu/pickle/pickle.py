import pickle as pk
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.helpers import eventually_report_in_mem


def wrap_dump(method):
    def wrapper(*args, **kwargs):

        if ('kensu.sklearn') in str(args[0].__class__):
            fmt = 'Sklearn Model'

        else:
            fmt = 'Unknown'
        kensu = KensuProvider().instance()

        result = method(*args, **kwargs)

        loc = args[1].name
        model = args[0]

        def get_absolute_path(path):
            import os
            return 'file:'+str(os.path.abspath(path))

        location = get_absolute_path(loc)



        orig_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(model.attr[0], kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming,format=fmt))
        orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, model.attr[0]))


        result_ds = kensu.extractors.extract_data_source(model.attr[0], kensu.default_physical_location_ref, location = location,
                                                       logical_naming=kensu.logical_naming,format=fmt)._report()
        result_sc = kensu.extractors.extract_schema(result_ds, model.attr[0])._report()

        kensu.real_schema_df[result_sc.to_guid()] = model
        kensu.model[result_sc.to_guid()] = model.attr

        if kensu.mapping == True:
            for col in [s.name for s in result_sc.pk.fields]:
                kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col),
                                             "Pickle Dump")
            kensu.report_with_mapping()


        return result

    wrapper.__doc__ = method.__doc__
    return wrapper

def wrap_load(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()
        result = method(*args, **kwargs)

        loc = args[0].name
        model = result

        def get_absolute_path(path):
            import os
            return 'file:'+str(os.path.abspath(path))

        location = get_absolute_path(loc)

        if ('sklearn') in str(args[0].__class__):
            fmt = 'Sklearn Model'
        else:
            fmt = 'Unknown'

        orig_ds = (kensu.extractors.extract_data_source(model.attr[0], kensu.default_physical_location_ref,
                                                                              location=location, logical_naming=kensu.logical_naming,format=fmt))._report()
        orig_sc = (kensu.extractors.extract_schema(orig_ds, model.attr[0]))._report()


        result_ds = eventually_report_in_mem(kensu.extractors.extract_data_source(model.attr[0], kensu.default_physical_location_ref,
                                                       logical_naming=kensu.logical_naming,format=fmt))
        result_sc = eventually_report_in_mem(kensu.extractors.extract_schema(result_ds, model.attr[0]))

        kensu.real_schema_df[orig_sc.to_guid()] = result
        kensu.model[orig_sc.to_guid()] = model.attr

        if kensu.mapping == True:
            for col in [s.name for s in result_sc.pk.fields]:
                kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col),
                                             "Pickle Load")


        return result

    wrapper.__doc__ = method.__doc__
    return wrapper