import boto3
from boto3 import *

from kensu.client import DataSourcePK, DataSource, FieldDef, SchemaPK, Schema
from kensu.requests.models import ksu_str
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.helpers import logical_naming_batch

class ksu_dict(dict):
    ksu_metadata = {}

    @property
    def __class__(self):
        return dict


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

#boto3._get_default_session().events.register('creating-resource-class.s3.ServiceResource',kensu_tracker)
#boto3._get_default_session().events.register('before-send.s3.PutObject', kensu_tracker)
boto3._get_default_session().events.register('provide-client-params.s3.PutObject', kensu_tracker)

# in case we wanted to see all events - use *
#S3 = boto3.resource('s3' , region_name='eu-west-1')
#event_system = S3.meta.client.meta.events
#event_system.register("*",kensu_tracker)
#event_system.register('creating-resource-class.s3.*', prt)