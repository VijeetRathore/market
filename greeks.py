import numpy as np
from scipy.stats import norm

def calc_greeks(S, K, T, r, sigma, option_type="CE"):
    d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)

    if option_type == "CE":
        delta = norm.cdf(d1)
        theta = (-S*norm.pdf(d1)*sigma/(2*np.sqrt(T))) - r*K*np.exp(-r*T)*norm.cdf(d2)
    else:
        delta = -norm.cdf(-d1)
        theta = (-S*norm.pdf(d1)*sigma/(2*np.sqrt(T))) + r*K*np.exp(-r*T)*norm.cdf(-d2)

    gamma = norm.pdf(d1)/(S*sigma*np.sqrt(T))
    vega = S*norm.pdf(d1)*np.sqrt(T)

    return delta, gamma, theta, vega


def implied_volatility(price, S, K, T, r, option_type):
    sigma = 0.3
    for _ in range(10):
        d1 = (np.log(S/K)+(r+sigma**2/2)*T)/(sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)

        if option_type == "CE":
            model_price = S*norm.cdf(d1)-K*np.exp(-r*T)*norm.cdf(d2)
        else:
            model_price = K*np.exp(-r*T)*norm.cdf(-d2)-S*norm.cdf(-d1)

        vega = S*norm.pdf(d1)*np.sqrt(T)
        sigma -= (model_price-price)/vega

    return sigma