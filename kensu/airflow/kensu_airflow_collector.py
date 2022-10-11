from airflow.models import BaseOperator

import logging

from typing import TYPE_CHECKING

from kensu.utils.kensu_provider import KensuProvider

if TYPE_CHECKING:
    from airflow.utils.context import Context

KENSU_ERRORS_FAIL_JOB = True
COLLECTOR_STATUS_INIT = "initializing..."
COLLECTOR_STATUS_DONE = "done."


def airflow_init_kensu(
        airflow_operator=None,  # type: BaseOperator
        project_name=None,
        process_name=None,
):
    if airflow_operator is not None:
        if project_name is None:
            from airflow.models import Variable
            project_name = Variable.get("KSU_PROJECT_NAME", default_var='Airflow :: ' + airflow_operator.dag_id)
        if process_name is None:
            process_name = airflow_operator.task_id

    # it seems GCP Composer's env variables are actually not passed (at least to some of the Airflow Operators)
    # so we set the important/sensitive settings explicitly from Airflow (secured) variables
    from airflow.models import Variable
    api_url = Variable.get("KSU_KENSU_INGESTION_URL", default_var=None)
    auth_token = Variable.get("KSU_KENSU_INGESTION_TOKEN", default_var=None)

    KensuProvider().initKensu(
        kensu_ingestion_url=api_url,
        kensu_ingestion_token=auth_token,
        init_context=True,
        project_name=project_name,
        process_name=process_name,
        bigquery_support=True)


def full_gs_uri(bucket, obj_path):
    return f"gs://{bucket}/{obj_path}"


def handle_ex(obj, ex):
    logging.warning(f"Kensu collector failed for {type(obj)}", ex)
    if KENSU_ERRORS_FAIL_JOB:
        raise ex


def log_status(obj, status):
    logging.info(f"Kensu collector for {type(obj)} is {status}")
