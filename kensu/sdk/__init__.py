import requests

from abc import ABC, abstractmethod

# we could reuse the reporters instead
class AbstractSDK(ABC):
    @abstractmethod
    def get_cookie():
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
    def get_rules_for_ds(self, ds_id, lineage_id, project_id, env):
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
    def get_latest_schema_in_logical(self, url, logical,n=-1):
        pass

    @abstractmethod
    def get_latest_stats_for_ds(self, projectId, env, linId, dsId):
        pass

    @abstractmethod
    def get_logical_ds_name_from_ds(self, dsId):
        pass



class DoNothingSDK(ABC):
    def __init__(self):
        pass

    def get_cookie():
        pass
    
    def get_lineages_in_project(self, project, process, env, code_version):
        pass
    
    def create_rule(self, lds_id, lineage_id, project_id, process_id, env_name, field_name, fun):
        pass
    
    def update_rule(self, predicate, fun):
        pass
    
    def get_rules(self):
        pass
    
    def get_rules_for_ds(self, ds_id, lineage_id, project_id, env):
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
    
    def get_latest_schema_in_logical(url, logical, n=-1):
        pass
    
    def get_latest_stats_for_ds(self, projectId, env, linId, dsId):
        pass
    
    def get_logical_ds_name_from_ds(self, dsId):
        pass


class SDK(AbstractSDK):
    def __init__(self, url, sdk_token):
        self.url = url
        self.PAT = sdk_token
        self.cookie_url = self.url + '/api/auth/callback?client_name=ExternalAppTokenClient'
        self.cookie_header = {'X-External-App-Token': self.PAT}
        self.cookie = self.get_cookie() 

    def get_cookie(self):
        session = requests.Session()
        response = session.post(url=self.cookie_url, headers=self.cookie_header, verify=False)
        cookie = session.cookies
        return cookie

    def get_lineages_in_project(self, project, process, env, code_version):
        url_pref = "/business/api/views/v1/project-catalog/process/data-flow?projectId=%s&processId=%s&logical=true&environment=%s&codeVersionId=%s"%(project,process,env,code_version)
        v = requests.get(self.url + url_pref, cookies=self.cookie, verify=False)
        return v.json()

    def create_rule(self, lds_id, lineage_id, project_id, process_id, env_name, field_name, fun):
        url_pref = "/business/api/v1/predicates"
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
        v = requests.post(self.url + url_pref, json=payload, cookies=self.cookie, verify=False)
        return v.json()

    def update_rule(self, predicate, fun):
        url_pref = "/business/api/v1/predicates/%s"%predicate

        payload = {"functionName": fun["name"],
                    "arguments": fun["arguments"]}

        v = requests.put(self.url + url_pref, json=payload, cookies=self.cookie, verify=False)
        return v.json()

    def get_rules(self):
        url_pref = "/business/api/views/v1/predicate-catalog"
        v = requests.get(self.url + url_pref, cookies=self.cookie, verify=False)
        return v.json()

    def get_rules_for_ds(self, ds_id, lineage_id, project_id, env):
        url_pref = "/business/api/v1/performance/data/%s/%s?projectId=%s&logical=true&environment=%s"%(ds_id,lineage_id,project_id,env)
        v = requests.get(self.url + url_pref, cookies=self.cookie, verify=False)
        return v.json()

    def get_datasources_in_logical(self, logical):
        v = requests.get(self.url + "/api/services/v1/experimental/datasources/in-logical/%s" % logical, cookies=self.cookie, verify=False)
        return v.json()

    def get_datasource(self, dsId):
        v = requests.get(self.url + "/api/services/v1/resources/datasource/%s" % dsId, cookies=self.cookie, verify=False)
        return v.json()

    def get_latest_datasource_in_logical(self, logical, n=-1):
        js = get_datasources_in_logical(self, logical)
        sorted_js = (sorted((i for i in js), key=lambda k: k['timestamp']))

        if len(sorted_js)>=abs(n):
            uuid = sorted_js[n]["uuid"]
            ds = get_datasource(url, self.cookie, uuid)
            return ds
        else:
            return None

    def get_schema(self, schema_id):
        v = requests.get(url+"/api/services/v1/resources/schema/%s" %schema_id, cookies=self.cookie, verify=False)
        return v.json()

    def get_latest_schema_in_datasource(self, ds):
        if ds:
            schemas = ds['schemas']
            schema_uuid = (max((i for i in schemas), key=lambda k: k['timestamp']))['schemaId']
            schema = get_schema(self, schema_uuid)
            return {x["columnName"]:x["columnType"] for x in schema['schema']}
        else:
            return None

    def get_latest_schema_in_logical(self, url, logical,n=-1):
        ds = get_latest_datasource_in_logical(url, logical, n)
        schema = get_latest_schema_in_datasource(url, ds)
        return schema

    def get_latest_stats_for_ds(self, projectId, env, linId, dsId):
        uri = self.url + "/business/api/v1/performance/data/%s/%s?projectId=%s&logical=false&environment=%s"%(dsId,linId,projectId,env)
        v = requests.get(uri, cookies=self.cookie, verify=False)
        stats_json = sorted(v.json()['data']['stats'],key=lambda k: k['timestamp'])[-1]
        return stats_json['stats']

    def get_logical_ds_name_from_ds(self, dsId):
        uri = self.url + "/business/api/v1/datasources/%s"%dsId
        v = requests.get(uri, cookies=self.cookie, verify=False)
        ds = v.json()
        return ds["data"]["logicalDatasource"]["name"]
