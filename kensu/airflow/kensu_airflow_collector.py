import traceback
from typing import Optional, Dict

from airflow.models import BaseOperator
from airflow.operators import bash as airflow_bash
from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook, BigQueryJob
from airflow.providers.google.cloud.hooks.gcs import GCSHook
from airflow.providers.google.cloud.operators import bigquery as gcp_bigquery
from airflow.providers.google.cloud.transfers import gcs_to_gcs as airflow_gcs_to_gcs
import airflow.operators.python

import logging

from google.cloud.bigquery import TableReference, LoadJob
import google.cloud.bigquery as bq
import google.cloud.bigquery.job as bqj

from kensu.google.cloud.bigquery import QueryJob
from kensu.google.cloud.bigquery.job.offline_parser import BqOfflineParser
from kensu.google.cloud.bigquery.job.remote_parser import BqRemoteParser
from kensu.utils.helpers import *
from kensu.utils.dsl.extractors.generic_datasource_info_support import *
from kensu.utils.dsl.extractors.external_lineage_dtos import *
from kensu.google.cloud.bigquery.extractor import *
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airflow.utils.context import Context

KENSU_ERRORS_FAIL_JOB = True


def airflow_init_kensu(
        airflow_operator=None,  # type: BaseOperator
        project_names=None,
        process_name=None,
        api_url=None,
        auth_token=None,
):
    if airflow_operator is not None:
        if project_names is None:
            project_names = ['Airflow :: ' + airflow_operator.dag_id]
        if process_name is None:
            process_name = airflow_operator.task_id
    # This must be called at each dag Operation, as Airflow operations may run on different Hosts
    if project_names is None:
        project_names = []

    # it seems GCP Composer's env variables are actually not passed (at least to some of the Airflow Operators)
    # so we set the important/sensitive settings explicitly from Airflow (secured) variables
    from airflow.models import Variable
    api_url = Variable.get("KENSU_API_URL", default_var=None)
    auth_token = Variable.get("KSU_API_TOKEN", default_var=None)

    KensuProvider().initKensu(
        api_url=api_url,
        auth_token=auth_token,
        init_context=True,
        project_names=project_names,
        process_name=process_name,
        mapping=True,
        report_in_mem=False,
        bigquery_support=True)



def report_bq_write_with_stats(
        dst_bq_table,
        bq_client,
        lineage
):
    ksu = KensuProvider().instance()
    if ksu.compute_stats:
        # for DDL writes, stats can be computed by just reading the whole table
        # FIXME: for incremental `INSERT INTO` would not give the correct stats (we'd get full table)
        out_stats_values = compute_bigquery_stats(
            table_ref=dst_bq_table.reference,
            table=dst_bq_table,
            client=bq_client,
            # stats for all output columns
            stats_aggs=None,
            input_filters=None)
        KensuBigQuerySupport().set_stats(dst_bq_table, out_stats_values)
    lineage.report(
        ksu,
        df_result=dst_bq_table,
        report_output=True,
        register_output_orig_data=True,
        operation_type='BigQueryCreateExternalTableOperator',
    )
    if len(lineage.lineage) > 0:
        ksu.report_with_mapping()
        return True
    else:
        logging.warning("Kensu got empty lineage - not reporting")
        logging.info("bq_lineage:" + str(lineage))
        logging.info("dst_bq_table:" + str(dst_bq_table))
        return False


