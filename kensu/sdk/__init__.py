import requests


def get_cookie(url,PAT):
    import requests
    session = requests.Session()
    cookieurl=url + '/api/auth/callback?client_name=ExternalAppTokenClient'
    header = {'X-External-App-Token':PAT}
    response = session.post(url=cookieurl,headers=header,verify=False)
    cookie = session.cookies
    return cookie

def get_lineages_in_project(url, cookie, project,process,env,cv):
    url_pref = "/business/api/views/v1/project-catalog/process/data-flow?projectId=%s&processId=%s&logical=true&environment=%s&codeVersionId=%s"%(project,process,env,cv)
    v = requests.get(url + url_pref, cookies=cookie, verify=False)
    return v.json()

    # from exporter.k import *
    # kc = KensuHelper()
    # project_id = "k-0c316854fa0c531a708e63646c773646b86566799fb6ffd1090e0eeaea5ae15f"
    # env_name = "Production"
    # lineage_id = "k-1f34e6b71fb43a56599fd18ca69290a0585e825415c992855efa2f169f473833"
    # process_id = "k-7cf9d0f0961544ca4262f18c6b2cdf6b646803dcacc953a5cfcee0daf7bd37e9"
    # lds_id = "c59107a6-f312-4ecc-90dd-7b26b2dd7562"
    # field_name = "count"
    # fun = { "name": "Range", "arguments": { "minVal": 0, "maxVal": 1000 } }
    # kc.create_rule(lds_id, lineage_id, project_id, process_id, env_name, field_name, fun)
def create_rule(url, cookie, lds_id, lineage_id, project_id, process_id, env_name, field_name, fun):
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
    v = requests.post(url + url_pref, json=payload, cookies= cookie, verify=False)
    return v.json()

def update_rule(url, cookie, predicate, fun):

    url_pref = "/business/api/v1/predicates/%s"%predicate

    payload = {"functionName": fun["name"],
                "arguments": fun["arguments"]}

    v = requests.put(url + url_pref, json=payload, cookies= cookie, verify=False)
    return v.json()

def get_rules(url, cookie):
    url_pref = "/business/api/views/v1/predicate-catalog"
    v = requests.get(url + url_pref, cookies=cookie, verify=False)
    return v.json()

def get_rules_for_ds(url, cookie, ds_id, lineage_id, project_id, env):
    url_pref = "/business/api/v1/performance/data/%s/%s?projectId=%s&logical=true&environment=%s"%(ds_id,lineage_id,project_id,env)
    v = requests.get(url + url_pref, cookies=cookie, verify=False)
    return v.json()
