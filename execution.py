import requests
from config import TOKEN

def place_order(signal, symbol, qty):
    url = "https://api.upstox.com/v2/order/place"

    payload = {
        "quantity": qty,
        "product": "MIS",
        "validity": "DAY",
        "instrument_token": symbol,
        "order_type": "MARKET",
        "transaction_type": "BUY" if "CALL" in signal else "SELL"
    }

    headers = {"Authorization": f"Bearer {TOKEN}"}

    res = requests.post(url, json=payload, headers=headers)
    return res.json()