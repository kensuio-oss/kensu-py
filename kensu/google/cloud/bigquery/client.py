
from google.cloud.bigquery import client
from .job.query import QueryJob
from google.cloud.bigquery.retry import DEFAULT_RETRY
from kensu.utils.kensu_provider import KensuProvider

class Client(client.Client):


    def query(
        self,
        query,
        job_config=None,
        job_id=None,
        job_id_prefix=None,
        location=None,
        project=None,
        retry=DEFAULT_RETRY,
        timeout=None
    ):
        gclient = super(Client, self)
        j = gclient.query(query,
        job_config,
        job_id,
        job_id_prefix,
        location,
        project,
        retry,
        timeout)
        kensu = KensuProvider().instance()
        kensu.data_collectors['BigQuery'] = gclient

        return QueryJob.patch(j)