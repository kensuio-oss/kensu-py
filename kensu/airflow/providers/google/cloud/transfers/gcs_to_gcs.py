from typing import TYPE_CHECKING

import logging

from airflow.providers.google.cloud.hooks.gcs import GCSHook
from airflow.providers.google.cloud.transfers import gcs_to_gcs as airflow_gcs_to_gcs

from kensu.airflow.kensu_airflow_collector import COLLECTOR_STATUS_INIT, COLLECTOR_STATUS_DONE, log_status, \
    airflow_init_kensu, handle_ex
from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs

if TYPE_CHECKING:
    from airflow.utils.context import Context


class GCSToGCSOperator(airflow_gcs_to_gcs.GCSToGCSOperator):
    def __init__(
            self,
            *args,
            **kwargs,
    ):
        super(GCSToGCSOperator, self).__init__(
            *args, **kwargs
        )
        self.ksu_copied_objects = []

    def _copy_single_object(self, hook, source_object, destination_object):
        res = super(GCSToGCSOperator, self)._copy_single_object(hook, source_object, destination_object)
        logging.info(
            f"Kensu _copy_single_object(source_object={source_object}, destination_object={destination_object})")
        self.ksu_copied_objects.append([source_object, destination_object])
        return res

    def _is_dir(self, hook, bucket_name, object_name):
        try:
            hook.get_blob_update_time(bucket_name, object_name)
            return False
        except ValueError:
            return True

    def execute(self, context: 'Context') -> None:
        # FIMXE: there's `self.move_object: bool`, we might want to get some info (stats) before actual copy happens
        res = super(GCSToGCSOperator, self).execute(context)
        try:
            log_status(self, COLLECTOR_STATUS_INIT)
            airflow_init_kensu(airflow_operator=self)
            logging.info(f"self.ksu_copied_objects={self.ksu_copied_objects}")
            hook = GCSHook(
                gcp_conn_id=self.gcp_conn_id,
                delegate_to=self.delegate_to,
                impersonation_chain=self.impersonation_chain,
            )
            for src, dest in self.ksu_copied_objects:
                src_uri = f"gs://{self.source_bucket}/{src}"
                dest_uri = f"gs://{self.destination_bucket}/{dest}"
                dest_categories = None
                # FIXME: do we any need special LDSo/PDSo logic here?
                # if self.destination_object and \
                #         self._is_dir(hook, bucket_name=self.destination_bucket, object_name=self.destination_object):
                #     lds_relative_path = self.destination_object.rstrip('/')
                #     lds_name = f"gs :: {lds_relative_path}"
                #     lds_location = full_gs_uri(self.destination_bucket, lds_relative_path)
                #     lds_name = lds_location
                #     dest_categories = [
                #         f"logical::{lds_name}",
                #         f"logicalLocation::{lds_location}"
                #     ]

                # e.g.:
                #             source_object=f'{INPUT_PART}/{colour}_{DATASET}*.{INPUT_FILETYPE}',
                #             destination_object=f'{colour}/{colour}_{DATASET}',
                logging.info(f"""
                GCSToGCSOperator:
                    src={src_uri},
                    dest={dest_uri},
                    dest_categories={dest_categories},
                    """)
                GenericComputedInMemDs.report_copy_with_opt_schema(
                    src=src_uri,
                    dest=dest_uri,
                    dest_categories=dest_categories,
                    operation_type='GCSToGCSOperator'
                )
        except Exception as ex:
            handle_ex(self, ex)
        log_status(self, COLLECTOR_STATUS_DONE)
        return res


GCSToGCSOperator.__doc__ = airflow_gcs_to_gcs.GCSToGCSOperator.__doc__
