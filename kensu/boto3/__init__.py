import logging

import boto3
from boto3 import *

from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
from kensu.requests.models import ksu_str
from kensu.itertools import kensu_list
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.helpers import logical_naming_batch

class ksu_dict(dict):
    ksu_metadata = {}

    @property
    def __class__(self):
        return dict

    def __getitem__(self, item):
        result = super(ksu_dict, self).__getitem__(item)
        if isinstance(result,str):
            ksu_result = ksu_str(result)
        elif isinstance(result,list):
            ksu_result = kensu_list(result)
        elif isinstance(result,dict):
            ksu_result = ksu_dict(result)
        else:
            ksu_result = result

        if hasattr(ksu_result,'ksu_metadata'):
            ksu_result.ksu_metadata = self.ksu_metadata
        return ksu_result


def create_timestream_ds_schema(db, table, schema_dict):
    from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema
    ksu = KensuProvider().instance()
    ds_name = fmt_timestream_name(db, table)
    return KensuDatasourceAndSchema.for_path_with_opt_schema(
        ksu=ksu,
        ds_path=fmt_timestream_uri(db, table),
        format="TimeStream table",
        categories=fmt_timesteam_lds_names(db,table),
        maybe_schema=schema_dict.items(),
        ds_name=ds_name,
    )

def kensu_put(event_params, event_ctx, **kwargs):
    if isinstance(event_params.get('Body'), ksu_str):
        kensu = KensuProvider().instance()
        put_body = event_params.get('Body')

        #The input is the ksu_str, the metadata contains its schema pk
        input_schema = put_body.metadata['real_schema']
        short_schema = put_body.metadata['short_schema']

        input_location = put_body.metadata['ds_location']
        s3_bucket = event_params.get('Bucket') or 'unknown-s3-bucket'
        s3_key = event_params.get('Key') or 'unknown-s3-key'

        # Creation of the output datasource (stored in S3)
        location = 'aws::S3::' + s3_bucket + '/' + s3_key
        name = s3_key

        if kensu.logical_naming == 'ReplaceNumbers':
            logical = logical_naming_batch(name)
        else:
            logical = name

        result_pk = DataSourcePK(location=location,
                                 physical_location_ref=kensu.default_physical_location_ref)
        result_ds = DataSource(name=name, categories=['logical::'+logical],format=name.split('.')[-1],
                               pk=result_pk)._report()

        input_fields = [k.name for k in short_schema.pk.fields]
        input_schema_pk = short_schema.to_guid()

        # This data source has the same schema fields as the input

        fields = [FieldDef(name=k.name, field_type=k.field_type, nullable=True) for k in input_schema.pk.fields]

        sc_pk = SchemaPK(result_ds.to_ref(),
                         fields=fields)
        result_sc = Schema(name="schema:" + result_ds.name, pk=sc_pk)._report()

        fields = [FieldDef(name=k.name, field_type=k.field_type, nullable=True) for k in short_schema.pk.fields]

        sc_pk = SchemaPK(result_ds.to_ref(),
                         fields=fields)

        short_result_sc = Schema(name="short-schema:" + result_ds.name, pk=sc_pk)._report()

        kensu.real_schema_df[short_result_sc.to_guid()] = put_body.metadata['stats']

        for col in input_fields:
            kensu.add_dependencies_mapping(short_result_sc.to_guid(),str(col),input_schema_pk,str(col),'s3_put')
        kensu.report_with_mapping()


def fmt_timestream_uri(db, table):
    return f"aws::TimeStream://{db}.{table}"


def fmt_timestream_name(db, table):
    return f"TimeStream://{db}.{table}"


def fmt_timestream_lds_name(db, table):
    return fmt_timestream_name(db, table)


def fmt_timesteam_lds_names(db, table):
    # FIXME: for now DS name and LDS name (and LDS location) must match (need to update write_reconds otherwise)
    return ['logical::' + fmt_timestream_name(db, table),
            # 'logicalLocation::' + fmt_timestream_uri(db, table),
            ]

