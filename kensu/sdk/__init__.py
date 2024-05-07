import logging
import os
from datetime import datetime
import re

import requests

from abc import ABC, abstractmethod

# we could reuse the reporters instead
from kensu.utils.exceptions import SdkError


class AbstractSDK(ABC):

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
    def get_logical_datasources(self):
        pass

    @abstractmethod
    def get_total_sent_data_mb(self):
        pass

    @abstractmethod
    def get_detailed_sent_data(self):
        pass

    @abstractmethod
    def disable_all_metrics(self, ds_reg_ex):
        pass

    @abstractmethod
    def set_metrics(self, ds_reg_ex, attributes_reg_ex, whitelist):
        pass

    @abstractmethod
    def get_tickets(self, status):
        pass

    @abstractmethod
    def set_ticket_status(self, id):
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

    def get_logical_datasources(self):
        pass

    def get_total_sent_data_mb(self):
        pass

    def get_detailed_sent_data(self):
        pass

    def disable_all_metrics(self, ds_reg_ex):
        pass

    def get_tickets(self, status):
        pass

    def set_ticket_status(self, id):
        pass

    def set_metrics(self, ds_reg_ex, attributes_reg_ex, whitelist):
        pass

class SDK(AbstractSDK):
    def __init__(self, url, sdk_token, verify_ssl):
        self.url = url
        self.PAT = sdk_token
        self.verify_ssl = verify_ssl
        self.debug_requests = os.environ.get('KENSU_DEBUG_HTTP_REQUESTS', 'False') == 'True'

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.PAT}"}

    def requests_get_json(self, uri_suffix):
        # FIXME: proper URI concat
        uri = self.url + uri_suffix
        resp = self.debug_request(
            uri=uri,
            method='GET',
            fn=lambda: requests.get(uri, headers=self._auth_headers(), verify=self.verify_ssl)
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
            fn=lambda: requests.post(full_uri, headers=self._auth_headers(), json=payload, verify=self.verify_ssl)
        )

    def requests_put_json(self, uri, payload):
        full_uri = self.url + uri
        return self.debug_request(
            uri=full_uri,
            payload=payload,
            method='PUT',
            fn=lambda: requests.put(full_uri, headers=self._auth_headers(), json=payload, verify=self.verify_ssl)
        )

    def requests_patch_json(self, uri, payload):
        full_uri = self.url + uri
        return self.debug_request(
            uri=full_uri,
            payload=payload,
            method='PATCH',
            fn=lambda: requests.patch(full_uri, headers=self._auth_headers(), json=payload, verify=self.verify_ssl)
        )

    def get_lineages_in_project(self, project, process, env, code_version):
        # FIXME: this works only when explicit environment was specified (and maybe same about code version)
        # FIXME: use proper URLencode
        uri = "/business/services/views/v1/project-catalog/process/data-flow?projectId=%s&processId=%s&environment=%s&codeVersionId=%s" % (
            project, process, env, code_version)
        return {'data': self.requests_get_json(uri)}

    def get_business_services_version(self):
        uri = '/business/services/v1/code-version'
        return self.requests_get_json(uri)['version']

    def create_rule(self, lds_id, lineage_id=None, project_id=None, process_id=None, env_name=None, field_name=None,
                    fun=None, context="DATA_STATS"):
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
        # e.g.: /business/services/v1/rules/1d7054fd-5f0c-4c71-b94f-2f0fe8deb210
        uri = f"/business/services/v1/rules/{predicate}"
        v = self.requests_patch_json(uri, payload=payload)
        return None

    @normalize_services_response
    def get_rules(self):
        # FIXME: not used?
        uri = "/business/services/views/v1/rules"
        return self.requests_get_json(uri)

    @normalize_services_response
    def get_rules_for_ds_in_project(self, ds_id, lineage_id, project_id, env):
        uri = f"/business/services/views/v2/performance/data/{ds_id}/{lineage_id}?projectId={project_id}&environment={env}"
        return self.requests_get_json(uri)

    def get_all_rules_for_ds(self, ds_id):
        uri = "/business/services/views/v1/rules?logical_data_source_id=%s&context=LOGICAL_DATA_SOURCE" % (ds_id)
        r = self.requests_get_json(uri)
        return {'data': {'predicates': r}}

    def get_logical_datasources(self):
        logical_data_sources = {'data': []}
        limit = 500
        offset = 0

        ds = {'data': [None]} 
    
        while ds['data']:
            try:
                ds = self.requests_get_json(f"/business/services/views/v1/logical-datasources?offset={offset}&limit={limit}")
                logical_data_sources['data'].extend(ds['data'])
                offset += limit
                
            except Exception as e:
                print(f"Error fetching data: {e}")
                break # Exit loop on error
   
        return logical_data_sources

    def get_total_sent_data_mb(self):
        return self.requests_get_json("/business/services/v1/ingestion-log")['entitiesSentKbTotal'] / 1000

    def get_detailed_sent_data(self):
        ingestion_log_details = self.requests_get_json("/business/services/v1/ingestion-log")['entitiesSentByToken']
        tokens = self.requests_get_json("/business/services/v1/tokens/app-groups")
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

    def disable_all_metrics(self, ds_reg_ex):
        dss = self.get_logical_datasources()
        for ds in dss:
            x = re.search(ds_reg_ex, ds['name'])  # check if ds name match with the regular exp
            if x:
                apps = self.requests_get_json(  # get list of all applications involved
                    "/business/services/views/v2/performance/stats/attributes?logicalDataSourceId=%s" % ds['id'])[
                    'applications']
                for app in apps:
                    logging.info("Disable metrics for " + ds['name'] + " and application " + app['name'])
                    self.requests_patch_json(
                        "/business/services/views/v1/logical-datasources/" + ds['id'] + "/configuration/processes/" +
                        app['id'] + "/metrics",
                        {"isMetricsConfigurationEnabled": True, "activeMetrics": [], "circuitBreakerRuleIds": []})

    def set_metrics(self, ds_reg_ex, attributes_reg_ex, whitelist=True):
        dss = self.get_logical_datasources()
        for ds in dss:
            x = re.search(ds_reg_ex, ds['name'])  # check if ds name match with the regular exp
            if x:
                apps = self.requests_get_json(  # get list of all applications involved
                    "/business/services/views/v2/performance/stats/attributes?logicalDataSourceId=%s" % ds['id'])[
                    'applications']
                schema = self.requests_get_json(  # get list of all the possible metrics
                    "/business/services/views/v1/logical-datasources/%s/schemas" % ds['id'])
                attributes = []
                for field in schema:
                    attributes.append(field['columnName'] + ".nullrows")
                    attributes.append(field['columnName'] + ".nrows")
                    if field['metricType'] == "NUMERIC":
                        attributes.append(field['columnName'] + ".min")
                        attributes.append(field['columnName'] + ".max")
                        attributes.append(field['columnName'] + ".mean")
                        attributes.append(field['columnName'] + ".stddev")
                    if field['metricType'] == "TIMESTAMP":
                        attributes.append(field['columnName'] + ".first")
                        attributes.append(field['columnName'] + ".last")
                filter_attributes = re.compile(attributes_reg_ex)
                if whitelist:  # whitelisting
                    attributes = list(filter(filter_attributes.search, attributes))
                else:  # blacklisting
                    attributes = list(filter(lambda x: not filter_attributes.search(x), attributes))
                attributes.append('nrows')
                for app in apps:
                    logging.info("Enable specified metrics for " + ds['name'] + " and application " + app['name'])
                    # CB rules are preserved
                    payload = {"isMetricsConfigurationEnabled": True, "activeMetrics": attributes}
                    self.requests_patch_json(
                        "/business/services/views/v1/logical-datasources/" + ds['id'] + "/configuration/processes/" +
                        app['id'] + "/metrics", payload)

    def get_tickets(self, status='OPEN'):
        limit = 20
        payload = {
            "limit": limit,
            "status": status,
            "sortBy": "CREATION_TIMESTAMP",
            "order": "DESC",
            "offset": 0
        }
        result = self.requests_post_json("/business/services/views/v1/tickets", payload=payload)
        tickets = result.json()['data']
        pointer = result.json()['pagination']
        while pointer['hasNext']:
            payload['offset'] = payload['offset'] + limit
            result = self.requests_post_json("/business/services/views/v1/tickets", payload=payload)
            tickets.extend(result.json()['data'])
            pointer = result.json()['pagination']
        return tickets

    def set_ticket_status(self, id):
        payload = {
            "resolution":"Resolved","status":"CLOSED","ticketIds":[id]
        }
        return self.requests_put_json("/business/services/views/v1/tickets/status", payload=payload)
