import functools
import multiprocessing
import traceback
import time
import json

from datetime import datetime


try:
    # py2
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ForkingMixIn
except ImportError:
    # py3
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ForkingMixIn


class FakeIngestionConf(object):

    def __init__(self, out_file_path, error_log_path, expected_useragent_subsubstr=None, expected_xauth_token=None):
        self.out_file_path = out_file_path
        self.expected_useragent_subsubstr = expected_useragent_subsubstr
        self.expected_xauth_token = expected_xauth_token
        self.error_log_path = error_log_path


class FakeIngestionRequestHandler(BaseHTTPRequestHandler):

    def __init__(self,
                 conf, # type: FakeIngestionConf
                 *args, **kwargs):
        print('RequestHandler conf', conf)
        print("args: {}".format(str(args)))
        print("kwargs: {}".format(str(kwargs)))
        self.conf = conf
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def dam_log_error(self, *args):
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = current_datetime + " " + " ".join([str(arg) for arg in args])
        print(msg)
        with open(self.conf.error_log_path, 'a') as f:
            f.write(msg + "\n")

    @staticmethod
    def dict_to_json(a_dict):
        return json.dumps(a_dict, sort_keys=True, indent=2)

    @staticmethod
    def request_to_offline_entry(body):
        template = """{
                      "action": "add_entity",
                      "entity": "BATCH_ENTITY_REPORT",
                      "generatedEntityGUID": "",
                      "schemaVersion": "0.1",
                      "jsonPayload": {body},
                      "context": {
                        "clientId": "",
                        "clientEventTimestamp": 1603276603676,
                        "serverReceivedTimestamp": 1603276603676
                      }
                    }"""
        return template.replace("\n", "").replace("\r", "").replace("{body}", body) + "\n"

    def do_POST(self):
        if self.path == '/v1/dam/api/base-entities-batch':
            json_resp = {
                "numIngested": 0,
                "numErrors": 0
            }
            req_content_length = int(self.getheader('content-length', 0))
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(self.dict_to_json(json_resp).encode("utf-8"))
            self.wfile.flush()
            try:
                print('request headers: {}'.format(self.headers))
                request_body_json = self.rfile.read(req_content_length).decode('utf-8')
                offline_file_entry = self.request_to_offline_entry(request_body_json)
                # print('processed request json: {}'.format(offline_file_entry))
                self.ensure_required_headers_present()
                with open(self.conf.out_file_path, 'ab') as outfile:
                    outfile.write(offline_file_entry.encode('utf-8'))
            except IOError:
                print('IOError: {}'.format(traceback.format_exc()))
                raise
        elif self.path == '/api/services/v2/logical-datasources/configuration/processes/metrics':
            json_resp = {
                            "processName": "ignored",
                            "metricsConfiguration": [
                                {
                                    "logicalDataSource": {"ldsName":"hive_database.db/hive_table"},
                                    "useDefaultConfig": False,
                                    "activeMetrics": [
                                      'featuresecond.median', 'id_pro.nullrows', 'featurefirst.min', 'featurefirst.nullrows', 'featuresecond.stddev', 'featurefirst.mean', 'featuresecond.max', 'nrows', 'featuresecond.mean', 'featurefirst.median', 'activity.nullrows', 'featurefirst.max', 'featuresecond.nrows', 'featuresecond.min', 'featurefirst.75%', 'featuresecond.25%', 'featuresecond.75%', 'featuresecond.nullrows', 'featurefirst.25%', 'featurefirst.nrows', 'activity.nrows', 'id.nrows'
                                      # excludes 'featurefirst.stddev' and a few more (depending on PDS)
                                    ]
                                },

                                {
                                    "logicalDataSource": {"ldsName":"warehouse/2019-10/somefile"},
                                    "useDefaultConfig": True
                                }
                            ]
                        }
            req_content_length = int(self.getheader('content-length', 0))
            try:
                body = self.rfile.read(req_content_length).decode('utf-8')
                print(f'/api/services/v2/logical-datasources/configuration/processes/metrics headers: {self.headers} body: {body}')
                import json
                body_json = json.loads(body)
                requested_info = body_json.get('requestedInfo')
                print(f'metrics/conf requested_info: {requested_info}')
                if requested_info:
                    if requested_info == 'BREAKERS':
                        json_resp = {'breakProcessExecutionNow': True, "processName": "ignored"}
                    elif requested_info == 'ALL':
                        json_resp['breakProcessExecutionNow'] = True
            except:
                print('Error: {}'.format(traceback.format_exc()))
                raise
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(self.dict_to_json(json_resp).encode("utf-8"))
            self.wfile.flush()
        else:
            self.send_error(404, '404')
        return

    def getheader(self, header_name, default):
        try:
            # py2
            return self.headers.getheader(header_name, default)
        except AttributeError:
            # py3
            return self.headers.get(header_name, default)

    def ensure_required_headers_present(self):
        self.ensure_required_header_present('User-Agent', self.conf.expected_useragent_subsubstr)
        self.ensure_required_header_present('X-Auth-Token', self.conf.expected_xauth_token)

    def ensure_required_header_present(self, header_name, expected_value):
        header_value = self.getheader(header_name, '')
        if expected_value is not None and not (expected_value in header_value):
            msg = "ERROR {} header with value '{}' did not contain the expected value '{}'".format(header_name, header_value, expected_value)
            self.dam_log_error(msg)


def run_server_bg_process(q,
                          conf  # type: FakeIngestionConf
                          ):
    print('run_server_bg_process to write to {}'.format(conf.out_file_path))
    handler = functools.partial(FakeIngestionRequestHandler, conf)
    httpd = HTTPServer(('0.0.0.0', 0), handler)
    httpd.timeout = 5
    port = httpd.socket.getsockname()[1]
    q.put(port)
    while True:
        httpd.handle_request()


class FakeIngestionApi:
    @staticmethod
    def create(conf  # type: FakeIngestionConf
               ):
        return FakeIngestionApi(conf)

    def __init__(self,
                 conf  # type: FakeIngestionConf
                 ):
        self.out_file_path = conf.out_file_path
        self.mp_queue = multiprocessing.Queue()
        self.p = multiprocessing.Process(target=run_server_bg_process,
                                         name='serve',
                                         args=(self.mp_queue, conf))

    def __enter__(self):
        self.p.start()
        port = self.mp_queue.get()
        print('Started a fake dam-ingestion-api server on port {} which will dump all requests to {}'.format(port,
                                                                                                             self.out_file_path))
        return port

    def __exit__(self, type, value, traceback):
        self.p.terminate()


if __name__ == '__main__':
    conf = FakeIngestionConf(out_file_path='outfile.custom.txt',
                             error_log_path='errors.txt',
                             expected_useragent_subsubstr=None,
                             expected_xauth_token='token')
    with FakeIngestionApi.create(conf=conf) as fake_ingestion_port:
        print('bound fake ingestion server to port={}'.format(fake_ingestion_port))
        time.sleep(1000)