def kensu_timestream_query(event_params):
    logging.info('KENSU: handler of timestream_query.query...')
    # if true, we'll report all columns found in the table, doesn't matter what columns were actually referred
    # FIXME: do we care about exact columns which were referred?
    ALWAYS_REPORT_ALL_COLUMNS = True
    from pprint import pprint

    sql = event_params['QueryString']
    # ignore kensu agent issued queries
    if 'DESCRIBE ' in sql:
        return

    # FIXME: pass custom config if any - context['client_config'] / context['client_region']
    client = boto3.client('timestream-query')
    aws_lineage = client.prepare_query(
        QueryString=sql,
        ValidateOnly=True  # do not store the query in the DB
    )
    # FIXME: also maybe need to check the query type (is it SELECT, INSERT etc?)

    # P.S. "Aliased" property is "lying" in case we're querying a subquery, e.g.
    # `select * from (select truck_id as truck_id_renamed from tbl)` will say Aliased=False,
    # while in fact the column was renamed and we don't know it's original name
    # so we need to verify existence of columns
    resolved_db_tables = set([
        (c['DatabaseName'], c['TableName'])
        for c in aws_lineage.get('Columns', [])
        if c.get('DatabaseName') and c.get('TableName')
    ])
    # add tables from sqlineage which might have been unresolved by `client.prepare_query`
    try:
        from sqllineage.runner import LineageRunner
        lin_result = LineageRunner(sql, verbose=True)
        maybe_source_tables = [
            (t.schema.raw_name, t.raw_name)
            for t in lin_result.source_tables
            if t.schema and not (t.schema.raw_name, t.raw_name) in resolved_db_tables]
        # sqllineage knows nothing about actual database, so check if such tables exist
        for (db, table) in maybe_source_tables:
            exists = True
            try:
                client.query(QueryString=f'DESCRIBE "{db}"."{table}"')
            except:
                exists = False
            if exists:
                resolved_db_tables.add((db, table))

            # col_lin = lin_result.get_column_lineage(exclude_subquery=False)
    except:
        logging.info(f"Exception while extracting sqllineage for timesteam-query")


    # FIXME: in some cases even the table name is not available in prepare_query result, use sqllineage as fallback
    # e.g. when refering to a column of certain table only inside expression
    full_table_schemas = {
        (db, table): {row['Data'][0]['ScalarValue']: row['Data'][1]['ScalarValue']
                       for row in client.query(QueryString=f'DESCRIBE "{db}"."{table}"').get('Rows', [])}
        for (db, table) in resolved_db_tables
    }
    # not renamed columns, if any
    unchecked_known_input_columns = [
        (c['Name'], c['DatabaseName'], c['TableName'])
        # {'column_name': c['Name'],
        #  'db': c['DatabaseName'],
        #  'table': c['TableName']}
        for c in aws_lineage.get('Columns', [])
        if c.get('DatabaseName') and c.get('TableName') and c.get('Name')
    ]
    validated_discovered_input_columns = [
        (db, table, col_name, full_table_schemas.get((db, table), {}).get(col_name))
        for (col_name, db, table) in unchecked_known_input_columns
        if full_table_schemas.get((db, table), {}).get(col_name)
    ]
    from collections import defaultdict
    validated_input_columns = defaultdict(lambda: {})
    for (db, table, col_name, data_type) in validated_discovered_input_columns:
        validated_input_columns[(db, table)][col_name] = data_type

    # FIXME: get input columns from sqllineage too...
    # for each discovered input table, if we didn't find any input columns, assume that all columns were accessed
    for (db, table) in resolved_db_tables:
        if not validated_input_columns.get((db, table)) or ALWAYS_REPORT_ALL_COLUMNS:
            logging.warning(f"Kensu was unable to find exact input columns for timestream query table '{db}'.'{table}', using all columns...")
            validated_input_columns[(db, table)] = full_table_schemas.get((db, table), {})

    #print("Kensu Timestream-query:")
    #pprint(resolved_db_tables)
    #pprint(full_table_schemas)
    #pprint(validated_discovered_input_columns)
    #print("final:")
    #pprint(validated_input_columns)
    # report read operation to Kensu
    from kensu.utils.dsl.extractors.external_lineage_dtos import KensuDatasourceAndSchema
    ksu = KensuProvider().instance()
    for ((db, table), schema_dict) in validated_input_columns.items():
        ds = create_timestream_ds_schema(db, table, schema_dict)
        if ksu.lean_mode:
            ds.ksu_ds._report()
            ds.ksu_schema._report()
            ksu.real_schema_df[ds.ksu_schema.to_guid()] = None  # is this one needed?
            ksu.register_input_lean_mode(ds.ksu_schema)
        else:
            logging.warning("Timestream-query.query() kensu tracking is supported only in kensu_lean_mode=True")


def dim_to_schema(dim):
    return (dim.get('Name'), dim.get('DimensionValueType', 'unknown'))


# FIXME: infer datatypes for measures and dimensions

def dimensions_schema(rec):
    return [dim_to_schema(d)
            for d in rec.get('Dimensions', [])]
# e.g.:
# ---
#     'MeasureName': 'IoTMulti-stats',
#     'MeasureValues': [
#             {'Name': 'load', 'Value': '12.3', 'Type': 'DOUBLE'},
#             #{'Name': 'fuel-reading	', 'Value': '13.4', 'Type': 'DOUBLE'},
#         ],
#     'MeasureValueType': 'MULTI',
def measures_schema(rec):
    n = rec.get('MeasureName')
    data_type = rec.get('MeasureValueType', 'DOUBLE')
    # FIXME: special case if MULTI
    if not n:
        return []
    elif data_type == 'MULTI':
        values = rec.get('MeasureValues', [])
        return [(v.get('Name'), v.get('Type'))
                for v in values]
    else:
        return [(n, data_type)]


