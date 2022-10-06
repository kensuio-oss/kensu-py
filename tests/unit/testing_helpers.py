import logging
import os
import re
import sys

from kensu.utils.kensu_provider import KensuProvider


def setup_logging():
    log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=log_format)


def setup_kensu_tracker(
        test_cls=None,
        out_file=None,
        offline=True,
        project_names=None,
        report_in_mem=False,
        **kwargs
):
    offline = True
    api_url = os.environ.get('KSU_KENSU_INGESTION_URL') or ''
    auth_token = os.environ.get('KSU_KENSU_INGESTION_TOKEN') or ''
    if test_cls:
        test_name = test_cls.__class__.__name__
        if out_file is None:
            out_file = test_name + '.jsonl'
        if project_names is None:
            project_names =[test_name]
    try:
        os.remove(out_file)
    except:
        pass
    KensuProvider().initKensu(
        init_context=True,
        allow_reinit=True,
        kensu_ingestion_url=api_url,
        kensu_ingestion_token=auth_token,
        report_to_file=offline,
        project_names=project_names,
        offline_file_name=out_file,
        mapping=True,
        report_in_mem=report_in_mem,
       **kwargs)


def assert_log_msg_exists(msg, msg2=None, msg3=None, full_str_match=False, test_case = None):
    def contains(m, line):
        if isinstance(m, re.Pattern):
            return bool(re.search(m, line))
        else:
            if full_str_match:
                return m is None or '"{}"'.format(m) in line
            else:
                return m is None or m in line
    with open(KensuProvider().instance().offline_file_name, "r") as f:
        lines = f.readlines()
        b = bool([True for l in lines
                     if msg in l and contains(msg2, l) and contains(msg3, l)])
        if test_case is not None:
            lines_str = "\n".join(["- " + str(l) for l in lines])
            test_case.assertTrue(b, "Missing a line with all of '{}' '{}' '{}' in offline file:\n {}".format(msg, msg2, msg3, lines_str))
        else:
            assert b
