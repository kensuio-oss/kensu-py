import pandas_gbq as pdg
from pandas_gbq import *
from .pandas_gbq import wrap_pandas_gbq_write
to_gbq=wrap_pandas_gbq_write(pdg.to_gbq)