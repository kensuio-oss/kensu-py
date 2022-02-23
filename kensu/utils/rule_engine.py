from kensu.utils.kensu_provider import KensuProvider
import warnings


def add_rule(data_source, field, type, parameters,context="DATA_STATS"):
    k = KensuProvider().instance()
    k.rules.append({data_source:
                        {'field': field,
                         'fun': {"name": type, "arguments": parameters},
                         'context':context
                         }})


def add_min_max(data_source, field, min = None, max = None, context="DATA_STATS"):
    parameters = {}
    if min is not None:
        parameters["minVal"] = min
    if max is not None:
        parameters["maxVal"] = max
    add_rule(data_source,field,type='Range',parameters=parameters,context=context)


def add_missing_value_rules(data_source, data_frame=None, cols=None, context="DATA_STATS"):
    if cols is None:
        cols = data_frame.columns
    for col in cols:
        field = col+'.nullrows'
        add_rule(data_source, field, type='Range', parameters={'maxVal':0}, context=context)


def add_frequency_rule(data_source, hours=None, days=None, weeks=None, months=None):
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
    else:
        print("add_frequency_rule failed: no time unit specified")
        return None

    add_rule(data_source,
             field=None,
             type='Frequency',
             parameters={'timeLapse': timeLapse,'timeLapseUnit':timeLapseUnit})


#TODO Variabilty over time
def add_variability_rule(data_source, field, variation_in_percent, hours = None, days = None, weeks = None, months = None,context = "DATA_STATS"):
    parameters = {}
    parameters['variation'] = variation_in_percent

    add_rule(data_source,field=field,
             type='Variability',
             parameters=parameters,context=context)


def add_variability_constraint_data_source(data_source, field, variation_in_percent, hours = None, days = None, weeks = None, months = None):
    context = "LOGICAL_DATA_SOURCE"
    return add_variability_rule(data_source, field, variation_in_percent, hours, days, weeks, months,context)


def check_format_consistency(data_source):
    k_sdk = KensuProvider().instance().sdk
    checked_format = k_sdk.get_latest_datasource_in_logical(data_source)['format']
    previous_ds = k_sdk.get_latest_datasource_in_logical(data_source, n=-2)

    if checked_format and previous_ds:
        previous_format = previous_ds['format']
        bool = checked_format == previous_format
        if bool:
            pass
        else:
            print("The format of the datasource {} is not consistent, expected {}, got {}".format(data_source,previous_format, checked_format))


def check_schema_consistency(data_source):
    k_sdk = KensuProvider().instance().sdk
    checked_schema = k_sdk.get_latest_schema_in_logical(data_source, n=-1)
    previous_schema = k_sdk.get_latest_schema_in_logical(data_source, n=-2)

    if checked_schema and previous_schema:
        # Check of field changes
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
                print("The following field in {} has a wrong type: {} Expected {}, got {}".format(data_source,y,previous_schema[y],checked_schema[y]))


# TODO WIP check nrows
def check_nrows_consistency(how = "minimum"):
    k = KensuProvider().instance()
    k.check_rules.append({"nrows_consistency":how})


def create_kensu_nrows_consistency(how):
    k = KensuProvider().instance()
    for lineage in k.lineage_and_ds:

        inputs_nrows= [{k.logical_name_by_guid[schema]: k.schema_stats[schema]['nrows']}
                        for schema in k.lineage_and_ds[lineage]['from_schema_ref']
                        if 'nrows' in k.schema_stats[schema]]

        values = []
        for dic in inputs_nrows:
            for key in dic:
                values.append(dic[key])

        output_name = k.logical_name_by_guid[list(k.lineage_and_ds[lineage]['to_schema_ref'])[0]]
        checked_rules = {output_name : []}
        if how in ['minimum','maximum']:
            if how == "minimum":
                min_value = min(values)
            elif how == "maximum":
                min_value = max(values)
            ds_in_candidates = []
            for val in inputs_nrows:
                key = list(val.keys())[0]
                if val[key] == min_value:
                    ds_in_candidates.append(key)
            for ds in ds_in_candidates:
                field = 'delta.nrows_'+ds.replace('.','_')+'.abs'
                add_min_max(output_name, field, max = 0)
                checked_rules[output_name].append({field:{"output_nrows" : (k.schema_stats[list(k.lineage_and_ds[lineage]['to_schema_ref'])[0]])['nrows'], "input_nrows" : min_value}})
            k.check_rules.append({'check_nrows_consistency':checked_rules})



#TODO Support other how types:::

        #     if output_nrows == min_value:
        #         None
        #     elif output_nrows < min_value:
        #         percent = (output_nrows / min_value) * 100
        #         percent = round(percent,2)
        #         print("{} has less rows than expected: {} out of a maximum of {} - {}%".format(output_name,output_nrows,min_value,percent))
        # elif how == "maximum":
        #     max_value = max(values)
        #     if output_nrows == max_value:
        #         None
        #     elif output_nrows < max_value:
        #         percent = (output_nrows / max_value) * 100
        #         percent = round(percent, 2)
        #         print(
        #             "{} has less rows than expected: {} out of a maximum of {} - {}%".format(output_name, output_nrows,
        #                                                                                      max_value, percent))
        # else:
        #     limiting_ds = how
        #     if limiting_ds in inputs_nrows:
        #         limiting_value = inputs_nrows[limiting_ds]
        #         if output_nrows == limiting_value:
        #             None
        #         elif output_nrows < limiting_value:
        #             percent = (output_nrows / limiting_value) * 100
        #             percent = round(percent, 2)
        #             print(
        #                 "{} has less rows than expected: {} out of a maximum of {} - {}%".format(output_name,
        #                                                                                          output_nrows,
        #                                                                                          limiting_value, percent))
        #
        #
