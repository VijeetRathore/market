import requests
from config import TOKEN

BASE = "https://api.upstox.com/v2/market-quote/quotes"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}


def fetch_live_data(keys):
    try:
        params = {
            "instrument_key": ",".join(keys)
        }

        res = requests.get(BASE, headers=HEADERS, params=params)
        data = res.json()

        quotes = data.get("data", {})
        parsed = {}

        for key, val in quotes.items():
            ltp = val.get("last_price")
            volume = val.get("volume", 0)

            parsed[key] = {
                "ltp": ltp,
                "volume": volume
            }

        return parsed

    except Exception as e:
        print("Fetch error:", e)
        return {}