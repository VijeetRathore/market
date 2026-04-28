# debug_chain.py
import requests

TOKEN = "YOUR_TOKEN_HERE"  # apna token daal

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Test different key formats
keys_to_try = [
    "NSE_INDEX|Nifty Bank",
    "NSE_INDEX|BANKNIFTY",
    "NSE_INDEX|26000",  # some APIs use instrument ID
]

for key in keys_to_try:
    url = "https://api.upstox.com/v2/option/chain"
    params = {"instrument_key": key, "expiry_date": "2026-04-24"}
    res = requests.get(url, headers=HEADERS, params=params, timeout=10)
    print(f"\nKey: {key}")
    print(f"Status: {res.status_code}")
    print(f"Response: {res.json()}")