#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright 2021 Kensu Inc
#
import logging

from kensu.pandas import DataFrame
from kensu.utils.kensu_provider import KensuProvider
import google.cloud.bigquery as bq
import google.cloud.bigquery.job as bqj
from google.cloud.bigquery import Table
import sqlparse

class QueryJob(bqj.QueryJob):

    @staticmethod
    def patch(job: bqj.QueryJob) -> bqj.QueryJob:
        return QueryJob.override_result(QueryJob.override_to_dataframe(job))


    @staticmethod
    def override_to_dataframe(job: bqj.QueryJob) -> bqj.QueryJob:
        f = job.to_dataframe

        def wrapper(*args, **kwargs):
            kensu = KensuProvider().instance()
            result = f(*args, **kwargs)
            df = DataFrame.using(result)

            read_ds = kensu.extractors.extract_data_source(result, kensu.default_physical_location_ref,
                                                         logical_naming=kensu.logical_naming)._report()
            read_sc = kensu.extractors.extract_schema(read_ds, df)._report()

            query = job.query
            sq = sqlparse.parse(query)
            ids = list(filter(lambda x: isinstance(x, sqlparse.sql.Identifier), sq[0].tokens))
            client = kensu.data_collectors['BigQuery']
            for id in ids:
                name = (id.get_real_name()).strip('`')
                table = client.get_table(name)
                path = table.path
                location = "bigquery:/" + path
                fmt = "BigQuery Table"
                ds = kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref, location=location,
                                                        format=fmt, logical_naming=kensu.logical_naming)._report()
                sc = kensu.extractors.extract_schema(ds, table)._report()

                if kensu.mapping:
                    for col in result:
                        if col in [v.name for v in sc.pk.fields]:
                            dep = {'GUID': read_sc.to_guid(),
                                   'COLUMNS': col,
                                   'FROM_ID': sc.to_guid(),
                                   'FROM_COLUMNS': col,
                                   'TYPE': 'read'}
                            kensu.dependencies_mapping.append(dep)

                kensu.real_schema_df[sc.to_guid()] = result[[v.name for v in sc.pk.fields]]

            return df
        wrapper.__doc__ = f.__doc__
        setattr(job, 'to_dataframe', wrapper)
        return job

    @staticmethod
    def find_sql_identifiers(tokens):
        for t in tokens:
            if isinstance(t, sqlparse.sql.Identifier):
                if t.is_group and len(t.tokens) > 0:
                    # String values like "World" in `N == "World"` are also Identifier
                    # but their first child is of ttype `Token.Literal.String.Symbol`
                    # although table seems to have a first child of ttype `Token.Name`
                    if str(t.tokens[0].ttype) == "Token.Name":
                        # FIXME .. this is also returning the column names... (REF_GET_TABLE)
                        yield t
            elif t.is_group:
                yield from QueryJob.find_sql_identifiers(t)


    @staticmethod
    def table_to_kensu(table: Table):
        kensu = KensuProvider().instance()
        ds = kensu.extractors.extract_data_source(table, kensu.default_physical_location_ref,
                                                logical_naming=kensu.logical_naming)._report()
        sc = kensu.extractors.extract_schema(ds, table)._report()
        return ds, sc


    @staticmethod
    def get_table_info_for_id(client: bq.Client, id: sqlparse.sql.Identifier):
        try:
            name = (id.get_real_name()).strip('`')
            table = client.get_table(name)
            ds, sc = QueryJob.table_to_kensu(table)
            return table, ds, sc
        except:
            # FIXME this is because the current find_sql_identifiers also returns the column names...
            #  (see aboveREF_GET_TABLE)
            #  Therefore get_table of a column name should fail
            return None


    @staticmethod
    def get_table_infos_from_sql(client: bq.Client, query: str):
        sq = sqlparse.parse(query)
        ids = QueryJob.find_sql_identifiers(sq[0].tokens) # FIXME we only take the first element
        table_infos = list(filter(lambda x: x is not None, [QueryJob.get_table_info_for_id(client, id) for id in ids]))
        return table_infos


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
                logging.debug("Not implemented job without destination")
            else:
                if isinstance(dest, bq.TableReference):
                    dest = client.get_table(dest)
                destination_ds, destination_sc = QueryJob.table_to_kensu(dest)
                kensu.real_schema_df[destination_sc.to_guid()] = dest
                dest_field_names = [f.name for f in destination_sc.pk.fields]
                table_infos = QueryJob.get_table_infos_from_sql(client, job.query)
                for table, ds, sc in table_infos:
                    kensu.real_schema_df[sc.to_guid()] = table
                try:
                    import requests
                    url = kensu.conf.get("sql.util.url")

                    table_id_to_schema_id = {}
                    metadata = {"tables": []}
                    for table, ds, sc in table_infos:
                        table_id = "`"+table.full_table_id.replace(":",".")+"`"
                        table_md = {
                            "id": table_id,
                            "schema": {
                                "fields": [ { "name": f.name, "type": f.field_type } for f in sc.pk.fields]
                            }
                        }
                        table_id_to_schema_id[table_id] = sc.to_guid()
                        metadata["tables"].append(table_md)
                    ## POST REQUEST to /lineage
                    lineage_info = requests.post(url + "/lineage", json={"sql": job.query, "metadata": metadata}).json()
                    for l in lineage_info:
                        t = l["table"]
                        mapping = l["mapping"]
                        for o in mapping:
                            for i in mapping[o]:
                                dep = {'GUID': destination_sc.to_guid(),
                                                'COLUMNS': o,
                                                'FROM_ID': table_id_to_schema_id[t],
                                                'FROM_COLUMNS': i,
                                                'TYPE': 'read'}
                                kensu.dependencies_mapping.append(dep)
                except:
                    for table, ds, sc in table_infos:
                        if kensu.mapping:
                            sc_field_names = [v.name for v in sc.pk.fields]
                            for col in dest_field_names:
                                if col in sc_field_names:
                                    dep = {'GUID': destination_sc.to_guid(),
                                        'COLUMNS': col,
                                        'FROM_ID': sc.to_guid(),
                                        'FROM_COLUMNS': col,
                                        'TYPE': 'read'}
                                    kensu.dependencies_mapping.append(dep)
                kensu.report_with_mapping()

            return result #TODO lineage and stuff if lost from here on

        wrapper.__doc__ = f.__doc__
        setattr(job, 'result', wrapper)
        return job

