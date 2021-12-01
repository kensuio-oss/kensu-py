#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging
import traceback

from kensu.google.cloud.bigquery.job.bq_helpers import BqKensuHelpers
from kensu.google.cloud.bigquery.job.bigquery_stats import compute_bigquery_stats
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema, GenericComputedInMemDs, \
    ExtDependencyEntry
import google.cloud.bigquery as bq
from kensu.utils.kensu_provider import KensuProvider

logger = logging.getLogger(__name__)


class BqRemoteParser:

    @staticmethod
    def get_headers():
        k = KensuProvider().instance()
        try:
            if k.bigquery_headers:
                headers = k.bigquery_headers
        except:
            headers = None
        return headers

    @staticmethod
    def parse(kensu, client: bq.Client, query: str, db_metadata, table_id_to_bqtable) -> GenericComputedInMemDs:
        ## POST REQUEST to /lineage-and-stats-criterions
        query = query.replace("PARSE_DATETIME", "to_timestamp")
        req = {"sql": query, "metadata": db_metadata}
        url = kensu.sql_util_url
        logger.debug("sending request to SQL parsing service url={} request={}".format(url, str(req)))
        import requests
        def convert(fieldtype):
            if fieldtype in ["INT64", "INT", "SMALLINT", "INTEGER", "BIGINT", "TINYINT", "BYTEINT", "BIGNUMERIC","NUMERIC"]:
                return "INTEGER"
            else:
                return fieldtype
        for table in db_metadata['tables']:
            for field in table['schema']['fields'] :
                field['type'] = convert(field['type'])

        #TODO Support UNNEST in queries  'SELECT e.key FROM `psyched-freedom-306508.my_dataset.sample`, UNNEST(user_properties) as e '
        lineage_resp = requests.post(url + "/lineage-and-stats-criterions", json=req, headers = BqRemoteParser.get_headers())
        logger.debug("lineage_resp:" + str(lineage_resp))
        logger.debug("lineage_resp_body:" + str(lineage_resp.text))
        parsed_resp = lineage_resp.json()
        lineage_info = parsed_resp['lineage']
        stats_info = parsed_resp['stats']
        lineage = list([BqRemoteParser.convert_lineage_entry(
                lineage_entry,
                kensu=kensu,
                client=client,
                table_id_to_bqtable=table_id_to_bqtable,
                stats_info=stats_info
            ) for lineage_entry in lineage_info])
        converted_lineage = GenericComputedInMemDs(lineage=lineage)
        logger.debug('converted_lineage:' + str(converted_lineage))
        return converted_lineage

    @staticmethod
    def convert_lineage_entry(lineage_entry, kensu, client: bq.Client, table_id_to_bqtable, stats_info):
        table_id = lineage_entry['table']
        logger.debug('table_id = {}, table_id_to_bqtable.keys={}'.format(table_id, str(table_id_to_bqtable)))
        bq_table = table_id_to_bqtable.get(table_id)
        stats_values = {}
        ds_name = None
        if bq_table is not None:
            ds, sc = BqKensuHelpers.table_to_kensu(bq_table)
            ds_path = ds.pk.location
            ds_name = ds.name
            sc = [(f.name, f.field_type) for f in sc.pk.fields]
            table_stats_info = stats_info.get(table_id, {})
            stats_aggs = table_stats_info.get('stats')
            stats_filters = table_stats_info.get('input_filters')
            bg_table_ref = bq_table.reference
            # note: making stats computation lazy in a f_get_stats lambda seem to behave very weirdly...
            # so stats are computed eagerly now
            if kensu.compute_stats:
                try:
                    stats_values = compute_bigquery_stats(
                        table_ref=bg_table_ref,
                        table=bq_table,
                        client=client,
                        stats_aggs=stats_aggs,
                        input_filters=stats_filters)
                except Exception as e:
                    stats_values = None
                    logger.debug(f"Unable to compute the stats: {e}")

            logger.debug(
                f'table_id {table_id} (table.ref={bg_table_ref}, ds_path: {ds_path}) got input_filters: {stats_filters} & stat_aggs:{str(stats_aggs)}')
        else:
            logger.warning('table_id={} as reported by remote service was not found in table_id cache: {}'.format(
                table_id, str(table_id_to_bqtable.keys())))
            sc = None
            ds_path = 'bigquery:/' + table_id  # FIXME: add proper BQ prefix, and extract a shared helper
        input = KensuDatasourceAndSchema.for_path_with_opt_schema(
            kensu,
            ds_path=ds_path,
            ds_name=ds_name,
            format='BigQuery table',
            categories=None,
            maybe_schema=sc,
            f_get_stats=lambda: stats_values
        )
        return ExtDependencyEntry(
            input_ds=input,
            lineage=lineage_entry['mapping']
        )