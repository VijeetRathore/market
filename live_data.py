import requests
from config import TOKEN

BASE = "https://api.upstox.com/v2/market-quote/quotes"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}


def fetch_live_data(keys, instrument_meta=None):
    try:
        params = {
            "instrument_key": ",".join(keys)
        }

        res = requests.get(BASE, headers=HEADERS, params=params, timeout=10)
        data = res.json()

        quotes = data.get("data", {})
        parsed = {}

        # Map API instrument keys -> live symbol keys
        key_map = {}
        if instrument_meta:
            for live_key, meta in instrument_meta.items():
                key_map[meta["instrument_key"]] = live_key

        for key, val in quotes.items():
            mapped_key = key_map.get(key, key)

            market_data = val.get("market_data", {})
            option_greeks = val.get("option_greeks", {})

            parsed[mapped_key] = {
                "ltp": market_data.get("ltp", val.get("last_price", 0)),
                "volume": market_data.get("volume", val.get("volume", 0)),
                "oi": market_data.get("oi", val.get("oi", 0)),
                "delta": option_greeks.get("delta"),
                "theta": option_greeks.get("theta"),
                "gamma": option_greeks.get("gamma"),
                "vega": option_greeks.get("vega"),
            }

        return parsed

    except Exception as e:
        print("Fetch error:", e)
        return {}

def fetch_banknifty_spot():
    try:
        params = {
            "instrument_key": "NSE_INDEX|Nifty Bank"
        }

        res = requests.get(BASE, headers=HEADERS, params=params, timeout=10)
        data = res.json()

        quotes = data.get("data", {})
        if not quotes:
            return None

        # Take first available quote
        quote = next(iter(quotes.values()))
        market_data = quote.get("market_data", {})

        return (
            market_data.get("ltp")
            or quote.get("last_price")
            or quote.get("ltp")
        )

    except Exception as e:
        print("Spot fetch error:", e)
        return None
    
if __name__ == "__main__":
    spot = fetch_banknifty_spot()
    print("Bank Nifty Spot:", spot)