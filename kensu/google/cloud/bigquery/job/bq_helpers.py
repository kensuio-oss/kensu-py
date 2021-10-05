#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#

from kensu.utils.kensu_provider import KensuProvider
from google.cloud.bigquery import Table


class BqKensuHelpers:
    @staticmethod
    def table_to_kensu(table: Table):
        kensu = KensuProvider().instance()
        # note: there should be no report here!
        ds = kensu.extractors.extract_data_source(table, kensu.default_physical_location_ref,
                                                  logical_naming=kensu.logical_naming)
        sc = kensu.extractors.extract_schema(ds, table)
        return ds, sc

