import urllib3
urllib3.disable_warnings()

from kensu.utils.kensu_provider import KensuProvider as K
k = K().initKensu()

import kensu.pandas as pd

stock = pd.read_csv('apple_stock.csv')

stock_renamed = stock.rename({'Adj Close':'Closing_Price'},axis=1)

stock_renamed.to_csv('copy.csv',index=False)