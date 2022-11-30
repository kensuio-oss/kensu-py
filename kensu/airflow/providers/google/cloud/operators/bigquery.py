import google
from airflow.providers.google.cloud.operators.bigquery import *

from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook, BigQueryJob
from airflow.providers.google.cloud.operators import bigquery as gcp_bigquery

import logging

from google.cloud.bigquery import TableReference

from kensu.airflow.kensu_airflow_collector import COLLECTOR_STATUS_INIT, COLLECTOR_STATUS_DONE, log_status, \
    airflow_init_kensu, handle_ex
from kensu.google.cloud.bigquery import QueryJob
from typing import TYPE_CHECKING

from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs
from kensu.utils.helpers import extract_ksu_ds_schema
from kensu.utils.kensu_provider import KensuProvider

if TYPE_CHECKING:
    from airflow.utils.context import Context


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


BigQueryInsertJobOperator.__doc__ = gcp_bigquery.BigQueryInsertJobOperator.__doc__


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
                # bigquery_conn_id is deprecated sin 2.3.+
                if hasattr(self, "bigquery_conn_id"):
                    bq_hook = BigQueryHook(
                        bigquery_conn_id=self.bigquery_conn_id,
                        delegate_to=self.delegate_to,
                        location=self.location,
                        impersonation_chain=self.impersonation_chain,
                    )
                else:
                    bq_hook = BigQueryHook(
                        gcp_conn_id=self.gcp_conn_id,
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
                               for source_object in (self.source_objects or [])] or \
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
                if not QueryJob.report_ddl_write_with_stats(result=dst_bq_table,
                                                            ddl_target_table=dst_bq_table,
                                                            client=bq_client,
                                                            lineage=lineage,
                                                            is_ddl_write=True,
                                                            operation_type='BigQueryCreateExternalTableOperator'):
                    logging.info("inputs:" + str(ksu_inputs) + f"self.source_objects: {self.source_objects}")
            else:
                logging.warning("table_resource not used - not supported by Kensu")
        except Exception as ex:
            handle_ex(self, ex)
        log_status(self, COLLECTOR_STATUS_DONE)
        return res


BigQueryCreateExternalTableOperator.__doc__ = gcp_bigquery.BigQueryCreateExternalTableOperator.__doc__
