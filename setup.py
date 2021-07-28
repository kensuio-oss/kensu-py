# coding: utf-8

"""


    No description provided (generated by Swagger Codegen https://github.com/swagger-api/swagger-codegen)

    OpenAPI spec version: beta

    Generated by: https://github.com/swagger-api/swagger-codegen.git
"""

import setuptools
from setuptools import setup, find_packages

NAME = "kensu"


VERSION = "1.4.1.6"


# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

#REQUIRES = ["urllib3 >= 1.15", "six >= 1.10", "certifi", "python-dateutil"]

setup(
    name=NAME,
    version=VERSION,
    description="",
    author_email="",
    url="",
    keywords=["Ingestion", "Kensu", "Data Intelligence Manager","Analytics Observability","Data Observability"],
#    install_requires=REQUIRES,
    packages=[
        package
        for package in setuptools.PEP420PackageFinder.find()
        if package.startswith("kensu")
    ],
    platforms="Posix; MacOS X; Windows",
    include_package_data=True,
    long_description="""\
    Python Client to Report Entities to Kensu Data Activity Manager\
    """
)
