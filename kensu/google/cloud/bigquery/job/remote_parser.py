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
        stats_info = parsed_resp['stats']
        lineage = list([BqRemoteParser.convert_lineage_entry(
                lineage_entry,
                kensu=kensu,
                client=client,
                table_id_to_bqtable=table_id_to_bqtable,
                stats_info=stats_info
            ) for lineage_entry in lineage_info])
        converted_lineage = GenericComputedInMemDs(lineage=lineage)
        logging.debug('converted_lineage:' + str(converted_lineage))
        return converted_lineage

    @staticmethod
    def convert_lineage_entry(lineage_entry, kensu, client: bq.Client, table_id_to_bqtable, stats_info):
        table_id = lineage_entry['table']
        logging.debug('table_id = {}, table_id_to_bqtable.keys={}'.format(table_id, str(table_id_to_bqtable)))
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
                stats_values = compute_bigquery_stats(
                    table_ref=bg_table_ref,
                    table=bq_table,
                    client=client,
                    stats_aggs=stats_aggs,
                    input_filters=stats_filters)
            logging.debug(
                f'table_id {table_id} (table.ref={bg_table_ref}, ds_path: {ds_path}) got input_filters: {stats_filters} & stat_aggs:{str(stats_aggs)}')
        else:
            logging.warning('table_id={} as reported by remote service was not found in table_id cache: {}'.format(
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