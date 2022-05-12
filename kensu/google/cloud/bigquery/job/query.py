#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging
import traceback

import google

from kensu.google.cloud.bigquery.extractor import KensuBigQuerySupport
from kensu.google.cloud.bigquery.job.bigquery_stats import compute_bigquery_stats
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
    def override_result(job  # type: google.cloud.bigquery.job.QueryJob
                        ) -> bqj.QueryJob:
        f = job.result

        def wrapper(*args, **kwargs):
            kensu = KensuProvider().instance()
            result = f(*args, **kwargs)
            client = kensu.data_collectors['BigQuery']
            QueryJob.report_bq_sql_query_job(client=client, job=job, result=result)
            return result

        wrapper.__doc__ = f.__doc__
        setattr(job, 'result', wrapper)
        return job


    @staticmethod
    def report_bq_sql_query_job(
            client: 'Client',
            job: 'QueryJob',
            result=None
    ):
        """track QueryJob without requiring to subclass the Job itself"""

        kensu = KensuProvider().instance()
        ddl_target_table = job.ddl_target_table
        dest = job.destination or ddl_target_table
        is_ddl_write = bool(ddl_target_table)
        logger.debug(f'in QueryJob.result(): dest={dest}')
        logger.debug(f'in QueryJob.result(): referenced={job.referenced_tables}')

        if isinstance(dest, bq.TableReference):
            dest = client.get_table(dest)

        if result is not None:
            QueryJob._store_bigquery_job_destination(result=result, dest=dest)
        else:
            if isinstance(dest, bq.Table):
                result = dest
            else:
                return


        # TODO What if several SELECT queries linked with ; ?
        db_metadata, table_id_to_bqtable, table_infos = BqOfflineParser.get_referenced_tables_metadata(
            kensu=kensu,
            client=client,
            job=job,
            query=BqOfflineParser.normalize_table_refs(job.query))
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
        QueryJob.report_ddl_write_with_stats(
            result=result,
            ddl_target_table=ddl_target_table,
            client=client,
            lineage=bq_lineage,
            is_ddl_write=is_ddl_write
        )


    @staticmethod
    def report_ddl_write_with_stats(
            result,
            ddl_target_table,
            client,
            lineage,
            is_ddl_write,
            operation_type=None
    ):
        kensu = KensuProvider().instance()
        if kensu.compute_stats and is_ddl_write and isinstance(ddl_target_table, bq.Table):
            # for DDL writes, stats can be computed by just reading the whole table
            # FIXME: for incremental `INSERT INTO` would not give the correct stats (we'd get full table)
            out_stats_values = compute_bigquery_stats(
                table_ref=ddl_target_table.reference,
                table=ddl_target_table,
                client=client,
                # stats for all output columns
                stats_aggs=None,
                input_filters=None)
            KensuBigQuerySupport().set_stats(result, out_stats_values)
        lineage.report(
            ksu=kensu,
            df_result=result,
            operation_type=operation_type,
            report_output=kensu.report_in_mem or is_ddl_write,
            register_output_orig_data=is_ddl_write   # used for DDL writes, like CREATE TABLE t2 AS SELECT * FROM t1
        )
        if is_ddl_write:
            if len(lineage.lineage) > 0:
                kensu.report_with_mapping()
                return True
            else:
                logger.warning("Kensu got empty lineage - not reporting")
                logger.info("lineage:" + str(lineage))
                logger.info("ddl_target_table:" + str(ddl_target_table))
                return False


    @staticmethod
    def _store_bigquery_job_destination(result, dest):
        try:
            if (dest is not None) and isinstance(dest, google.cloud.bigquery.table.Table):
                result.ksu_dest = dest
        except:
            logger.warning('setting _store_bigquery_job_destination failed')
            traceback.print_exc()
