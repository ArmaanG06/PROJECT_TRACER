import numpy as np
import pandas as pd



def pair_spread(prices: pd.DataFrame, a, b, beta, alpha):

    legs = prices[[a, b]].dropna()

    log_a = np.log(legs[a])
    log_b = np.log(legs[b])

    spread = log_a - alpha - beta * log_b 
    return spread