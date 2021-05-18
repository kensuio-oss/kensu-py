#! python -m py.test test_sftp.py

import logging
import sys
import os
import unittest
import pytest


from kensu import pysftp
from kensu.client import ApiClient
from kensu.utils.kensu_provider import KensuProvider

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)


@pytest.mark.usefixtures("sftpserver")
class TestSftp(unittest.TestCase):
    offline = True
    api_url = os.environ.get('KSU_API_URL') or ''
    auth_token = os.environ.get('KSU_API_TOKEN') or ''
    kensu = KensuProvider().initKensu(init_context=True,
                                      api_url=api_url,
                                      auth_token=auth_token,
                                      report_to_file=offline,
                                      project_names=['pysftp'],
                                      offline_file_name='kensu-offline-to-pysftp-test.jsonl',
                                      mapping=True, report_in_mem=True)

    def setUp(self):
        self.ac = ApiClient()

    # see https://docs.pytest.org/en/reorganize-docs/unittest.html#autouse-fixtures-and-accessing-other-fixtures
    @pytest.fixture(autouse=True)
    def init_sftpserver(self, sftpserver, tmpdir):
        self.sftpserver = sftpserver
        self.tmpfile = tmpdir.join("samplefile.txt")
        self.tmpfile.write("# testdata")

    def test_one(self):
        # uses https://pypi.org/project/pytest-sftpserver/
        with self.sftpserver.serve_content({'a_dir': {'somefile.txt': "File content"}}):
            cnopts = pysftp.CnOpts()
            cnopts.hostkeys = None
            with pysftp.Connection(host=self.sftpserver.host,
                                   port=self.sftpserver.port,
                                   username='user',
                                   password='pass',
                                   cnopts=cnopts) as sftp:
                print("Connection to sftp OK  ... ")
                local_file_path = self.tmpfile
                remote_file_path = f"/2021-05-01.csv"
                sftp.put(local_file_path, remote_file_path)
                directory_structure = sftp.listdir_attr()
                uploaded = False
                for attr in directory_structure:
                    print(attr.filename, attr)
                    if "/" + attr.filename == remote_file_path:
                        uploaded = True
                assert uploaded, True


if __name__ == '__main__':
    unittest.main()
