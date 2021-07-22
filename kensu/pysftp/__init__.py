import pysftp
import os
import posixpath
import logging


# this import is actually used by end-user
from pysftp import CnOpts


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
        maybe_schema = [("unknown, unknown"), ]
        from kensu.utils.helpers import extract_ksu_ds_schema
        from kensu.utils.helpers import get_absolute_path as get_kensu_abs_path
        kensu_normalized_absolute_path = get_kensu_abs_path(absolute_localpath)
        try:
            import kensu.pandas as pd
            maybe_pandas_df = pd.read_csv(absolute_localpath, sep=";")
            from kensu.utils.kensu_provider import KensuProvider
            ksu = KensuProvider().instance()
            ds, schema = extract_ksu_ds_schema(ksu, maybe_pandas_df, report=False, register_orig_data=False)
            maybe_schema = [(f.name, f.field_type) for f in schema.pk.fields]
        except:
            print("Kensu failed to infer schema for data of pysftp copy operation...")
            import traceback
            traceback.print_exc()
            traceback.print_tb(tb=None)
        print('Extracted schema:', maybe_schema)
        from kensu.utils.dsl.extractors.external_lineage_dtos import GenericComputedInMemDs
        GenericComputedInMemDs.report_copy_with_opt_schema(
            src=kensu_normalized_absolute_path,
            dest=qualified_remote_path,
            operation_type="sftp.put()",
            maybe_schema=maybe_schema
        )

    put.__doc__ = pysftp.Connection.put.__doc__


Connection.__doc__ = pysftp.Connection.__doc__
