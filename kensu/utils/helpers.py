import re
from hashlib import sha1




def to_snake_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def singleton(cls, *args, **kw):
    instances = {}

    def _singleton():
        if cls not in instances:
            instances[cls] = cls(*args, **kw)
        return instances[cls]

    return _singleton


def to_hash_key(o):
    return sha1(str(o).encode()).hexdigest()

def eventually_report_in_mem(o):
    from kensu.utils.kensu_provider import KensuProvider
    kensu = KensuProvider().instance()
    if kensu.report_in_mem:
        o._report()
    return o

