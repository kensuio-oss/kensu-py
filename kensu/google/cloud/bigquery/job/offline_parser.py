#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging

from google.cloud.bigquery import Table

from kensu.google.cloud.bigquery.job.bq_helpers import BqKensuHelpers
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema, GenericComputedInMemDs, \
    ExtDependencyEntry
from kensu.utils.helpers import extract_ksu_ds_schema
from kensu.utils.kensu import Kensu
import google.cloud.bigquery as bq
import sqlparse

logger = logging.getLogger(__name__)


class BqOfflineParser:

    # FIXME: or should we better simply fetch schema ALL visible tables and databases !!!!???
    @staticmethod
    def get_referenced_tables_metadata(
            kensu: Kensu,
            client: bq.Client,
            query: str = None,
            table: Table = None):
        if query:
            table_infos = BqOfflineParser.get_table_info_from_sql(client, query)
        elif table:
            tb = client.get_table(table)
            ds,sc = BqKensuHelpers.table_to_kensu(tb)
            table_infos = [(tb,ds,sc)]

        # for table, ds, sc in table_infos:
        #     # FIXME: this possibly don't fit here well...
        #     kensu.real_schema_df[sc.to_guid()] = table

        table_id_to_bqtable = {}
        metadata = {"tables": []}
        for table, ds, sc in table_infos:
            table_id = "`" + table.full_table_id.replace(":", ".") + "`"  # FIXME: replace this in DS extractor too!
            table_md = {
                "id": table_id,
                "schema": {
                    "fields": [{"name": f.name, "type": f.field_type} for f in sc.pk.fields]
                }
            }
            table_id_to_bqtable[table_id] = table
            metadata["tables"].append(table_md)
        return metadata,  table_id_to_bqtable, table_infos

    @staticmethod
    def get_table_info_for_id(client: bq.Client, id: sqlparse.sql.Identifier or sqlparse.sql.Token):
        try:
            if isinstance(id,sqlparse.sql.Identifier):
                name = (id.get_real_name()).strip('`')
            elif isinstance(id,sqlparse.sql.Token):
                name = id.value.strip('`')
            table = client.get_table(name)
            ds, sc = BqKensuHelpers.table_to_kensu(table)  # FIXME?
            return table, ds, sc
        except Exception as e:
            logger.debug("get_table_info_for_id failed for table={}, maybe not BQ table: {}".format(id, str(e)))
            # FIXME this is because the current find_sql_identifiers also returns the column names...
            #  (see aboveREF_GET_TABLE)
            #  Therefore get_table of a column name should fail
            return None

    @staticmethod
    def get_table_info_from_sql(client: bq.Client, query: str):
        sq = sqlparse.parse(query)
        ids = BqOfflineParser.find_sql_identifiers(sq[0].tokens)  # FIXME we only take the first element
        table_infos = list(
            filter(lambda x: x is not None, [BqOfflineParser.get_table_info_for_id(client, id) for id in ids]))
        return table_infos

    @staticmethod
    def find_sql_identifiers(tokens):
        for e in tokens:
            for t in e.flatten():
                if str(t.ttype) == "Token.Name":
                    yield t

    @staticmethod
    def fallback_lineage(kensu, table_infos, dest):
        res_ds, res_schema = extract_ksu_ds_schema(kensu, orig_variable=dest, report=False, register_orig_data=False)
        res_field_names = [f.name for f in res_schema.pk.fields]
        all_inputs = []
        for input_table, input_ds, input_sc in table_infos:
            if res_ds.pk.location == input_ds.pk.location:
                continue
            input = KensuDatasourceAndSchema.for_path_with_opt_schema(
                kensu,
                ds_path=input_ds.pk.location,
                ds_name=input_ds.name,
                format='BigQuery table',
                categories=None,
                maybe_schema=[(f.name, f.field_type) for f in input_sc.pk.fields],
                f_get_stats= None # FIXME: needs input filters
            )
            all_inputs.append(input)
        return GenericComputedInMemDs.for_direct_or_full_mapping(all_inputs=all_inputs, out_field_names=res_field_names)