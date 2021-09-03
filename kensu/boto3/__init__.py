import boto3
from boto3 import *

from kensu.requests.models import ksu_str


def kensu_put(event_params, event_ctx, **kwargs):
    if isinstance(event_params.get('Body'), ksu_str):
        put_body = event_params.get('Body')
        #The input is the ksu_str, the metadata contains its schema pk
        input_schema = put_body.metadata['schema']
        input_location = put_body.metadata['ds_location']
        s3_bucket = event_params.get('Bucket') or 'unknown-s3-bucket'
        s3_key = event_params.get('Key') or 'unknown-s3-key'
        from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs
        GenericComputedInMemDs.report_copy_with_opt_schema(
            src=input_location,
            src_name=None,
            dest='aws::S3::' + s3_bucket + '/' + s3_key,  # output datasource (stored in S3)
            dest_name=s3_key,
            operation_type="s3.put()",
            maybe_schema=[(f.name, f.field_type) for f in input_schema.pk.fields]
        )

def add_custom_method(class_attributes, **kwargs):
    class_attributes['kensu_put'] = kensu_put

boto3._get_default_session().events.register("creating-resource-class.s3.Object",
                        add_custom_method)



def kensu_tracker(*class_attributes, **kwargs):
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
# event_system = S3.meta.client.meta.events
# event_system.register("*",kensu_tracker)
#event_system.register('creating-resource-class.s3.*', prt)