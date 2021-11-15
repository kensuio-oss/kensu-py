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


