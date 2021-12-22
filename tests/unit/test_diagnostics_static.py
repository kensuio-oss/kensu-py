#  python -m unittest discover -s tests/unit

import unittest

from kensu.diagnostics import diags_static as d


class TestDiagnosticsStatic(unittest.TestCase):

    def setUp(self):
        print("yolo")
        d.conf = d.DiagsConf(verbose=True, debug=True, pythonpath=None,
                             csv=False, json=False, files_dir=None)

    def tearDown(self):
        pass

    def test_01(self):
        py = """import math as m\nm.ceil(12.34)"""
        r = d.parse_single_file_content("test_mock_filename", py)
        assert
        print(f"r is {r}")

    """def test_02(self):
        py = '''import pandas\ndf = pandas.DataFrame()\ndf.describe()'''
        r = d.parse_single_file_content("test_mock_filename", py)
        print(f"r is {r}")
    """

if __name__ == '__main__':
    unittest.main()
