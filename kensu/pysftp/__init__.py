import pysftp
import os
import posixpath
import logging


# this import is actually used by end-user
from pysftp import CnOpts

from kensu.utils.helpers import report_simple_copy_with_guessed_schema


class Connection(pysftp.Connection):

    def __init__(self, host, username=None, private_key=None, password=None,
                 port=22, private_key_pass=None, ciphers=None, log=False,
                 cnopts=None, default_path=None):
        super().__init__(host,
                         username=username,
                         private_key=private_key,
                         password=password,
                         port=port,
                         private_key_pass=private_key_pass,
                         ciphers=ciphers,
                         log=log,
                         cnopts=cnopts,
                         default_path=default_path)
        self.ksu_sftp_host = host
        self.ksu_sftp_port = port

    def _ftp_server_addr(self):
        return f"ftp://{self.ksu_sftp_host}:{self.ksu_sftp_port}"

    def put(
            self,
            localpath,
            remotepath=None,
            callback=None,
            confirm=True,
            preserve_mtime=False
    ):
        result = super(Connection, self).put(
            localpath,
            remotepath=remotepath,
            callback=callback,
            confirm=confirm,
            preserve_mtime=preserve_mtime
        )
        if not remotepath:
            remotepath = os.path.split(localpath)[1]
        resolved_remote_path = posixpath.join(self.pwd, remotepath)
        qualified_remote_path = self._ftp_server_addr() + resolved_remote_path
        absolute_localpath = os.path.abspath(str(localpath))

        logging.info(f"sftp.put(localpath: {absolute_localpath}, remote_qualified_path:{qualified_remote_path})")
        # schema is not known for a generic ftp file copy !!! but we try to guess it
        from kensu.utils.helpers import get_absolute_path as get_kensu_abs_path
        kensu_normalized_absolute_path = get_kensu_abs_path(absolute_localpath)
        report_simple_copy_with_guessed_schema(
            input_uri=kensu_normalized_absolute_path,
            output_absolute_uri=qualified_remote_path,
            read_schema_from_filename=absolute_localpath,
            operation_type='sftp.put()'
        )
    put.__doc__ = pysftp.Connection.put.__doc__


Connection.__doc__ = pysftp.Connection.__doc__
