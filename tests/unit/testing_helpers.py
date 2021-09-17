import logging
import os
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
    api_url = os.environ.get('KSU_API_URL') or ''
    auth_token = os.environ.get('KSU_API_TOKEN') or ''
    if test_cls:
        test_name = test_cls.__class__.__name__
        if out_file is None:
            out_file = test_name + '.jsonl'
        if project_names is None:
            project_names =[test_name]
    KensuProvider().initKensu(
        init_context=True,
        allow_reinit=True,
        api_url=api_url,
        auth_token=auth_token,
        report_to_file=offline,
        project_names=project_names,
        offline_file_name=out_file,
        mapping=True,
        report_in_mem=report_in_mem,
       **kwargs)