# def report_bq_sql_query_job(
#         client: 'Client',
#         job: 'QueryJob',
#         result=None,
#         dest=None
# ):
#     """track QueryJob without requiring to subclass the Job itself"""
#
#     ksu = KensuProvider().instance()
#     ddl_target_table = job.ddl_target_table
#     dest = job.destination or ddl_target_table
#     is_ddl_write = bool(ddl_target_table)
#     logging.info(f'in QueryJob.result(): dest={dest}')
#     logging.info(f'in QueryJob.result(): referenced={job.referenced_tables}')
#
#     if isinstance(dest, bq.TableReference):
#         dest = client.get_table(dest)
#     else:
#         return
#     if result is None:
#         if isinstance(dest, bq.Table):
#             result = dest
#         else:
#             return
#
#     # TODO What if several SELECT queries linked with ; ?
#     db_metadata, table_id_to_bqtable, table_infos = BqOfflineParser.get_referenced_tables_metadata(
#         kensu=ksu,
#         client=client,
#         job=job,
#         query=BqOfflineParser.normalize_table_refs(job.query))
#     try:
#         bq_lineage = BqRemoteParser.parse(
#             kensu=ksu,
#             client=client,
#             query=job.query,
#             db_metadata=db_metadata,
#             table_id_to_bqtable=table_id_to_bqtable)
#     except:
#         logging.warning("Error in BigQuery collector, using fallback implementation")
#         traceback.print_exc()
#         bq_lineage = BqOfflineParser.fallback_lineage(ksu, table_infos, dest)
#
#     # FIXME: rm - QueryJob._store_bigquery_job_destination(result=result, dest=dest)
#
#     if is_ddl_write and isinstance(ddl_target_table, bq.TableReference) and ksu.compute_stats:
#         # for DDL writes, stats can be computed by just reading the whole table
#         # FIXME: for incremental `INSERT INTO` would not give the correct stats (we'd get full table)
#         out_stats_values = compute_bigquery_stats(
#             table_ref=ddl_target_table,
#             table=client.get_table(ddl_target_table),
#             client=client,
#             # stats for all output columns
#             stats_aggs=None,
#             input_filters=None)
#         KensuBigQuerySupport().set_stats(result, out_stats_values)
#     bq_lineage.report(
#         ksu=ksu,
#         df_result=result,
#         operation_type='BigQuery SQL result',
#         report_output=ksu.report_in_mem or is_ddl_write,
#         register_output_orig_data=is_ddl_write  # used for DDL writes, like CREATE TABLE t2 AS SELECT * FROM t1
#         # FIXME: how about INSERT INTO?
#     )
#     if is_ddl_write:
#         # FIXME: report_with_mapping fails with empty inputs/lineage?
#         if len(bq_lineage.lineage) > 0:
#             ksu.report_with_mapping()


def full_gs_uri(bucket, obj_path):
    return f"gs://{bucket}/{obj_path}"


def report_simple_copy_with_guessed_schema(input_uri,  # type: str
                                           output_filename,  # type: str
                                           sep
                                           ):
    try:
        maybe_schema = None
        output_absolute_uri = get_absolute_path(output_filename)
        logging.info(f"report_simple_copy_with_guessed_schema input={input_uri} output={output_absolute_uri}")
        if output_absolute_uri.endswith('.csv'):
            try:
                # FIXME: part of duplicated code here
                import kensu.pandas as pd
                maybe_pandas_df = pd.read_csv(output_filename)  # FIXME: sep=";"
                from kensu.utils.kensu_provider import KensuProvider
                ksu = KensuProvider().instance()
                _, schema = extract_ksu_ds_schema(ksu, maybe_pandas_df, report=False, register_orig_data=False)
                maybe_schema = [(f.name, f.field_type) for f in schema.pk.fields]
            except Exception as ex:
                logging.warning("unable to guess schema of .csv() file", ex)
        GenericComputedInMemDs.report_copy_with_opt_schema(
            src=input_uri,
            dest=output_absolute_uri,
            operation_type='airflow.BashOperator::curl',
            maybe_schema=maybe_schema
        )
    except Exception as e:
        logging.warning(f"caught exception in dumb_parse_curl", e)


def handle_ex(obj, ex):
    logging.warning(f"Kensu collector failed for {type(obj)}", ex)
    if KENSU_ERRORS_FAIL_JOB:
        raise ex


def log_status(obj, status):
    logging.info(f"Kensu collector for {type(obj)} is {status}")


COLLECTOR_STATUS_INIT = "initializing..."
COLLECTOR_STATUS_DONE = "done."


