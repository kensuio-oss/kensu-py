from kensu.utils.wrappers import remove_ksu_wrappers, remove_ksu_kwargs_wrappers

from kensu.utils.kensu_provider import KensuProvider


def wrap_pandas_gbq_write(method):
    def wrapper(*args, **kwargs):
        kensu = KensuProvider().instance()

        new_args = remove_ksu_wrappers(args)
        new_kwargs = remove_ksu_kwargs_wrappers(kwargs)

        df_result = method(*new_args, **new_kwargs)
        df = args[0]  # see get_dummies definition (first arg is `data`)

        orig_ds = kensu.extractors.extract_data_source(df, kensu.default_physical_location_ref,
                                                     logical_naming=kensu.logical_naming)
        orig_sc = kensu.extractors.extract_schema(orig_ds, df)

        from google.cloud import bigquery
        client = bigquery.Client()
        df_table = client.get_table(args[1])

        result_ds = kensu.extractors.extract_data_source(df_table, kensu.default_physical_location_ref,
                                                       logical_naming=kensu.logical_naming)._report()
        result_sc = kensu.extractors.extract_schema(result_ds, df_table)._report()


        for col in df.columns:
            kensu.add_dependencies_mapping(result_sc.to_guid(), str(col), orig_sc.to_guid(), str(col), 'Write')

        kensu.real_schema_df[result_sc.to_guid()] = df
        kensu.report_with_mapping()

        return df_result

    wrapper.__doc__ = method.__doc__
    return wrapper