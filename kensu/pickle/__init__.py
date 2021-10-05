import os
# disable Kensu collector when requested to do so (e.g. inside Apache Spark executor nodes)
if "KSU_DISABLE_PY_COLLECTOR" in os.environ:
    from pickle import *
else:
    import pickle as pk
    from .pickle import wrap_dump,wrap_load
    if hasattr(pk, "dump"):
        dump = wrap_dump(pk.dump)
    if hasattr(pk, "load"):
        load = wrap_load(pk.load)
