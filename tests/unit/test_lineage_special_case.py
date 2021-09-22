#! python -m py.test test_sftp.py

import logging
import sys
import os
import time
import unittest
import pytest

from kensu.client import ApiClient, DataSource, DataSourcePK, SchemaPK, Schema, FieldDef, ProcessLineagePK, ProcessRef, \
    ProcessLineage, SchemaRef, SchemaLineageDependencyDef, ProcessLineageRef, LineageRunPK, LineageRun, ProcessRunRef
from kensu.utils.kensu_provider import KensuProvider
from tests.unit.testing_helpers import setup_logging, setup_kensu_tracker
import kensu

setup_logging()


class TestLineageSpecialCase(unittest.TestCase):

    def setUp(self):
        self.ac = ApiClient()
        self.kensu_tracker = setup_kensu_tracker(test_cls=self)  # type: kensu.utils.kensu.Kensu

    def test_one(self):
        report_lineage_run = True
        ds1, schema1 = self.report_ds_with_schema('ds1', fields_list=['col1'])

        ds2_app1, ds2_app1_schema = self.report_ds_with_schema('ds2', fields_list=['col1'])
        # sent from app1: table1.col1 -> table2.col1
        self.report_lineage(schema1, ds2_app1_schema, {'col1': ['col1']}, report_lineage_run=report_lineage_run)

        # sent from app2: table2.field1 -> table3.field1
        # (table2.field1 was not known by app1, so lineage does not connect)
        ds2_app2, ds2_app2_schema = self.report_ds_with_schema('ds2', fields_list=['field1'])
        ds3_app2, ds3_app2_schema = self.report_ds_with_schema('ds3', fields_list=['field1'])
        self.report_lineage(ds2_app2_schema, ds3_app2_schema, {'field1': ['field1']},
                            report_lineage_run=report_lineage_run)

    # helpers bellow, you can ignore

    def report_ds(self, name):
        return DataSource(name=name,
                          pk=DataSourcePK(location='/' + name,
                                          physical_location_ref=self.kensu_tracker.UNKNOWN_PHYSICAL_LOCATION.to_ref()))._report()

    def report_ds_with_schema(self, ds_name, fields_list):
        ds = self.report_ds(ds_name)
        fields = list([
            FieldDef(name=str(f), field_type=str("unknown"), nullable=True)
            for f in fields_list
        ])
        sc_pk = SchemaPK(ds.to_ref(), fields=fields)
        return ds, Schema(name="schema:" + ds.name, pk=sc_pk)._report()

    def report_lineage(self, from_schema, to_schema, column_data_deps, report_lineage_run=True):
        dataflow = [
            SchemaLineageDependencyDef(from_schema_ref=from_schema.to_ref(),
                                       to_schema_ref=to_schema.to_ref(),
                                       column_data_dependencies=column_data_deps)
        ]
        lineage = ProcessLineage(name='Lineage from {} to {}'.format(from_schema.name, to_schema.name, ),
                                 operation_logic='APPEND',
                                 pk=ProcessLineagePK(
                                     process_ref=ProcessRef(by_guid=self.kensu_tracker.process.to_guid()),
                                     data_flow=dataflow))._report()

        if report_lineage_run:
            LineageRun(pk=LineageRunPK(lineage_ref=ProcessLineageRef(by_guid=lineage.to_guid()),
                                       process_run_ref=ProcessRunRef(
                                           by_guid=self.kensu_tracker.process_run.to_guid()),
                                       timestamp=round(int(time.time()) * 1000)))._report()

        return lineage


if __name__ == '__main__':
    unittest.main()
