import logging

from kensu.utils.kensu_provider import KensuProvider


def add_rule(data_source, field, type, parameters,context="DATA_STATS"):
    k = KensuProvider().instance()
    k.rules.append({data_source:
                        {'field': field,
                         'fun': {"name": type, "arguments": parameters},
                         'context':context
                         }})


def add_not_null_rule(
        ksu,  # type: Kensu
        lds_name,
        non_null_col,
        null_suffix='nullrows'
):
    try:
        logging.info(f"KENSU: Adding a Kensu rule: NOT_NULL({non_null_col}) on LDS={lds_name}")
        lds_context = "LOGICAL_DATA_SOURCE"
        add_rule(data_source=lds_name,
                 field=f'{non_null_col}.{null_suffix}',
                 type='Range',
                 parameters={'maxVal': 0},
                 context=lds_context)
        ksu.send_rules()
    except Exception as e:
        logging.warning(f"Error while adding a Kensu rule  NOT_NULL({non_null_col}.{null_suffix})", e)


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
        logging.info("KENSU: add_frequency_rule failed: no time unit specified")
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
