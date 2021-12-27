#  python -m unittest discover -s tests/unit

import unittest

from kensu.diagnostics import diags_static as d


class TestDiagnosticsStatic(unittest.TestCase):

    def setUp(self):
        print("\nyolo\n")
        d.conf = d.DiagsConf(verbose=True, debug=True, pythonpath=None,
                             csv=False, json=False, files_dir=None)

    def tearDown(self):
        pass

    def test_imports_flat(self):
        flat = d.imports_flat("pandas", dict())
        print(flat)
        print()
        assert "read_csv" in flat("pandas")

    """
    def test_01(self):
        py = '''import math as m\nm.ceil(12.34)\nmath.atan2(0.5, 0.5)\nmath.atan2(0.5, 0.5)'''
        r = d.parse_single_file_content("test_mock_filename", py)
        assert "test_mock_filename" in r.keys()
        assert len(r.keys()) == 1
        print(r)
        # {'test_mock_filename': {'math': {'ceil': 1}}}
        # assert r.values()[0].keys[0] == "math"
        # assert r.values()[0].values[0].keys[0] == "math"

    """

    def test_sammy(self):
        py = """import sys
month = sys.argv[1]
import pandas as pd 
customers_info = pd.read_csv('data/%s/customers-data.csv'%month)
contact_info = pd.read_csv('data/%s/contact-data.csv'%month)
business_info = pd.read_csv('data/%s/business-data.csv'%month)
customer360 = customers_info.merge(contact_info,on='id')
monthly_ds = pd.merge(customer360,business_info)
monthly_ds.to_csv('data/%s/data.csv'%month,index=False)
"""
        r = d.parse_single_file_content("test_mock_filename_sammy", py)
        # assert "test_mock_filename_sammy" in r.keys()
        # assert len(r.keys()) == 1
        print(r)

    #
    # TODO kensu-py
    """
    def test_02(self):
        # TODO check pandas is installed when running this test
        py = '''import pandas\ndf = pandas.DataFrame()\ndf.describe()'''
        r = d.parse_single_file_content("test_mock_filename", py)
        print(f"r is {r}")
    """

if __name__ == '__main__':
    unittest.main()
