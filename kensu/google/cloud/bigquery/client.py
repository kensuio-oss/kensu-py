import sqlparse
from google.cloud.bigquery import client, Dataset

from .job.offline_parser import BqOfflineParser
from .job.query import QueryJob
from google.cloud.bigquery.retry import DEFAULT_RETRY
from kensu.utils.kensu_provider import KensuProvider
from .job.remote_parser import BqRemoteParser
import google.cloud.bigquery as bq


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

        if query.lower().replace(" ","").startswith("insertinto"):
            kensu = KensuProvider().instance()
            client = kensu.data_collectors['BigQuery']
            q = sqlparse.parse(query)
            d = BqOfflineParser.find_sql_identifiers(q[0].tokens).__next__()
            table = d.value.replace('`','')
            ds_data = table.split('.')
            if len(ds_data) == 3:
                ds = ".".join(ds_data[0:2])
                destination = client.create_dataset(Dataset(ds), timeout=30, exists_ok=True).table(
                    ds_data[2])
                if isinstance(destination, bq.TableReference):
                    dest = client.get_table(destination)
                db_metadata, table_id_to_bqtable, table_infos = BqOfflineParser.get_referenced_tables_metadata(
                    kensu=kensu,
                    client=client,
                    query=query)
                try:
                    query_without_insert = query.split(d.value)
                    query_without_insert.remove(query_without_insert[0])
                    query_without_insert= "".join(query_without_insert)

                    bq_lineage = BqRemoteParser.parse(
                        kensu=kensu,
                        client=client,
                        query=query_without_insert,
                        db_metadata=db_metadata,
                        table_id_to_bqtable=table_id_to_bqtable)
                except:
                    bq_lineage = BqOfflineParser.fallback_lineage(kensu, table_infos, dest)

                table_infos[0][1]._report()
                bq_lineage.report(
                    ksu=kensu,
                    df_result=table_infos[0][2],
                    operation_type='BigQuery SQL result',
                    report_output=True,
                    # FIXME: how to know when in mem or when bigquery://projects/psyched-freedom-306508/datasets/_b63f45da1cafbd073e5c2770447d963532ac43ec/tables/anonc79d9038a13ab2dbe40064636b0aceedc62b5d69
                    register_output_orig_data=True  # FIXME? when do we need this? INSERT INTO?
                )
                kensu.report_with_mapping()

        return QueryJob.patch(j)