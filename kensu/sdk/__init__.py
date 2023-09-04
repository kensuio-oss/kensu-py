import logging
import os
from datetime import datetime

import requests

from abc import ABC, abstractmethod


# we could reuse the reporters instead
from kensu.utils.exceptions import SdkError


class AbstractSDK(ABC):
    @abstractmethod
    def get_cookie(self):
        pass

    @abstractmethod
    def get_lineages_in_project(self, project, process, env, code_version):
        pass

    @abstractmethod
    def create_rule(self, lds_id, lineage_id, project_id, process_id, env_name, field_name, fun):
        pass

    @abstractmethod
    def update_rule(self, predicate, fun):
        pass

    @abstractmethod
    def get_rules(self):
        pass

    @abstractmethod
    def get_all_rules_for_ds(self, ds_id):
        pass

    @abstractmethod
    def get_rules_for_ds_in_project(self, ds_id, lineage_id, project_id, env):
        pass

    @abstractmethod
    def get_datasources_in_logical(self, logical):
        pass

    @abstractmethod
    def get_datasource(self, dsId):
        pass

    @abstractmethod
    def get_latest_datasource_in_logical(self, logical, n=-1):
        pass

    @abstractmethod
    def get_schema(self, schema_id):
        pass

    @abstractmethod
    def get_latest_schema_in_datasource(self, ds):
        pass

    @abstractmethod
    def get_latest_schema_in_logical(self, logical,n=-1):
        pass

    @abstractmethod
    def get_latest_stats_for_ds(self, projectId, env, linId, dsId):
        pass

    @abstractmethod
    def get_logical_ds_name_from_ds(self, dsId):
        pass

    @abstractmethod
    def get_datasources(self):
        pass

    @abstractmethod
    def get_logical_datasources(self):
        pass

    @abstractmethod
    def get_total_sent_data_mb(self):
        pass

    @abstractmethod
    def get_detailed_sent_data(self):
        pass


def normalize_services_response(func):
    def wrapper(*args, **kwargs):
        res = func(*args, **kwargs)
        if res and 'data' not in res:
            return {'data': res}
        return res
    wrapper.__doc__ = func.__doc__
    return wrapper


class DoNothingSDK(ABC):
    def __init__(self):
        pass

    def get_cookie(self):
        pass
    
    def get_lineages_in_project(self, project, process, env, code_version):
        pass
    
    def create_rule(self, lds_id, lineage_id, project_id, process_id, env_name, field_name, fun):
        pass
    
    def update_rule(self, predicate, fun):
        pass
    
    def get_rules(self):
        pass

    def get_all_rules_for_ds(self, ds_id):
        pass
    
    def get_rules_for_ds_in_project(self, ds_id, lineage_id, project_id, env):
        pass
    
    def get_datasources_in_logical(self, logical):
        pass
    
    def get_datasource(self, dsId):
        pass
    
    def get_latest_datasource_in_logical(self, logical, n=-1):
        pass
    
    def get_schema(self, schema_id):
        pass
    
    def get_latest_schema_in_datasource(self, ds):
        pass
    
    def get_latest_schema_in_logical(self, logical, n=-1):
        pass
    
    def get_latest_stats_for_ds(self, projectId, env, linId, dsId):
        pass
    
    def get_logical_ds_name_from_ds(self, dsId):
        pass

    def get_datasources(self):
        pass
    
    def get_logical_datasources(self):
        pass

    def get_total_sent_data_mb(self):
        pass

    def get_detailed_sent_data(self):
        pass


