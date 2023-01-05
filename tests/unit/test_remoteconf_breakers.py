#  python -m unittest discover -s tests/unit

import logging
import sys
import unittest

log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)

from tests.unit.utils.http_to_jsonl_server import FakeIngestionConf, FakeIngestionApi

from kensu.utils.kensu import Kensu
from kensu.utils.kensu_provider import KensuProvider
from kensu.utils.remote.circuit_breakers import query_if_to_break_app, break_app_if_needed
from kensu.utils.remote.remote_conf import query_metric_conf, SingleLdsRemoteConf

from tests.unit.testing_helpers import setup_kensu_tracker, setup_logging

setup_logging()


class CustomIgnoredException(BaseException):
    def __init__(self, *args, **kwargs):  # real signature unknown
        pass


class TestRemoteConfAndBreakers(unittest.TestCase):
    server = None  # type: FakeIngestionApi
    server_port = None  # type: int

    known_process_name = 'my-process-name'
    known_lds_name = 'hive_database.db/hive_table'
    known_lds_names = [
        "hive_database.db/hive_table",
        "/warehouse/2019-10/my_ds_name_3"
    ]

    @classmethod
    def setUpClass(cls) -> None:
        # start fake server
        ingestion_token = 'mytoken'
        conf = FakeIngestionConf(out_file_path='outfile.custom.txt',
                                 error_log_path='errors.txt',
                                 expected_useragent_subsubstr=None,
                                 expected_xauth_token=ingestion_token)
        cls.server = FakeIngestionApi.create(conf=conf)
        cls.server_port = cls.server.__enter__()
        print(f'bound fake ingestion server to port={cls.server_port}')
        # Setup kensu-py
        setup_kensu_tracker(out_file='somefile.txt',
                            process_name=cls.known_process_name)
        ksu = KensuProvider().instance()
        # need to be after kensu init, to override default config
        Kensu._configure_api(ksu.kensu_remote_conf_api, f'http://localhost:{cls.server_port}', ingestion_token)
        ksu.remote_circuit_breaker_precheck_delay_secs = 1

    @classmethod
    def tearDownClass(cls) -> None:
        print('tearDownClass')
        if cls.server:
            print(f'Closing FakeIngestionApi at port {cls.server_port}')
            cls.server.__exit__(None, None, None)

    def test_circuit_breaker_positive(self):
        ksu = KensuProvider().instance()
        break_app_now = query_if_to_break_app(
            api=ksu.kensu_remote_conf_api,
            process_name=self.known_process_name,
            lds_names=self.known_lds_names)
        print(f'break_app_now: {break_app_now}')
        print(break_app_now.__class__)
        assert break_app_now

    def test_circuit_breaker_kill_app(self):
        expected_exit_code = 253
        # mock that we "accessed" bad datasource(s)
        ksu = KensuProvider().instance()
        ksu.circuit_breaker_logical_datasource_names = self.known_lds_names
        with self.assertRaises(SystemExit) as cm:
            break_app_if_needed(exit_code=expected_exit_code)
        self.assertEqual(cm.exception.code, expected_exit_code)

    def test_circuit_breaker_negative(self):
        ksu = KensuProvider().instance()
        break_app_now = query_if_to_break_app(
            api=ksu.kensu_remote_conf_api,
            process_name="unknown-process-name",
            lds_names=self.known_lds_names)
        print(f'break_app_now: {break_app_now}')
        assert not break_app_now

        break_app_now = query_if_to_break_app(
            api=ksu.kensu_remote_conf_api,
            process_name=self.known_process_name,
            lds_names=["other_lds", "another_lds"])
        print(f'break_app_now: {break_app_now}')
        assert not break_app_now

    def test_circuit_breaker_not_kill_app(self):
        # FIXME: test that we sleep for ...
        # assert that `break_app_if_needed()` doesn't raise a SystemExist
        # (as CustomIgnoredException wouldn't be raised otherwise)
        ksu = KensuProvider().instance()
        # mock that we "accessed" good datasource(s)
        ksu.circuit_breaker_logical_datasource_names = ['unknown-lds']
        with self.assertRaises(CustomIgnoredException):
            break_app_if_needed(exit_code=253)
            raise CustomIgnoredException()

    def test_remote_conf_defaults(self):
        ksu = KensuProvider().instance()
        default_conf = SingleLdsRemoteConf.default()
        # no match => default
        # unknown lds_name; using self.known_process_name from Kensu.process_name
        c = query_metric_conf(lds_name='unknown_lds_name')
        assert c == default_conf

        # unknown process_name
        c = query_metric_conf(lds_name=self.known_lds_name, process_name='unknown-process-name')
        assert c == default_conf

    def test_remote_conf(self):
        # explicit metrics, as responded by remote API
        specific_conf = SingleLdsRemoteConf(
            activeMetrics=[
                'featurefirst.min',
                'featurefirst.nullrows',
                'featuresecond.stddev',
                'nrows',
                'id.nrows'
            ],
            useDefaultConfig=False
        )
        # using self.known_process_name from Kensu.process_name
        assert query_metric_conf(lds_name=self.known_lds_name) == specific_conf


if __name__ == '__main__':
    unittest.main()
