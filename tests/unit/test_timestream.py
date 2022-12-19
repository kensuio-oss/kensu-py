#  python -m unittest discover -s tests/unit

import logging
import sys
import unittest

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)

from kensu.boto3 import *


class TestTimestream(unittest.TestCase):

    def test_fmt_names(self):
        assert fmt_timestream_name('mydb', 'mytable') == 'TimeStream://mydb.mytable'
        assert fmt_timestream_uri('mydb', 'mytable') == 'aws::TimeStream://mydb.mytable'

    # official spec
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/timestream-write.html#TimestreamWrite.Client.write_records
    # here, we're trying to match the schema as displayed in TimeStream DB UI @ AWS
    def test_write_measure_schema(self):
        # MeasureName is optional
        assert measures_schema({}) == []
        # FIXME: is lowercase keys/values supported?
        # default type = DOUBLE
        assert measures_schema({'MeasureName': 'n'}) == [('n', 'DOUBLE')]
        assert measures_schema({'MeasureName': 'n', 'MeasureValueType': 'VARCHAR'}) == [('n', 'VARCHAR')]
        # MULTI datatype implies multiple measure columns, and then MeasureName is ignored
        assert measures_schema({'MeasureName': 'IoTMulti-stats',
                                'MeasureValueType': 'MULTI',
                                'MeasureValues': [
                                    # Type is required here
                                    {'Name': 'load', 'Value': '12.3', 'Type': 'DOUBLE'},
                                    {'Name': 'fuelreading', 'Value': '13', 'Type': 'BIGINT'},
                                ],
                                }) == [
                   ('load', 'DOUBLE'),
                   ('fuelreading', 'BIGINT'),
               ]

    def test_write_dimensions_schema(self):
        assert dimensions_schema({}) == []
        assert dimensions_schema({'Dimensions': []}) == []
        # FIXME: is lowercase keys/values supported?
        assert dimensions_schema({'Dimensions': [
            # DimensionValueType is optional. FIXME: infer datatype from the value of first record entry ?
            {'Name': 'dim1'},
            {'Name': 'dim2', 'DimensionValueType': 'VARCHAR'},
        ]}) == [('dim1', 'unknown'), ('dim2', 'VARCHAR')]

    def test_write_schema(self):
        records = [
            {
                'MeasureName': 'measure1',
                'MeasureValueType': 'VARCHAR',
                'Dimensions': [
                    {'Name': 'dim1'},
                    {'Name': 'dim2', 'DimensionValueType': 'VARCHAR'}]
            }
        ]
        # result schema is in lowercase
        expected = {
            'measure1': 'varchar',
            'dim1': 'unknown',
            'dim2': 'varchar',
            # time is automatically added
            'time': 'timestamp',
        }
        assert extract_timestream_write_schema(records, common_attributes=None) == expected

        records = [
            {
                'MeasureName': 'measure1-ignored',
                'MeasureValueType': 'MULTI',
                'MeasureValues': [
                    # Type is required here
                    # FIXME: there's some limitations/exceptions with special characters in measure names it seems,
                    #  like `-` which we do not handle yet
                    {'Name': 'load-Measure', 'Value': '12.3', 'Type': 'DOUBLE'},
                    {'Name': 'fuel-Reading', 'Value': '13', 'Type': 'BIGINT'},
                ],
                'Dimensions': [
                    {'Name': 'dim1'},
                    {'Name': 'dim2', 'DimensionValueType': 'VARCHAR'}]
            }
        ]
        expected = {
            'load-measure': 'double',
            'fuel-reading': 'bigint',
            'dim1': 'unknown',
            'dim2': 'varchar',
            # time automatically added
            'time': 'timestamp'
        }
        assert extract_timestream_write_schema(records, common_attributes=None) == expected
        # should also work if all schema stuff is provided only inside CommonAttributes
        # (when `records` contain only values)
        assert extract_timestream_write_schema(records=[{}], common_attributes=records[0]) == expected


if __name__ == '__main__':
    unittest.main()
