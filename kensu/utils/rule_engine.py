from kensu.utils.kensu_provider import KensuProvider

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
