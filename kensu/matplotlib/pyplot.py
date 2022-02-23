from matplotlib.pyplot import *
import matplotlib.pyplot as plt
from functools import partial

from kensu.utils.helpers import eventually_report_in_mem, get_absolute_path


def subplots(*args,**kwargs):
    orig_return = plt.subplots(*args, **kwargs)

    for i in range(len(orig_return[1])):
        def add_inheritance(self, arg):
            self.inheritance.append(arg)
        orig_return[1][i].inheritance = []
        orig_return[1][i].add_inheritance = partial(add_inheritance, orig_return[1][i])

        from kensu.utils.wrappers import kensu_wrapper_and_report
        for f in dir(orig_return[1][i]):
            if f in ['bar','boxplot','hist','hist2d','plot','plot_date']:
                exec("setattr(orig_return[1][i],f, kensu_wrapper_and_report(orig_return[1][i].%s,orig_return[1][i]))" % f)
    return orig_return



def savefig(*args, **kwargs):
    fig = gcf()
    res = fig.savefig(*args, **kwargs)
    fig.canvas.draw_idle() # need this if 'transparent=True' to reset colors

    from kensu.utils.kensu_provider import KensuProvider
    kensu = KensuProvider().instance()

    name = args[0]
    location = get_absolute_path(args[0])

    fig_ds = kensu.extractors.extract_data_source(fig, kensu.default_physical_location_ref,
                                                  logical_naming=kensu.logical_naming, location=location)._report()
    fig_sc = kensu.extractors.extract_schema(fig_ds,fig)._report()

    kensu.real_schema_df[fig_sc.to_guid()] = fig

    for ax in fig.axes:
        if (ax.inheritance) is not []:
            for element in ax.inheritance:
                orig_ds = eventually_report_in_mem(
                    kensu.extractors.extract_data_source(element, kensu.default_physical_location_ref,
                                                         logical_naming=kensu.logical_naming))

                orig_sc = eventually_report_in_mem(kensu.extractors.extract_schema(orig_ds, element))

                for col in [k.name for k in orig_sc.pk.fields]:
                    kensu.add_dependencies_mapping(fig_sc.to_guid(), col, orig_sc.to_guid(), col, 'fig')
    kensu.report_with_mapping()

    return res