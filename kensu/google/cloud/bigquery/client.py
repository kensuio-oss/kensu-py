import sqlparse
from google.cloud.bigquery import client, Dataset
import logging

from kensu.client import DataSourcePK, Schema, SchemaPK
from kensu.utils.helpers import to_datasource

logger = logging.getLogger(__name__)

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

        queries = query

        #For succession of SELECT queries, only the last one return a result
        for query in queries.split(";"):
            if query.lower().replace(" ","").replace("\n","").startswith("insertinto") \
                    or query.lower().replace(" ","").replace("\n","").startswith("merge") :
                kensu = KensuProvider().instance()
                client = kensu.data_collectors['BigQuery']
                q = sqlparse.parse(query)
                d = BqOfflineParser.find_sql_identifiers(q[0].tokens).__next__()
                table = d.value.replace('`','')
                ds_data = table.split('.')
                query = query.replace("\n","")
                if project is not None and len(ds_data) == 2:
                    ds_data = [project] + ds_data
                if len(ds_data) == 3:
                    ds_data_corr = ds_data
                    ds_data = []
                    for element in ds_data_corr:
                        ds_data.append(element.split(' ')[0])
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
                        if query.lower().replace(" ","").replace("\n","").startswith("insertinto") :
                            index_select = query.lower().index("select")
                            query_without_insert = query[index_select:]
                            logger.debug(f"Query without INSERT TO:{query_without_insert}")
                        elif query.lower().replace(" ","").replace("\n","").startswith("merge"):
                            import re
                            query_without_insert = re.findall('\(.*\)', query)[0]
                            db_metadata, table_id_to_bqtable, table_infos = BqOfflineParser.get_referenced_tables_metadata(
                                kensu=kensu,
                                client=client,
                                query=query_without_insert)

                        else:
                            query_without_insert = query
                    except:
                        logger.debug(f"{query}")
                        query_without_insert = query

                    try:
                        #TODO: Use sqlparse
                        bq_lineage = BqRemoteParser.parse(
                            kensu=kensu,
                            client=client,
                            query=query_without_insert,
                            db_metadata=db_metadata,
                            table_id_to_bqtable=table_id_to_bqtable)
                    except:
                        bq_lineage = BqOfflineParser.fallback_lineage(kensu, table_infos, dest)

                    db_metadata_out, table_id_to_bqtable_out, table_infos_out = BqOfflineParser.get_referenced_tables_metadata(
                        kensu=kensu,
                        client=client,
                        table=dest)

                    table_infos_out[0][1]._report()
                    bq_lineage.report(
                        ksu=kensu,
                        df_result=table_infos_out[0][2],
                        operation_type='BigQuery SQL result',
                        report_output=True,
                        # FIXME: how to know when in mem or when bigquery://projects/psyched-freedom-306508/datasets/_b63f45da1cafbd073e5c2770447d963532ac43ec/tables/anonc79d9038a13ab2dbe40064636b0aceedc62b5d69
                        register_output_orig_data=True  # FIXME? when do we need this? INSERT INTO?
                    )

                    from kensu.google.cloud.bigquery.job.bigquery_stats import compute_bigquery_stats
                    try:
                        output_stats = compute_bigquery_stats(table_ref=destination, table = client.get_table(destination), client = client,query = query_without_insert)
                    except:
                        logger.debug(f"Unable to compute stats for table {str(table)}")
                        output_stats=None
                    kensu.real_schema_df[table_infos_out[0][2].to_guid()] = output_stats

                    kensu.report_with_mapping()

        return QueryJob.patch(j)


    def load_table_from_uri(
        self,
        source_uris,
        destination,
        job_id = None,
        job_id_prefix = None,
        location = None,
        project = None,
        job_config = None,
        retry = DEFAULT_RETRY,
        timeout = None
    ):
        gclient = super(Client, self)
        j = gclient.load_table_from_uri(source_uris,
        destination,
        job_id,
        job_id_prefix,
        location,
        project,
        job_config,
        retry,
        timeout)

        block = j.result()

        kensu = KensuProvider().instance()
        kensu.data_collectors['BigQuery'] = gclient

        dest_metadata, table_id_to_bqtable, table_infos = BqOfflineParser.get_referenced_tables_metadata(
            kensu=kensu,
            client=gclient,
            table=destination)
        ds = table_infos[0][1]._report()
        sc = table_infos[0][2]._report()
        sc_guid = sc.to_guid()
        kensu.real_schema_df[sc_guid] = None
        in_schema = sc


        if isinstance(source_uris, list):
            input_ds = source_uris
        else:
            input_ds = [source_uris]

        list_schemas = []
        for ds_uri_location in input_ds:
            #TODO Extractor?
            logical_naming = kensu.logical_naming
            location = ds_uri_location
            ds_pk = DataSourcePK(location=location, physical_location_ref=kensu.default_physical_location_ref)
            format = ds_uri_location.split(".")[-1] if "." in ds_uri_location else "Unknown"
            name = ('/').join(location.split('/')[-2:])
            ds_in = to_datasource(ds_pk, format, location, logical_naming, name)._report()
            ds_in_guid = ds_in.to_guid()
            in_schema.pk.data_source_ref.by_guid = ds_in_guid
            schema_in = Schema(name = "Schema:"+name, pk=in_schema.pk)._report()
            list_schemas.append(schema_in)
            #TODO replace none
            kensu.real_schema_df[schema_in.to_guid()] = None
            for col in [field.name for field in sc.pk.fields]:
                kensu.add_dependencies_mapping(sc_guid,col,schema_in.to_guid(),col,"load")

        kensu.report_with_mapping()

        return j
