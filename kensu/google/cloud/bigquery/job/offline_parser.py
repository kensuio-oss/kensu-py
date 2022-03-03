#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging
import re
from typing import Union

from google.cloud.bigquery import Table, TableReference

from kensu.google.cloud.bigquery.job.bq_helpers import BqKensuHelpers
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema, GenericComputedInMemDs, \
    ExtDependencyEntry
from kensu.utils.helpers import extract_ksu_ds_schema
from kensu.utils.kensu import Kensu
import google.cloud.bigquery as bq
import sqlparse

logger = logging.getLogger(__name__)


class BqOfflineParser:

    @staticmethod
    def normalize_table_refs(q):
        # FIXME: this might be still quite error prone in non-standard use-cases...
        """
        >>> normalize_table_refs('SELECT * FROM `a1`.`b2`.`c3`')
        'SELECT * FROM `a1.b2.c3`'
        """
        matches = re.findall(r'`([a-zA-Z0-9-_]+)`.`([a-zA-Z0-9-_]+)`.`([a-zA-Z0-9-_]+)`', q)
        for (s1, s2, s3) in matches:
            q = q.replace(f'`{s1}`.`{s2}`.`{s3}`', f'`{s1}.{s2}.{s3}`')

        return q

    @staticmethod
    def get_referenced_tables_metadata(
            kensu: Kensu,
            client: bq.Client,
            job,  # type: google.cloud.bigquery.job.QueryJob
            query: str = None,
            table: Table = None):
        table_infos = []
        if job:
            # Referenced tables for the job. Queries that reference more than 50 tables will not have a complete list.
            # FIXME: separate referenced from ddl target
            referenced_tables = job.referenced_tables + [j for j in [job.ddl_target_table] if j] # type: list[TableReference]
            # [TableReference(DatasetReference('project', 'db'), 'table')]
            table_infos = list([BqOfflineParser.table_ref_to_kensu(client, table_id=t)
                            for t in referenced_tables])
        is_bigquery_api_limit_reached = len(table_infos) > 49
        if not table_infos or is_bigquery_api_limit_reached:
            fallback_tables = list(BqOfflineParser.fallback_referenced_tables_from_sql(kensu=kensu,
                                                                              client=client,
                                                                              query=query,
                                                                              table=query))
            table_infos = list(set(table_infos + fallback_tables))
        return BqOfflineParser.to_sql_util_metadata(table_infos)


    # FIXME: or should we better simply fetch schema for ALL visible tables and databases !!!!???
    @staticmethod
    def fallback_referenced_tables_from_sql(
            kensu: Kensu,
            client: bq.Client,
            query: str = None,
            table: Table = None):
        # FIXME: return table/tableRef here?!
        if query:
            table_infos = BqOfflineParser.get_table_info_from_sql(client, query)
        elif table:
            table_infos = [BqOfflineParser.table_ref_to_kensu(client, table_id=table)]
        else:
            table_infos = []
        return table_infos


    @staticmethod
    def to_sql_util_metadata(table_infos):
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
    def table_ref_to_kensu(
            client: bq.Client,
            table_id: Union[Table, TableReference, str],
    ):
        table = client.get_table(table_id)
        ds, sc = BqKensuHelpers.table_to_kensu(table)
        return table, ds, sc

    @staticmethod
    def get_table_info_for_id(client: bq.Client, id: sqlparse.sql.Identifier or sqlparse.sql.Token):
        try:
            if isinstance(id,sqlparse.sql.Identifier):
                name = (id.get_real_name()).strip('`')
            elif isinstance(id,sqlparse.sql.Token):
                name = id.value.strip('`')
            return BqOfflineParser.table_ref_to_kensu(client, table_id=name)
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
                # FIXME: hmm, are stats not implemented for fallback mode? also needs input filters
                f_get_stats=lambda: None
            )
            all_inputs.append(input)
        return GenericComputedInMemDs.for_direct_or_full_mapping(all_inputs=all_inputs, out_field_names=res_field_names)