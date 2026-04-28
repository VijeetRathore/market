# check_strikes.py
import requests
import gzip
from datetime import datetime, timedelta
from config import TOKEN

BASE = "https://api.upstox.com/v2"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

DUMP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/csv,application/octet-stream,*/*",
    "Authorization": f"Bearer {TOKEN}",
}

def get_banknifty_ltp():
    url = f"{BASE}/market-quote/ltp"
    params = {"instrument_key": "NSE_INDEX|Nifty Bank"}
    res = requests.get(url, headers=HEADERS, params=params, timeout=10)
    data = res.json()
    try:
        ltp = data["data"]["NSE_INDEX:Nifty Bank"]["last_price"]
        return ltp
    except Exception:
        print("LTP fetch failed:", data)
        return None

def get_strikes_from_csv():
    url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz"
    res = requests.get(url, headers=DUMP_HEADERS, timeout=20)
    if res.status_code != 200:
        print(f"CSV fetch failed: {res.status_code}")
        return []

    csv_text = gzip.decompress(res.content).decode("utf-8")
    lines = csv_text.splitlines()

    raw_header = lines[0].strip().lstrip("\ufeff")
    header = [h.strip().strip('"').strip("'").lower() for h in raw_header.split(",")]
    col = {name: i for i, name in enumerate(header)}

    print(f"Columns: {list(col.keys())}")

    key_col    = col["instrument_key"] if "instrument_key" in col else None
    name_col   = col["name"] if "name" in col else col.get("tradingsymbol")
    expiry_col = col["expiry"] if "expiry" in col else col.get("expiry_date")
    type_col   = col["instrument_type"] if "instrument_type" in col else None
    strike_col = col["strike"] if "strike" in col else None
    opttype_col = col["option_type"] if "option_type" in col else None

    if strike_col is None:
        print("No strike column found!")
        return []

    today = datetime.now().date()
    results = []

    for line in lines[1:]:
        parts = [p.strip().strip('"').strip("'") for p in line.split(",")]
        try:
            name      = parts[name_col] if name_col is not None else ""
            inst_type = parts[type_col] if type_col is not None else ""
            expiry_str = parts[expiry_col] if expiry_col is not None else ""
            inst_key  = parts[key_col] if key_col is not None else ""
            strike_str = parts[strike_col]
            opt_type  = parts[opttype_col] if opttype_col is not None else ""

            if inst_type not in ("OPTIDX", "OPTSTK"):
                continue
            if "BANKNIFTY" not in name.upper():
                continue
            if not expiry_str:
                continue

            exp_date = datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
            if not (0 <= (exp_date - today).days <= 14):
                continue

            strike = float(strike_str) if strike_str else 0

            results.append({
                "key": inst_key,
                "strike": int(strike),
                "type": opt_type,
                "expiry": expiry_str[:10],
            })
        except Exception:
            continue

    return results

def main():
    print("Fetching BankNifty LTP...")
    ltp = get_banknifty_ltp()

    if ltp:
        print(f"BankNifty Current Price: {ltp}")
        atm = round(ltp / 100) * 100
        print(f"ATM Strike (approx):      {atm}\n")
    else:
        atm = None

    print("Fetching strikes from CSV...")
    strikes = get_strikes_from_csv()

    if not strikes:
        print("No strikes found!")
        return

    unique_strikes = sorted(set(s["strike"] for s in strikes))
    print(f"\nTotal near-expiry BANKNIFTY strikes: {len(unique_strikes)}")
    print(f"Strike range: {unique_strikes[0]} → {unique_strikes[-1]}")
    print(f"All strikes: {unique_strikes}")

    if atm:
        above = [s for s in unique_strikes if s > atm]
        below = [s for s in unique_strikes if s < atm]
        at    = [s for s in unique_strikes if s == atm]

        print(f"\nATM ({atm}):        {'✅ PRESENT' if at else '⚠️  NOT present (nearest will be used)'}")
        print(f"Strikes above ATM: {len(above)}  → {above[:10]}")
        print(f"Strikes below ATM: {len(below)}  → {below[-10:]}")

        atm_plus5  = [s for s in above if s <= atm + 500]
        atm_minus5 = [s for s in below if s >= atm - 500]
        print(f"\nATM +5 zone (±500pts): {atm_plus5}")
        print(f"ATM -5 zone (±500pts): {atm_minus5}")

        if len(atm_plus5) >= 5 and len(atm_minus5) >= 5:
            print("\n✅ Enough strikes — ATM skew + OI momentum logic POSSIBLE")
        else:
            print(f"\n⚠️  Only {len(atm_plus5)} above, {len(atm_minus5)} below — need 5 on each side")

        # Show what keys would be subscribed for ATM zone
        atm_zone_keys = [
            s["key"] for s in strikes
            if abs(s["strike"] - atm) <= 500
        ]
        print(f"\nKeys in ATM ±500pt zone: {len(atm_zone_keys)}")
        print("Sample:", atm_zone_keys[:6])

if __name__ == "__main__":
    main()