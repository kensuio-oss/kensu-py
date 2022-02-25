import logging

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


class SDK(AbstractSDK):
    def __init__(self, url, sdk_token, verify_ssl):
        self.url = url
        self.PAT = sdk_token
        self.cookie_url = self.url + '/api/auth/callback?client_name=ExternalAppTokenClient'
        self.cookie_header = {'X-External-App-Token': self.PAT}
        self.verify_ssl = verify_ssl
        self.cookie = self.get_cookie()  # FIXME: get_cookie called only once in __init__()! thus it might get expired!

    def get_cookie(self):
        session = requests.Session()
        response = session.post(url=self.cookie_url, headers=self.cookie_header, verify=self.verify_ssl)
        cookie = session.cookies
        return cookie

    def requests_get_json(self, uri_suffix):
        # FIXME: proper URI concat
        # FIXME: verify if this update the cookie jar?
        # FIXME: what if cookie expired?
        resp = requests.get(self.url + uri_suffix, cookies=self.cookie, verify=self.verify_ssl)
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


    def get_lineages_in_project(self, project, process, env, code_version):
        # FIXME: use proper URLencode
        uri = "/business/api/views/v1/project-catalog/process/data-flow?projectId=%s&processId=%s&logical=true&environment=%s&codeVersionId=%s" % (project,process,env,code_version)
        return self.requests_get_json(uri)

    def create_rule(self, lds_id, lineage_id=None, project_id=None, process_id=None, env_name=None, field_name=None, fun=None, context="DATA_STATS"):
        uri = "/business/api/v1/predicates"
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
            return requests.post(self.url + uri, json=payload, cookies=self.cookie, verify=self.verify_ssl).json()

    def update_rule(self, predicate, fun):
        uri = "/business/api/v1/predicates/%s" % predicate

        payload = {"functionName": fun["name"],
                   "arguments": fun["arguments"]}

        v = requests.put(self.url + uri, json=payload, cookies=self.cookie, verify=self.verify_ssl)
        return None

    def get_rules(self):
        uri = "/business/api/views/v1/predicate-catalog"
        return self.requests_get_json(uri)

    def get_rules_for_ds_in_project(self, ds_id, lineage_id, project_id, env):
        uri = "/business/api/v1/performance/data/%s/%s?projectId=%s&logical=true&environment=%s" % (ds_id,lineage_id,project_id,env)
        return self.requests_get_json(uri)

    def get_all_rules_for_ds(self,ds_id):
        uri = "/business/api/v1/predicates?logical_data_source_id=%s&context=LOGICAL_DATA_SOURCE" % (ds_id)
        return self.requests_get_json(uri)

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
