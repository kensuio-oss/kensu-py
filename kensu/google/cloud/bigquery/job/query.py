#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging
import traceback

import google

from kensu.google.cloud.bigquery.job.bigquery_parser import BqOfflineParser, BqRemoteParser, BqCommonHelpers
from kensu.pandas import DataFrame
from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema, GenericComputedInMemDs
from kensu.utils.helpers import extract_ksu_ds_schema
from kensu.utils.kensu_provider import KensuProvider
import google.cloud.bigquery as bq
import google.cloud.bigquery.job as bqj
from google.cloud.bigquery import Table
import sqlparse

class QueryJob(bqj.QueryJob):
    # .to_dataframe (and possibly other methods) calls .result

    @staticmethod
    def patch(job: bqj.QueryJob) -> bqj.QueryJob:
        return QueryJob.override_result(QueryJob.override_to_dataframe(job))


    @staticmethod
    def override_to_dataframe(job: bqj.QueryJob) -> bqj.QueryJob:
        f_orig_to_dataframe = job.to_dataframe

        def wrapper(*args, **kwargs):
            kensu = KensuProvider().instance()
            # pd_df_result = f_orig_to_dataframe(*args, **kwargs)
            # or get result() and later convert result to pandas...
            job_result = job.result()
            pd_df_result = job_result.to_dataframe(*args, **kwargs)
            ksu_pd_df_result = DataFrame.using(pd_df_result)

            out_ds, out_schema=extract_ksu_ds_schema(kensu, pd_df_result, report=kensu.report_in_mem, register_orig_data=False)
            in_ds, in_schema = extract_ksu_ds_schema(kensu, job_result, report=kensu.report_in_mem, register_orig_data=False)
            # FIXME: extract all-to-all helper...
            logging.debug("in_schema="+str(in_schema)+"\nout_schema="+str(out_schema))
            if kensu.mapping:
                for col in pd_df_result:
                    if col in [v.name for v in in_schema.pk.fields]:
                        kensu.add_dependencies_mapping(guid=out_schema.to_guid(),
                                                     col=str(col),
                                                     from_guid=in_schema.to_guid(),
                                                     from_col=str(col),
                                                     type='to_dataframe')
                # FIXME: what is this? call only on write?! kensu.report_with_mapping()
            return ksu_pd_df_result
        wrapper.__doc__ = f_orig_to_dataframe.__doc__
        setattr(job, 'to_dataframe', wrapper)
        return job


    @staticmethod
    def override_result(job: bqj.QueryJob) -> bqj.QueryJob:
        f = job.result
        def wrapper(*args, **kwargs):
            kensu = KensuProvider().instance()
            result = f(*args, **kwargs)
            client = kensu.data_collectors['BigQuery']
            # FIXME lots of copy paste from above function to_dataframe
            dest = job.destination
            if not dest:
                # FIXME
                logging.debug("Not implemented job without destination")
            else:
                # fixme: dest has no direct relation with final returned result
                if isinstance(dest, bq.TableReference):
                    dest = client.get_table(dest)
                db_metadata, table_id_to_schema_id, table_id_to_bqtable, table_infos = BqOfflineParser.get_referenced_tables_metadata(
                    kensu,
                    client,
                    job.query)
                bq_lineage = None
                try:
                    bq_lineage = BqRemoteParser.parse(
                        kensu=kensu,
                        client=client,
                        query=job.query,
                        db_metadata=db_metadata,
                        table_id_to_bqtable=table_id_to_bqtable)
                except:
                    logging.warning("Error in BigQuery collector, using fallback implementation")
                    traceback.print_exc()
                    # FIXME: do dest stats need any special handling?
                    bq_lineage = BqOfflineParser.fallback_lineage(kensu, table_infos, dest)

                try:
                    # FIXME: set it to each of the input tables too?!!! meh. what if mutable & reused among queries?
                    # FIXME: dest is lost here...?
                    if (dest is not None) and isinstance(dest, google.cloud.bigquery.table.Table):
                        result.ksu_dest = dest
                except:
                    logging.warning('setting result.bq_sql_query failed')
                    traceback.print_exc()
                # FIXME: call report only if dest is defined?
                if True:
                    bq_lineage.report(
                        ksu=kensu,
                        df_result=dest,
                        operation_type='BigQuery SQL result',
                        report_output=kensu.report_in_mem,  # FIXME: how to know when in mem or when bigquery://projects/psyched-freedom-306508/datasets/_b63f45da1cafbd073e5c2770447d963532ac43ec/tables/anonc79d9038a13ab2dbe40064636b0aceedc62b5d69
                        register_output_orig_data=False # FIXME? when do we need this? INSERT INTO?
                    )
                #FIXME? kensu.report_with_mapping()


            return result

        wrapper.__doc__ = f.__doc__
        setattr(job, 'result', wrapper)
        return job

