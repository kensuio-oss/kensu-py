import traceback

from airflow.models import BaseOperator
from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook, BigQueryJob
from airflow.providers.google.cloud.operators import bigquery as gcp_bigquery

import logging

from google.cloud.bigquery import TableReference

from kensu.google.cloud.bigquery import QueryJob
from kensu.utils.dsl.extractors.external_lineage_dtos import *
from kensu.google.cloud.bigquery.extractor import *
from typing import TYPE_CHECKING

from kensu.utils.helpers import extract_ksu_ds_schema

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


def full_gs_uri(bucket, obj_path):
    return f"gs://{bucket}/{obj_path}"


def handle_ex(obj, ex):
    logging.warning(f"Kensu collector failed for {type(obj)}", ex)
    if KENSU_ERRORS_FAIL_JOB:
        raise ex


def log_status(obj, status):
    logging.info(f"Kensu collector for {type(obj)} is {status}")


COLLECTOR_STATUS_INIT = "initializing..."
COLLECTOR_STATUS_DONE = "done."

