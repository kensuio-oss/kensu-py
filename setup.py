# coding: utf-8

import setuptools
from setuptools import setup, find_packages
import os

# Provide option to deliver only a subset of the packages related to pyspark for python3.5 to a different artifact name, so
# we have these builds:
# - pyspark build - kensu-pyspark, include only a few packages
# - normal build - kensu, include everything
DELIVERY_ARTIFACT_NAME = os.environ["DELIVERY_ARTIFACT_NAME"] if "DELIVERY_ARTIFACT_NAME" in os.environ else ""
PYSPARK_ARTIFACT_NAME = "kensu-pyspark"
REGULAR_ARTIFACT_NAME = "kensu"


def is_py35_pyspark_delivery():
    return PYSPARK_ARTIFACT_NAME in DELIVERY_ARTIFACT_NAME


def artifact_name():
    if is_py35_pyspark_delivery():
        return PYSPARK_ARTIFACT_NAME
    else:
        return REGULAR_ARTIFACT_NAME


NAME = artifact_name()


BUILD_FLAVOR = os.environ["BUILD_FLAVOR"] if "BUILD_FLAVOR" in os.environ else ""
BUILD_NUMBER = os.environ["BUILD_NUMBER"] if "BUILD_NUMBER" in os.environ else ""
# https://semver.org/
VERSION = "2.8.1" + BUILD_FLAVOR + BUILD_NUMBER




# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

def get_extra_requires(path, add_all=True, add_all_but_test=True, add_no_extra_deps=True):
    import re
    from collections import defaultdict

    with open(path) as fp:
        extra_deps = defaultdict(set)
        for k in fp:
            if k.strip() and not k.startswith('#'):
                tags = set()
                if ':' in k:
                    k, v = k.split(':')
                    tags.update(vv.strip() for vv in v.split(','))
                tags.add(re.split('[<=>]', k)[0])
                for t in tags:
                    extra_deps[t].add(k)

        # add tag `all` at the end
        if add_all:
            extra_deps['all'] = set(vv for v in extra_deps.values() for vv in v)

        # add tag `all-but-test` at the end
        if add_all_but_test:
            extra_deps['all-but-test'] = set(vv for v in extra_deps.values() for vv in v if vv != "test")

        if add_no_extra_deps:
            extra_deps['no-extra-deps'] = set()


    print("Collected the following dependencies from " + path + ":")
    print(extra_deps)

    return extra_deps


def get_install_requires(path):
    with open(path) as fp:
        deps = []
        for l in fp:
            if l.strip() and not l.startswith('#'):
                deps.append(l)
        return deps


def maybe_filter_py35packages(package):
    if is_py35_pyspark_delivery():
        package_ok = package.startswith("kensu.pyspark") or \
            package.startswith("kensu.utils.remote") or \
            package.startswith("kensu.utils.kensu_conf_file")
    else:
        package_ok = True
    print("Got package: {}, include={}".format(package, package_ok))
    return package_ok


setup(
    name=NAME,
    version=VERSION,
    description="",
    author_email="",
    url="",
    keywords=["DODD", "Data Observability Driven Development", "Data Observability", "Analytics Observability"],
    packages=[
        package
        for package in setuptools.PEP420PackageFinder.find()
        if (package.startswith("kensu") and maybe_filter_py35packages(package)) or \
            package == "kensu"
    ],
    install_requires=get_install_requires('common-requirements.txt'),
    extras_require=get_extra_requires('extra.requirements'),
    platforms="Posix; MacOS X; Windows",
    # - when delivering only kensu-pyspark (minimal sub-set of kensu-py compatible with py3.5),
    # we have to use include_package_data=False to exclude uneeded .py files which are not compatible with py3.5
    # - when delivering regular kensu-py, we have to use include_package_data=True to include all .py files as normal
    include_package_data=not is_py35_pyspark_delivery(),
    long_description="""\
    DODD Python Agent: enable Data Observability Driven Development in your Python script\
    """
)