class BigQueryInsertJobOperator(gcp_bigquery.BigQueryInsertJobOperator):
    def __init__(
            self,
            *args,
            **kwargs,
    ):
        super(BigQueryInsertJobOperator, self).__init__(
            *args, **kwargs
        )
        self.ksu_bq_job = None

    def _submit_job(
            self,
            hook: BigQueryHook,
            job_id: str,
    ) -> BigQueryJob:
        # just store bigquery job to be accessed later
        bq_job = super(BigQueryInsertJobOperator, self)._submit_job(hook, job_id)
        self.ksu_bq_job = bq_job
        return bq_job

    def execute(self, context: 'Context') -> None:
        job_id = super(BigQueryInsertJobOperator, self).execute(context)
        try:
            log_status(self, COLLECTOR_STATUS_INIT)
            airflow_init_kensu(airflow_operator=self)
            # it seems hook.get_job() shall be called only when a running non-finished job already existed (a conflict)
            bq_job = self.ksu_bq_job or self.hook.get_job(
                project_id=self.project_id,
                location=self.location,
                job_id=job_id,
            )
            bq_client = self.hook.get_client(project_id=self.project_id)
            logging.info(f"bq_job: {bq_job} type={str(type(bq_job))}")
            # Union[CopyJob, QueryJob, LoadJob, ExtractJob]
            if isinstance(bq_job, google.cloud.bigquery.job.QueryJob):
                QueryJob.report_bq_sql_query_job(
                    client=bq_client,
                    job=bq_job
                )
        except Exception as ex:
            handle_ex(self, ex)
        log_status(self, COLLECTOR_STATUS_DONE)
        return job_id


class BigQueryCreateExternalTableOperator(gcp_bigquery.BigQueryCreateExternalTableOperator):

    def __init__(
            self,
            *args,
            **kwargs,
    ):
        super(BigQueryCreateExternalTableOperator, self).__init__(
            *args, **kwargs
        )

    def execute(self, context: 'Context') -> None:
        res = super(BigQueryCreateExternalTableOperator, self).execute(context)
        try:
            log_status(self, COLLECTOR_STATUS_INIT)
            # logging.info("Airflow context keys: " + str(context.keys()))
            # logging.info("Airflow context: " + str(context.items()))
            airflow_init_kensu(airflow_operator=self)
            ksu = KensuProvider().instance()
            if self.table_resource:
                bq_hook = BigQueryHook(
                    gcp_conn_id=self.bigquery_conn_id,
                    delegate_to=self.delegate_to,
                    location=self.location,
                    impersonation_chain=self.impersonation_chain,
                )
                #  e.g. table_resource: {
                #             "externalDataConfiguration": {
                #                 "sourceFormat": "PARQUET",
                #                 "sourceUris": [f"gs://{BUCKET}/raw/{parquet_file}"],
                #             },
                # }
                ext_input_conf = self.table_resource.get('externalDataConfiguration', {})
                source_uris = [f"gs://{self.bucket}/{source_object}"
                               for source_object in self.source_objects] or \
                              ext_input_conf.get('sourceUris')
                source_format = ext_input_conf.get('sourceFormat') or 'CSV'

                bq_table_ref_dict = self.table_resource['tableReference']
                bq_client = bq_hook.get_client(project_id=bq_table_ref_dict['projectId'])

                bq_table_ref = TableReference.from_api_repr(bq_table_ref_dict)
                dst_bq_table = bq_client.get_table(bq_table_ref)

                _, result_schema = extract_ksu_ds_schema(ksu, dst_bq_table)
                ksu_inputs, lineage = GenericComputedInMemDs.build_approx_lineage(
                    source_uris=source_uris,
                    source_format=source_format,
                    result_schema=result_schema
                )
                if not report_bq_write_with_stats(dst_bq_table=dst_bq_table, bq_client=bq_client, lineage=lineage):
                    logging.info("inputs:" + str(ksu_inputs) + f"self.source_objects: {self.source_objects}")
            else:
                logging.warning("table_resource not used - not supported by Kensu")
        except Exception as ex:
            handle_ex(self, ex)
        log_status(self, COLLECTOR_STATUS_DONE)
        return res
