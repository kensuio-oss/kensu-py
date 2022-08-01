from kensu.utils.rule_engine import add_not_null_rule

if __name__ == '__main__':
    from kensu.utils.kensu_provider import KensuProvider
    from testing_helpers import setup_logging
    setup_logging()

    ## kensu setup
    ksu = KensuProvider().initKensu(init_context=True,
                                    project_names=['manual check sdk'])
    #### end of kensu setup

    add_not_null_rule(ksu,
                      lds_name='Recommendations First Outreach Table',
                      non_null_col='phone_number',
                      null_suffix='na')