# returns a dict: {fieldName -> fieldType}
def extract_timestream_write_schema(records, common_attributes):
    # FIXME: take into account CommonAttributes
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/timestream-write.html#TimestreamWrite.Client.write_records
    if len(records) == 0:
        return {}
    else:
        rec = records[0]
        schema = dimensions_schema(rec) + measures_schema(rec) + [('time', 'timestamp')]
        if common_attributes:
            schema = schema + dimensions_schema(common_attributes) + measures_schema(common_attributes)
        return dict([(n.lower(), data_type.lower())
                     for (n, data_type) in schema])

def kensu_write_records(event_params):
    database = event_params['DatabaseName']
    table = event_params['TableName']
    records = list(event_params['Records'])

    kensu = KensuProvider().instance()
    # Creation of the output datasource (stored in S3)
    schema_dict = extract_timestream_write_schema(records, event_params.get('CommonAttributes'))
    ds = create_timestream_ds_schema(database, table, schema_dict)
    ds.ksu_ds._report()
    schema = ds.ksu_schema._report()

    # TODO: Create Stats

    if kensu.lean_mode:
        kensu.outputs_lean.append(schema)
        if ds.ksu_ds.name in kensu.ds_name_stats:
            stats_json = kensu.ds_name_stats[ds.ksu_ds.name]
        else:
            stats_json = None
        kensu.real_schema_df[schema.to_guid()]= stats_json
        kensu.report_without_mapping()




def add_custom_method(class_attributes, **kwargs):
    class_attributes['kensu_put'] = kensu_put

    original_get = class_attributes['get']

    def kensu_get(event_params, **kwargs):
        result = original_get(event_params,**kwargs)

        if 'Body' in result:
            result = ksu_dict(result)

            s3_bucket = event_params.bucket_name or 'unknown-s3-bucket'
            s3_key = event_params.key or 'unknown-s3-key'

            # Creation of the output datasource (stored in S3)
            location = 'aws::S3::' + s3_bucket + '/' + s3_key
            name = s3_key
            result.ksu_metadata['origin_location'] = location
            result.ksu_metadata['origin_name'] = name

            import botocore.response as btr
            from kensu.botocore.response import StreamingBody

            if isinstance(result['Body'],btr.StreamingBody):
                result['Body'].__class__ = StreamingBody
                result['Body'].ksu_metadata = result.ksu_metadata
        return result

    class_attributes['get'] = kensu_get

boto3._get_default_session().events.register("creating-resource-class.s3.Object",
                        add_custom_method)



def kensu_tracker(*class_attributes, **kwargs):
    import logging
    param_types = [
    ]
    import pprint
    if kwargs.get('params'):
        param_types = [[k, v, type(v)] for k, v in kwargs.get('params').items()]
    logging.debug('---\nKensu AWS tracker: '
          'param_types: {}\n'
          'class_attributes:{}\n kwargs: {}\n-----'.format(
        str(param_types),
        str(class_attributes),
        pprint.pformat(kwargs) + '\n'+ str([ [k, v, type(v)] for k,v in kwargs.items()])))

    event_name = kwargs.get('event_name')
    event_params = kwargs.get('params')
    event_ctx = kwargs.get('context')
    if event_name == 'provide-client-params.s3.PutObject' and event_params:
        kensu_put(event_params=event_params, event_ctx=event_ctx, **kwargs)
    if event_name == 'provide-client-params.timestream-write.WriteRecords' and event_params:
        kensu_write_records(event_params)
    if event_name == 'provide-client-params.timestream-query.Query' and event_params:
        kensu_timestream_query(event_params)

#boto3._get_default_session().events.register('creating-resource-class.s3.ServiceResource',kensu_tracker)
#boto3._get_default_session().events.register('before-send.s3.PutObject', kensu_tracker)
boto3._get_default_session().events.register('provide-client-params.s3.PutObject', kensu_tracker)

# in case we wanted to see all events - use *
#S3 = boto3.resource('s3' , region_name='eu-west-1')
#event_system = S3.meta.client.meta.events
#event_system.register("*",kensu_tracker)
#event_system.register('creating-resource-class.s3.*', prt)

#boto3._get_default_session().events.register("*",kensu_tracker)

boto3._get_default_session().events.register('provide-client-params.timestream-write.WriteRecords', kensu_tracker)
boto3._get_default_session().events.register('provide-client-params.timestream-query.Query', kensu_tracker)
