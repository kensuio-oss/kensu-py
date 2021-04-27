import pickle as pk
from .pickle import wrap_dump,wrap_load
if hasattr(pk, "dump"):
    dump = wrap_dump(pk.dump)
if hasattr(pk, "load"):
    load = wrap_load(pk.load)