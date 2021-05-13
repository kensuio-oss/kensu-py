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
                name = (id.get_name()).strip('`')
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
                destination_ds = kensu.extractors.extract_data_source(dest, kensu.default_physical_location_ref,
                                                             logical_naming=kensu.logical_naming)._report()
                destination_sc = kensu.extractors.extract_schema(destination_ds, dest)._report()
                kensu.real_schema_df[destination_sc.to_guid()] = dest
                dest_field_names = [f.name for f in destination_sc.pk.fields]
                query = job.query
                sq = sqlparse.parse(query)
                ids = list(filter(lambda x: isinstance(x, sqlparse.sql.Identifier), sq[0].tokens))
                for id in ids:
                    name = (id.get_name()).strip('`')
                    table = client.get_table(name)
                    ds = kensu.extractors.extract_data_source(table, kensu.default_physical_location_ref,
                                                              logical_naming=kensu.logical_naming)._report()
                    sc = kensu.extractors.extract_schema(ds, table)._report()

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

                    kensu.real_schema_df[sc.to_guid()] = table
                kensu.report_with_mapping()

            return result #TODO lineage and stuff if lost from here on

        wrapper.__doc__ = f.__doc__
        setattr(job, 'result', wrapper)
        return job

