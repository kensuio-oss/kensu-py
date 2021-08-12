#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging
import traceback

from kensu.google.cloud.bigquery.job.bigquery_stats import compute_bigquery_stats
from kensu.pandas import DataFrame
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema, GenericComputedInMemDs, \
    ExtDependencyEntry
from kensu.utils.kensu import Kensu
from kensu.utils.kensu_provider import KensuProvider
import google.cloud.bigquery as bq
import google.cloud.bigquery.job as bqj
from google.cloud.bigquery import Table
import sqlparse


class BqCommonHelpers:
    @staticmethod
    def table_to_kensu(table: Table):
        kensu = KensuProvider().instance()
        ds = kensu.extractors.extract_data_source(table, kensu.default_physical_location_ref,
                                                  logical_naming=kensu.logical_naming)._report()
        sc = kensu.extractors.extract_schema(ds, table)._report()
        return ds, sc


class BqOfflineParser:

    # FIXME: or should we better simply fetch schema ALL visible tables and databases !!!!???
    @staticmethod
    def get_referenced_tables_metadata(
            kensu: Kensu,
            client: bq.Client,
            query: str):
        table_infos = BqOfflineParser.get_table_infos_from_sql(client, query)
        # for table, ds, sc in table_infos:
        #     # FIXME: this possibly don't fit here well...
        #     kensu.real_schema_df[sc.to_guid()] = table

        table_id_to_schema_id = {}
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
            table_id_to_schema_id[table_id] = sc.to_guid()  # FIXME: should be not here?
            metadata["tables"].append(table_md)
        return metadata, table_id_to_schema_id, table_id_to_bqtable, table_infos

    @staticmethod
    def get_table_info_for_id(client: bq.Client, id: sqlparse.sql.Identifier):
        try:
            name = (id.get_real_name()).strip('`')
            table = client.get_table(name)
            ds, sc = BqCommonHelpers.table_to_kensu(table)  # FIXME?
            return table, ds, sc
        except:
            # FIXME this is because the current find_sql_identifiers also returns the column names...
            #  (see aboveREF_GET_TABLE)
            #  Therefore get_table of a column name should fail
            return None

    @staticmethod
    def get_table_infos_from_sql(client: bq.Client, query: str):
        sq = sqlparse.parse(query)
        ids = BqOfflineParser.find_sql_identifiers(sq[0].tokens)  # FIXME we only take the first element
        table_infos = list(
            filter(lambda x: x is not None, [BqOfflineParser.get_table_info_for_id(client, id) for id in ids]))
        return table_infos

    @staticmethod
    def find_sql_identifiers(tokens):
        for t in tokens:
            if isinstance(t, sqlparse.sql.Identifier):
                if t.is_group and len(t.tokens) > 0:
                    # String values like "World" in `N == "World"` are also Identifier
                    # but their first child is of ttype `Token.Literal.String.Symbol`
                    # although table seems to have a first child of ttype `Token.Name`
                    if str(t.tokens[0].ttype) == "Token.Name":
                        # FIXME .. this is also returning the column names... (REF_GET_TABLE)
                        yield t
            elif t.is_group:
                yield from BqOfflineParser.find_sql_identifiers(t)

    @staticmethod
    def fallback_lineage(kensu, table_infos, dest):
        global_lineage = []
        for table, ds, sc in table_infos:
            ds_path = ds.pk.location
            schema_fields = [(f.name, f.field_type) for f in sc.pk.fields]
            input = KensuDatasourceAndSchema.for_path_with_opt_schema(
                kensu,
                ds_path=ds_path,
                format='BigQuery table',
                categories=None,
                maybe_schema=schema_fields,
                f_get_stats=None  # FIXME
            )
            lin_entry = ExtDependencyEntry(
                input_ds=input,
                lineage=dict([(v.name, v.name) for v in sc.pk.fields])  # FIXME: check if output field exists
            )
            global_lineage.append(lin_entry)
        return global_lineage


class BqRemoteParser:

    @staticmethod
    def parse(kensu, client: bq.Client, query: str, db_metadata, table_id_to_bqtable) -> GenericComputedInMemDs:
        ## POST REQUEST to /lineage-and-stats-criterions
        req = {"sql": query, "metadata": db_metadata}
        url = kensu.conf.get("sql.util.url")
        logging.debug("sending request to SQL parsing service url={} request={}".format(url, str(req)))
        import requests
        lineage_resp = requests.post(url + "/lineage-and-stats-criterions", json=req)
        logging.debug("lineage_resp:" + str(lineage_resp))
        logging.debug("lineage_resp_body:" + str(lineage_resp.text))
        parsed_resp = lineage_resp.json()
        lineage_info = parsed_resp['lineage']
        stats_info = parsed_resp['stats']  # FIXME
        inputs = []
        lineage = []
        for lineage_entry in lineage_info:
            logging.debug('lineage_entry["table"] = {}, table_id_to_bqtable.keys={}'.format(lineage_entry['table'], list(table_id_to_bqtable.keys())))
            bq_table = table_id_to_bqtable.get(lineage_entry['table'])
            if bq_table is not None:
                ds, sc = BqCommonHelpers.table_to_kensu(bq_table)
                ds_path = ds.pk.location
                sc = [(f.name, f.field_type) for f in sc.pk.fields]
            else:
                sc = None
                ds_path = 'bigquery:/' + lineage_entry['table']  # FIXME: add proper BQ prefix, and extract a shared helper
            input = KensuDatasourceAndSchema.for_path_with_opt_schema(
                kensu,
                ds_path=ds_path,
                format='BigQuery table',
                categories=None,
                maybe_schema=sc,
                f_get_stats=lambda: (bq_table is not None) and compute_bigquery_stats(bq_table, client, stats_descriptions=stats_info) or None
            )
            lin_entry = ExtDependencyEntry(
                input_ds=input,
                lineage=lineage_entry['mapping']
            )
            inputs.append(input)
            lineage.append(lin_entry)
        lineage_info = GenericComputedInMemDs(inputs=inputs, lineage=lineage)
        logging.debug('final lineage' + str(lineage_info))
        return lineage_info
