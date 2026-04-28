def position_size(capital, risk_per_trade=0.01):
    return capital * risk_per_trade

def apply_risk(price, signal):
    if signal == "BUY_CALL":
        return {"sl": price*0.9, "target": price*1.2}

    if signal == "BUY_PUT":
        return {"sl": price*0.9, "target": price*1.2}

    return {}