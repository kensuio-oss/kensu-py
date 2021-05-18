#! python -m py.test test_sftp.py

import logging
import sys
import os
import unittest

#import pysftp

from kensu import pysftp
from kensu.client import ApiClient
from kensu.utils.kensu_provider import KensuProvider

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)

import pytest


@pytest.mark.usefixtures("sftpserver")
class TestSftp(unittest.TestCase):
    offline = False
    api_url=os.environ.get('KSU_API_URL') or ''
    auth_token=os.environ.get('KSU_API_TOKEN') or ''
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
            today = '2021-05-01'
            cnopts = pysftp.CnOpts()
            cnopts.hostkeys = None
            with pysftp.Connection(host=self.sftpserver.host,
                                   port=self.sftpserver.port,
                                   username=None,
                                   password=None,
                                   cnopts=cnopts) as sftp:
                print("Connection to sftp OK  ... ")
                localFilePath = self.tmpfile
                remoteFilePath = f"/{today}.csv"
                result = sftp.put(localFilePath, remoteFilePath)
                print('stat info:' + str(dir(result)))
                directory_structure = sftp.listdir_attr()
                uploaded = False
                # import paramiko
                # t = sftp._transport  # type: paramiko.Transport
                print(str(f"ftp://{sftp.ksu_sftp_host}:{sftp.ksu_sftp_port}"))
                for attr in directory_structure:
                    print(attr.filename, attr)
                    if "/" + attr.filename == remoteFilePath:
                        uploaded = True
                assert uploaded, True


if __name__ == '__main__':
    unittest.main()
