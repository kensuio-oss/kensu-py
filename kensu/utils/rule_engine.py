from kensu.utils.kensu_provider import KensuProvider
import warnings

def add_rule(data_source, field, type, parameters):
    k = KensuProvider().instance()
    k.rules.append({data_source:
                        {'field': field,
                         'fun': {"name": type, "arguments": parameters}
                         }})

def add_min_max(data_source, field, min = None, max = None):
    parameters = {}
    if min:
        parameters["minVal"] = min
    if max:
        parameters["maxVal"] = max
    add_rule(data_source,field,type='Range',parameters=parameters)

def add_missing_value_rules(data_source, data_frame):
    for col in data_frame.columns:
        field = col+'.nullrows'
        add_rule(data_source, field, type='Range', parameters={'maxVal':0})

def add_frequency_rule(data_source, hours = None, days = None, weeks = None, months = None):

    if hours:
        timeLapseUnit = 'Hours'
        timeLapse = hours
    elif days:
        timeLapseUnit = 'Days'
        timeLapse = days
    elif weeks:
        timeLapseUnit = 'Weeks'
        timeLapse = weeks
    elif months:
        timeLapseUnit = 'Months'
        timeLapse = months

    add_rule(data_source,field=None,
             type='Frequency',
             parameters={'timeLapse': timeLapse,'timeLapseUnit':timeLapseUnit})

def add_variability_rule(data_source, variation, hours = None, days = None, weeks = None, months = None):

    parameters = {}
    parameters['variation'] = variation

    add_rule(data_source,field=None,
             type='Variability',
             parameters=parameters)

def check_format_consistency(data_source):
    k = KensuProvider().instance()

    from kensu.sdk import get_latest_datasource_in_logical
    cookie = k.get_cookie()
    checked_format = get_latest_datasource_in_logical(k.api_url.replace("-api",""),cookie,data_source)['format']
    previous_format = get_latest_datasource_in_logical(k.api_url.replace("-api",""),cookie,data_source,n=-2)['format']

    bool = checked_format == previous_format

    if bool:
        None
    else:
        print("The format of the datasource {} is not consistent, expected {}, got {}".format(data_source,previous_format, checked_format))

def check_schema_consistency(data_source):
    from kensu.sdk import get_latest_schema_in_logical
    k = KensuProvider().instance()
    cookie = k.get_cookie()
    checked_schema = get_latest_schema_in_logical(k.api_url.replace("-api",""),cookie, data_source, n=-1)
    previous_schema = get_latest_schema_in_logical(k.api_url.replace("-api",""),cookie, data_source, n=-2)

    if checked_schema and previous_schema:
        #Check of field changes
        missing_keys = previous_schema.keys() - checked_schema.keys()
        if missing_keys:
            print("The following key(s) are missing from {} : {}".format(data_source,list(missing_keys)))

        new_keys =  checked_schema.keys() - previous_schema.keys()
        if new_keys:
            print("The following key(s) are new in {} : {}".format(data_source,list(new_keys)))

        all_changed_fields = list(missing_keys)+list(new_keys)

        type_diff = dict(set(checked_schema.items())-set(previous_schema.items()))
        for x in all_changed_fields:
            if x in type_diff:
                del type_diff[x]
        if type_diff:
            for y in type_diff.keys():
                print("The following field in {} has a wrong type: Expected {}, got {}".format(data_source,previous_schema[y],checked_schema[y]))