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


    def test_merge_file2imp2func2count(self):
        d1 = dict()
        d1['f1'] = dict()
        d1['f1']['i1'] = dict()
        d1['f2'] = dict()
        d1['f2']['i1'] = dict()

        d2 = dict()
        d2['f1'] = dict()
        d2['f2'] = dict()
        d2['f3'] = dict()
        d2['f1']['i1'] = dict()
        d2['f2']['i2'] = dict()
        d2['f3']['i3'] = dict()

        # those two add up to 8
        d1['f1']['i1']['func1'] = 3
        d2['f1']['i1']['func1'] = 5
        # func1 only in d1
        d1['f1']['i1']['func2'] = 7
        # func only in d2
        d2['f1']['i1']['func3'] = 11
        # import only in d2
        d2['f2']['i2']['func1'] = 13
        # file only in d2
        d2['f3']['i3']['func4'] = 17

        r1 = d.merge_file2imp2func2count(d1, d2)
        assert r1['f1']['i1']['func1'] == 8
        assert r1['f1']['i1']['func2'] == 7
        assert r1['f1']['i1']['func3'] == 11
        assert r1['f2']['i2']['func1'] == 13
        assert r1['f3']['i3']['func4'] == 17


    def test_read_csv_in_pandas_getmembers(self):
        import pandas as pd
        from inspect import getmembers
        mems = getmembers(pd)
        keys = [m[0] for m in mems]
        print(f"'read_csv' in keys == {'read_csv' in keys}")
        assert 'read_csv' in keys

    def test_read_csv_in_pandas(self):
        py = '''import pandas as pd\ndf = pd.DataFrame()\npd.read_csv('data/%s/customers-data.csv')'''
        r = d.parse_single_file_content("test_mock_filename", py)
        assert r["test_mock_filename"]

    def __test_imports_flat(self):
        # TODO
        flat = d.imports_flat("pandas", dict())
        # print(flat)
        #print()
        #assert "read_csv" in flat("pandas").keys()

    def test_01(self):
        py = '''import math as m\nm.ceil(12.34)\nmath.atan2(0.5, 0.5)\nmath.atan2(0.5, 0.5)'''
        r = d.parse_single_file_content("test_mock_filename", py)
        assert len(r.keys()) == 1
        assert "test_mock_filename" in r.keys()
        assert r['test_mock_filename']['math']['ceil'] == 1
        assert r['test_mock_filename']['math']['atan2'] == 2
        print(r)
        

    def test_sammy(self):
        py = '''import sys
month = sys.argv[1]
import pandas as pd 
customers_info = pd.read_csv('data/%s/customers-data.csv'%month)
contact_info = pd.read_csv('data/%s/contact-data.csv'%month)
business_info = pd.read_csv('data/%s/business-data.csv'%month)
customer360 = customers_info.merge(contact_info,on='id')
monthly_ds = pd.merge(customer360,business_info)
monthly_ds.to_csv('data/%s/data.csv'%month,index=False)
'''
        r = d.parse_single_file_content("test_mock_filename_sammy", py)
        assert len(r.keys()) == 1
        assert r['test_mock_filename_sammy']['pandas']['to_csv'] == 1
        assert r['test_mock_filename_sammy']['pandas']['merge'] == 2
        assert r['test_mock_filename_sammy']['pandas']['read_csv'] == 3


if __name__ == '__main__':
    unittest.main()
