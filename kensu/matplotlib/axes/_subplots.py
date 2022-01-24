import matplotlib.axes._subplots as sbp
from kensu.utils.wrappers import kensu_wrapper_and_report

class AxesSubplot(sbp.AxesSubplot):
    inheritance = []

    def add_inheritance(self, arg):
        self.inheritance.append(arg)







        # from kensu.utils.wrappers import kensu_wrapper_and_report
        # for f in dir(cls):
        #     if callable(getattr(cls, f)) and f.startswith('__') is False and f != "add_inheritance":
        #         exec("setattr(cls,f, kensu_wrapper_and_report(cls.%s,cls))" % f)
