import os

# P.S. this file should use py3.5 syntax, no f-strings allowed

def extract_config_property(key, default, arg=None, kw=None, conf=None, tpe=None):
    """
    Looks for a property value following this precedence:
      env_var > arg > kwargs > conf > default
    The default value is used to determine the type of the conf value (it can be overridden by tpe).
    The environment variable will be looked up based on the pattern of `KSU_<upper-key>`.
    """
    env_var_key = "KSU_" + key.upper()
    if os.environ.get(env_var_key) is not None:
        env_var = os.environ.get(env_var_key)
        if tpe is not None:
            env_var = tpe(env_var)
        return env_var
    elif arg is not None:
        return arg
    elif key in kw and kw[key] is not None:
        return kw[key]
    elif key in conf and conf.get(key) is not None:
        if default is not None and tpe is None:
            tpe = type(default)
        r = conf.get(key)
        if tpe is list:
            r = r.replace(" ", "").split(",")
        elif tpe is bool:
            r = conf.getboolean(key)
        elif tpe is not None:
            r = tpe(r)
        return r
    else:
        return default


def get_conf_path(default = "conf.ini"):
    return os.environ["KSU_CONF_FILE"] if "KSU_CONF_FILE" in os.environ else default
