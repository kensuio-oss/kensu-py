#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging
import traceback

import google

from kensu.google.cloud.bigquery.job.offline_parser import BqOfflineParser
from kensu.google.cloud.bigquery.job.remote_parser import BqRemoteParser
from kensu.pandas import DataFrame
from kensu.utils.helpers import report_all2all_lineage
from kensu.utils.kensu_provider import KensuProvider
import google.cloud.bigquery as bq
import google.cloud.bigquery.job as bqj

logger = logging.getLogger(__name__)


class QueryJob(bqj.QueryJob):
    # - client.query(sql) returns QueryJob which we patch here for tracking
    # - for both QueryJob.to_dataframe and QueryJob.result() we return a monkey-patched QueryJob
    #      having QueryJob.result set to our wrapper fn
    #  * we add a .ksu_dest field to QueryJob.result() which is internally used to connect lineage later on
    # - QueryJob.to_dataframe calls original .result() internally, so to be able to track it, currently
    # we do not call the original .to_dataframe(), but obtain .result() and then convert it to DataFrame
    # Limitations:
    # - currently bq.TableReference (temp table) is tested as destination of job (could be RowIterator too)

    @staticmethod
    def patch(job: bqj.QueryJob) -> bqj.QueryJob:
        return QueryJob.override_result(QueryJob.override_to_dataframe(job))

    @staticmethod
    def override_to_dataframe(job: bqj.QueryJob) -> bqj.QueryJob:
        f_orig_to_dataframe = job.to_dataframe

        def wrapper(*args, **kwargs):
            # instead of calling .to_dataframe(),  to be able to track lineage
            # we get raw .result() and later convert result to pandas
            # (otherwise original input info is lost inside to_dataframe fn)
            job_result = job.result()
            to_dataframe_res = job_result.to_dataframe(*args, **kwargs)
            final_result = DataFrame.using(to_dataframe_res)
            report_all2all_lineage(in_obj=job_result, out_obj=to_dataframe_res, in_inmem=True, out_inmem=True,
                                   op_type='to_dataframe')
            return final_result

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
            dest = job.destination
            if isinstance(dest, bq.TableReference):
                dest = client.get_table(dest)

            #TODO What if several SELECT queries linked with ; ?
            db_metadata, table_id_to_bqtable, table_infos = BqOfflineParser.get_referenced_tables_metadata(
                kensu=kensu,
                client=client,
                query=job.query)
            try:
                bq_lineage = BqRemoteParser.parse(
                    kensu=kensu,
                    client=client,
                    query=job.query,
                    db_metadata=db_metadata,
                    table_id_to_bqtable=table_id_to_bqtable)
            except:
                logger.warning("Error in BigQuery collector, using fallback implementation")
                traceback.print_exc()
                bq_lineage = BqOfflineParser.fallback_lineage(kensu, table_infos, dest)

            QueryJob._store_bigquery_job_destination(result=result, dest=dest)

            bq_lineage.report(
                ksu=kensu,
                df_result=result,
                operation_type='BigQuery SQL result',
                report_output=kensu.report_in_mem,
                # FIXME: how to know when in mem or when bigquery://projects/psyched-freedom-306508/datasets/_b63f45da1cafbd073e5c2770447d963532ac43ec/tables/anonc79d9038a13ab2dbe40064636b0aceedc62b5d69
                register_output_orig_data=False  # FIXME? when do we need this? INSERT INTO?
            )
            # FIXME? kensu.report_with_mapping()

            return result

        wrapper.__doc__ = f.__doc__
        setattr(job, 'result', wrapper)
        return job

    @staticmethod
    def _store_bigquery_job_destination(result, dest):
        try:
            if (dest is not None) and isinstance(dest, google.cloud.bigquery.table.Table):
                result.ksu_dest = dest
        except:
            logger.warning('setting _store_bigquery_job_destination failed')
            traceback.print_exc()