class SDK(AbstractSDK):
    def __init__(self, url, sdk_token, verify_ssl):
        self.url = url
        self.PAT = sdk_token
        self.cookie_url = self.url + '/api/auth/callback?client_name=ExternalAppTokenClient'
        self.cookie_header = {'X-External-App-Token': self.PAT}
        self.verify_ssl = verify_ssl
        self.cookie = self.get_cookie()  # FIXME: get_cookie called only once in __init__()! thus it might get expired!
        self.debug_requests = os.environ.get('KENSU_DEBUG_HTTP_REQUESTS', 'False') == 'True'
        self.is_legacy_services = None

    def is_legacy_srv(self):
        if self.is_legacy_services is None:
            from packaging import version
            self.is_legacy_services = version.parse(self.get_business_services_version()) < version.parse('11.0.0')
        return self.is_legacy_services

    def get_cookie(self):
        session = requests.Session()
        response = session.post(url=self.cookie_url, headers=self.cookie_header, verify=self.verify_ssl)
        cookie = session.cookies
        return cookie

    def requests_get_json(self, uri_suffix):
        # FIXME: proper URI concat
        # FIXME: verify if this update the cookie jar?
        # FIXME: what if cookie expired?
        uri = self.url + uri_suffix
        resp = self.debug_request(
            uri=uri,
            method='GET',
            fn=lambda: requests.get(uri, cookies=self.cookie, verify=self.verify_ssl)
        )
        if not (200 <= resp.status_code <= 299):
            msg = f"Failed to query Kensu SDK for uri={uri_suffix} status={resp.status_code}:\n{resp.text}"
            e = SdkError(msg)
            logging.warning(msg, e)
            raise SdkError(e)
        try:
            return resp.json()
        except:
            logging.warning(f"Unable to decode Kensu SDK response for uri={uri_suffix}:\n{v}", e)
            raise SdkError()

    def debug_request(self, uri, method, fn, payload=None):
        if self.debug_requests:
            logging.warning(f'performing {method} request to {uri}, payload: {payload}')
        resp = fn()
        if self.debug_requests:
            logging.warning('got response: ' + str(resp))
            logging.warning('got response text: ' + str(resp.text))
        return resp

    def requests_post_json(self, uri, payload):
        full_uri = self.url + uri
        return self.debug_request(
            uri=full_uri,
            payload=payload,
            method='POST',
            fn=lambda: requests.post(full_uri, json=payload, cookies=self.cookie, verify=self.verify_ssl)
        )

    def requests_put_json(self, uri, payload):
        full_uri = self.url + uri
        return self.debug_request(
            uri=full_uri,
            payload=payload,
            method='PUT',
            fn=lambda: requests.put(full_uri, json=payload, cookies=self.cookie, verify=self.verify_ssl)
        )

    def requests_patch_json(self, uri, payload):
        full_uri = self.url + uri
        return self.debug_request(
            uri=full_uri,
            payload=payload,
            method='PATCH',
            fn=lambda: requests.patch(full_uri, json=payload, cookies=self.cookie, verify=self.verify_ssl)
        )

    def get_lineages_in_project(self, project, process, env, code_version):
        # FIXME: this works only when explicit environment was specified (and maybe same about code version)
        # FIXME: use proper URLencode
        if self.is_legacy_srv():
            uri = "/business/api/views/v1/project-catalog/process/data-flow?projectId=%s&processId=%s&logical=true&environment=%s&codeVersionId=%s" % (project,process,env,code_version)
            return self.requests_get_json(uri)
        else:
            uri = "/business/services/views/v1/project-catalog/process/data-flow?projectId=%s&processId=%s&environment=%s&codeVersionId=%s" % (project, process, env, code_version)
            return {'data':self.requests_get_json(uri)}

    def get_business_services_version(self):
        uri = '/business/services/v1/code-version'
        return self.requests_get_json(uri)['version']

    def create_rule(self, lds_id, lineage_id=None, project_id=None, process_id=None, env_name=None, field_name=None, fun=None, context="DATA_STATS"):
        if self.is_legacy_srv():
            uri = "/business/api/v1/predicates"
        else:
            uri = "/business/services/v1/rules"
        payload = None
        if context == "DATA_STATS":
            payload = {
                "context": "DATA_STATS",
                "datasourceId": lds_id,
                "lineageId": lineage_id,
                "projectId": project_id,
                "processId": process_id,
                "environment": env_name,
                "isLogical": True,
                "fieldName": field_name,
                "functionName": fun["name"],
                "arguments": fun["arguments"]
            }
        elif context == "LOGICAL_DATA_SOURCE":
            payload = {
                "context": "LOGICAL_DATA_SOURCE",
                "datasourceId": lds_id,
                "environment": "",
                "fieldName": field_name,
                "functionName": fun["name"],
                "arguments": fun["arguments"]
            }

        if payload:
            # FIXME: verify no failure?
            return self.requests_post_json(uri, payload=payload)

    def update_rule(self, predicate, fun):
        payload = {"functionName": fun["name"],
                   "arguments": fun["arguments"]}
        if self.is_legacy_srv():
            uri = "/business/api/v1/predicates/%s" % predicate
            v = self.requests_put_json(uri, payload=payload)
        else:
            # e.g.: /business/services/v1/rules/1d7054fd-5f0c-4c71-b94f-2f0fe8deb210
            uri = f"/business/services/v1/rules/{predicate}"
            v = self.requests_patch_json(uri, payload=payload)
        return None

    @normalize_services_response
    def get_rules(self):
        # FIXME: not used?
        if self.is_legacy_srv():
            uri = "/business/api/views/v1/predicate-catalog"
        else:
            uri = "/business/services/views/v1/rules"
        return self.requests_get_json(uri)

    @normalize_services_response
    def get_rules_for_ds_in_project(self, ds_id, lineage_id, project_id, env):
        if self.is_legacy_srv():
            uri = "/business/api/v1/performance/data/%s/%s?projectId=%s&logical=true&environment=%s" % (
            ds_id, lineage_id, project_id, env)
        else:
            uri = f"/business/services/views/v2/performance/data/{ds_id}/{lineage_id}?projectId={project_id}&environment={env}"
        return self.requests_get_json(uri)

    def get_all_rules_for_ds(self, ds_id):
        if self.is_legacy_srv():
            uri = "/business/api/v1/predicates?logical_data_source_id=%s&context=LOGICAL_DATA_SOURCE" % (ds_id)
            return self.requests_get_json(uri)
        else:
            uri = "/business/services/views/v1/rules?logical_data_source_id=%s&context=LOGICAL_DATA_SOURCE" % (ds_id)
            r = self.requests_get_json(uri)
            return {'data':{'predicates':r}}

    def get_datasources_in_logical(self, logical):
        # FIXME: 404
        return self.requests_get_json("/api/services/v1/experimental/datasources/in-logical/%s" % logical)

    def get_datasource(self, dsId):
        return self.requests_get_json("/api/services/v1/resources/datasource/%s" % dsId)

    def get_latest_datasource_in_logical(self, logical, n=-1):
        js = self.get_datasources_in_logical(logical)
        sorted_js = (sorted((i for i in js), key=lambda k: k['timestamp']))

        if len(sorted_js)>=abs(n):
            uuid = sorted_js[n]["uuid"]
            ds = self.get_datasource(uuid)
            return ds
        else:
            return None

    def get_schema(self, schema_id):
        return self.requests_get_json("/api/services/v1/resources/schema/%s" % schema_id)

    def get_latest_schema_in_datasource(self, ds):
        if ds:
            schemas = ds['schemas']
            schema_uuid = (max((i for i in schemas), key=lambda k: k['timestamp']))['schemaId']
            schema = self.get_schema(schema_uuid)
            return {x["columnName"]:x["columnType"] for x in schema['schema']}
        else:
            return None

    def get_latest_schema_in_logical(self, logical, n=-1):
        ds = self.get_latest_datasource_in_logical(logical, n)
        schema = self.get_latest_schema_in_datasource(ds)
        return schema

    def get_latest_stats_for_ds(self, projectId, env, linId, dsId):
        resp_json = self.requests_get_json("/business/api/v1/performance/data/%s/%s?projectId=%s&logical=false&environment=%s" % (dsId,linId,projectId,env))
        stats_json = sorted(resp_json['data']['stats'], key=lambda k: k['timestamp'])[-1]
        return stats_json['stats']

    def get_logical_ds_name_from_ds(self, dsId):
        ds = self.requests_get_json("/business/api/v1/datasources/%s" % dsId)
        return ds["data"]["logicalDatasource"]["name"]

    def get_datasources(self):
        return self.requests_get_json("/api/services/v1/resources/datasources")

    def get_logical_datasources(self):
        return self.requests_get_json("/business/services/views/v1/logical-datasources")

    def get_total_sent_data_mb(self):
        return self.requests_get_json("/business/services/v1/ingestion-log")['entitiesSentKbTotal'] / 1000

    def get_detailed_sent_data(self):
        ingestion_log_details = self.requests_get_json("/business/services/v1/ingestion-log")['entitiesSentByToken']
        self.cookie = self.get_cookie()
        tokens = self.requests_get_json("/services/v1/preferences/tokens")
        ingestion_list = []
        for ingestion_log_detail in ingestion_log_details:
            ingestion_dict = {}
            if ingestion_log_detail['entitiesSent'] > 0:
                token = next(token for token in tokens if token['id'] == ingestion_log_detail['ingestionTokenId'])
                ingestion_dict = {
                    'week': datetime.fromtimestamp(ingestion_log_detail['ingestedAt'] / 1000).strftime('%Y/%V'),
                    'sizeMb': ingestion_log_detail['entitiesSentKbSize'] / 1000,
                    'entities': ingestion_log_detail['entitiesSent'],
                    'tokenId': token['id'],
                    'tokenDescription': token['tokenDescription'],
                    'appGroup': token['appGroupName']
                }
                ingestion_list.append(ingestion_dict)
        return ingestion_list
