import boto3
from boto3 import *

from kensu.client import DataSourcePK, DataSource, Schema, SchemaPK, FieldDef
from kensu.utils.kensu_provider import KensuProvider
from kensu.requests.models import ksu_str
from kensu.utils.helpers import eventually_report_in_mem


def kensu_put(self,**kwargs):
    self.put(**kwargs)

    if isinstance(kwargs['Body'], ksu_str):
        #The input is the ksu_str, the metadata contains its schema pk

        input_schema = kwargs['Body'].metadata['schema']
        input_location = kwargs['Body'].metadata['ds_location']

        #Creation of the output datasource (stored in S3)
        location = 'aws::S3::' + self.bucket_name + '/' + self.key
        name = self.key

        kensu = KensuProvider().instance()

        result_pk = DataSourcePK(location=location,
                                 physical_location_ref=kensu.default_physical_location_ref)
        result_ds = DataSource(name=name, format=name.split('.')[-1],
                               pk=result_pk)._report()

        # This data source has the same schema fields as the input

        fields = [FieldDef(name=k.name,field_type=k.field_type,nullable=True) for k in input_schema.pk.fields]

        sc_pk = SchemaPK(result_ds.to_ref(),
                         fields=fields)
        result_sc = Schema(name="schema:" + result_ds.name, pk=sc_pk)._report()

        kensu.real_schema_df[result_sc.to_guid()] = None

        from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs
        GenericComputedInMemDs.report_copy_with_opt_schema(
            src=input_location,
            dest=location,
            operation_type="s3.put()",
            maybe_schema=[(f.name, f.field_type) for f in input_schema.pk.fields]
        )

def add_custom_method(class_attributes, **kwargs):
    class_attributes['kensu_put'] = kensu_put

boto3._get_default_session().events.register("creating-resource-class.s3.Object",
                        add_custom_method)
