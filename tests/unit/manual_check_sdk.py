if __name__ == '__main__':
    from kensu.utils.kensu_provider import KensuProvider
    from testing_helpers import setup_logging
    setup_logging()

    ## kensu setup
    ksu = KensuProvider().initKensu(init_context=True,
                                    project_names=['manual check sdk'])
    #### end of kensu setup

    from kensu.utils.rule_engine import add_rule
    import logging

    def add_not_null_rule(
            ksu,  # type: Kensu
            lds_name,
            non_null_col,
            null_suffix='nullrows'
    ):
        try:
            from kensu.utils.rule_engine import add_rule
            #for lds_name in [cat.replace('logical::', '') for cat in ds.categories]:
            logging.info(f"Adding a Kensu rule: NOT_NULL({non_null_col}) on LDS={lds_name}")
            lds_context = "LOGICAL_DATA_SOURCE"
            add_rule(data_source=lds_name,
                     field=f'{non_null_col}.{null_suffix}',
                     type='Range',
                     parameters={'maxVal': 0},
                     context=lds_context)
            ksu.send_rules()
        except Exception as e:
            logging.error(f"Error while adding a Kensu rule  NOT_NULL({non_null_col})", e)

    add_not_null_rule(ksu,
                      lds_name='Recommendations First Outreach Table',
                      non_null_col='phone_number',
                      null_suffix='na')


