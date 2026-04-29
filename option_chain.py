import requests
import gzip
from datetime import datetime, timedelta
from config import TOKEN
from live_data import fetch_banknifty_spot


BASE = "https://api.upstox.com/v2"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

BANKNIFTY_KEYS_TO_TRY = [
    "NSE_INDEX|Nifty Bank",
    "NSE_INDEX|BANKNIFTY",
]


def _safe_json(res):
    try:
        return res.json()
    except Exception:
        return {"status": "error", "raw": res.text}


def _next_wednesdays(n=6):
    today = datetime.now().date()
    out = []
    d = today
    while len(out) < n:
        if d.weekday() == 2 and d >= today:
            out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


# ---------- Method A: Official Option Chain API ----------

def _try_chain_with_key(instrument_key, expiry):
    url = f"{BASE}/option/chain"
    params = {"instrument_key": instrument_key, "expiry_date": expiry}
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=10)
        data = _safe_json(res)
        if data.get("status") == "success" and data.get("data"):
            return data["data"]
    except Exception as e:
        print(f"  Exception {instrument_key}/{expiry}: {e}")
    return None


def try_option_chain_keys():
    expiries = _next_wednesdays(6)
    print(f"Trying expiries: {expiries}")
    for expiry in expiries:
        for inst_key in BANKNIFTY_KEYS_TO_TRY:
            print(f"Trying: {inst_key} | {expiry}")
            rows = _try_chain_with_key(inst_key, expiry)
            if rows:
                all_keys = []
                for row in rows:
                    ce = row.get("call_options", {}).get("instrument_key")
                    pe = row.get("put_options", {}).get("instrument_key")
                    if ce:
                        all_keys.append(ce)
                    if pe:
                        all_keys.append(pe)
                if all_keys:
                    print(f"Chain API success: {len(all_keys)} keys")
                    return all_keys
    return []


# ---------- Method B: Upstox v2 instruments API ----------

def try_instrument_search():
    # correct upstox v2 instrument list endpoint
    urls_to_try = [
        f"{BASE}/instruments",
        f"{BASE}/instruments/search?query=BANKNIFTY&exchange=NSE_FO",
        "https://api.upstox.com/v2/instruments/NSE_FO",
    ]
    for url in urls_to_try:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            print(f"Instrument search {url.split('upstox.com')[-1]}: {res.status_code}")
            if res.status_code != 200:
                continue
            data = _safe_json(res)
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("data", [])
            if not items:
                continue
            today = datetime.now().date()
            keys = []
            for item in items:
                key = item.get("instrument_key") or item.get("key")
                name = str(item.get("name", "") or item.get("trading_symbol", ""))
                inst_type = item.get("instrument_type", "")
                expiry_str = item.get("expiry", "")
                if "BANKNIFTY" not in name.upper():
                    continue
                if inst_type not in ("OPTIDX", "OPTSTK", "OPT"):
                    continue
                if not key or not expiry_str:
                    continue
                try:
                    exp_date = datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
                    if 0 <= (exp_date - today).days <= 14:
                        keys.append(key)
                except Exception:
                    continue
            if keys:
                print(f"Instrument search success: {len(keys)} keys")
                return keys
        except Exception as e:
            print(f"  {e}")
    return []


# ---------- Method C: CSV Dump ----------

DUMP_URLS = [
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.csv.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.csv",
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv",
]

DUMP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/csv,application/octet-stream,*/*",
    "Authorization": f"Bearer {TOKEN}",
}


def fetch_instrument_dump():
    for url in DUMP_URLS:
        try:
            res = requests.get(url, headers=DUMP_HEADERS, timeout=20)
            print(f"Dump {url.split('/')[-1]}: {res.status_code}")
            if res.status_code == 200:
                if url.endswith(".gz"):
                    return gzip.decompress(res.content).decode("utf-8")
                return res.text
        except Exception as e:
            print(f"  {e}")
    return None


def parse_banknifty_keys_from_csv(csv_text):
    if not csv_text:
        return []

    lines = csv_text.splitlines()
    if not lines:
        return []

    # Strip BOM, quotes, whitespace from header
    raw_header = lines[0].strip().lstrip("\ufeff")
    header = [h.strip().strip('"').strip("'").lower() for h in raw_header.split(",")]
    col = {name: i for i, name in enumerate(header)}

    print(f"   CSV columns detected: {list(col.keys())[:12]}")

    key_col   = col["instrument_key"] if "instrument_key" in col else col.get("key")
    name_col  = col["name"] if "name" in col else (col["tradingsymbol"] if "tradingsymbol" in col else col.get("trading_symbol"))
    expiry_col = col["expiry"] if "expiry" in col else col.get("expiry_date")
    type_col  = col["instrument_type"] if "instrument_type" in col else col.get("instrumenttype")
    
    if type_col is None:
        print("   Cannot find instrument type column")
        return []

    if key_col is None or name_col is None:
        print(f"   Cannot find required columns in CSV")
        return []

    today = datetime.now().date()
    keys = []

    for line in lines[1:]:
        # Also strip quotes from each cell
        parts = [p.strip().strip('"').strip("'") for p in line.split(",")]
        try:
            inst_key   = parts[key_col]   if key_col is not None else ""
            name       = parts[name_col]  if name_col is not None else ""
            inst_type  = parts[type_col]  if type_col is not None else ""
            expiry_str = parts[expiry_col] if expiry_col is not None else ""
            
            tradingsymbol = (
                parts[col["tradingsymbol"]]
                if "tradingsymbol" in col and len(parts) > col["tradingsymbol"]
                else ""
            )
            if inst_type not in ("OPTIDX", "OPTSTK", "OPT"):
                continue

            search_text = f"{name} {tradingsymbol}".upper()
            if "BANKNIFTY" not in search_text:
                continue   
            

            if expiry_str:
                exp_date = datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
                if not (0 <= (exp_date - today).days <= 14):
                    continue
            if inst_key:
                keys.append(inst_key)
        except Exception:
            continue

    print(f"Dump parse: {len(keys)} near-expiry BANKNIFTY keys")
    return keys

def try_instrument_dump():
    csv_text = fetch_instrument_dump()
    if not csv_text:
        return []
    return parse_banknifty_keys_from_csv(csv_text)

def build_meta_from_csv(csv_text, keys):
    if not csv_text:
        return {}

    lines = csv_text.splitlines()
    raw_header = lines[0].strip().lstrip("\ufeff")

    header = [h.strip().strip('"').strip("'").lower() for h in raw_header.split(",")]
    col = {name: i for i, name in enumerate(header)}

    key_col = col.get("instrument_key")
    strike_col = col.get("strike")
    opt_col = col.get("option_type")
    symbol_col = col.get("tradingsymbol")

    if None in (key_col, strike_col, opt_col, symbol_col):
        print("❌ Required columns not found in CSV")
        return {}

    meta = {}

    for line in lines[1:]:
        parts = [p.strip().strip('"').strip("'") for p in line.split(",")]

        try:
            instrument_key = parts[key_col]
            tradingsymbol = parts[symbol_col]
            live_key = f"NSE_FO:{tradingsymbol}"

            if instrument_key not in keys and live_key not in keys:
                continue

            strike = float(parts[strike_col])
            opt_type = parts[opt_col].upper()

            if opt_type not in ("CE", "PE"):
                continue

            meta[live_key] = {
                "instrument_key": instrument_key,
                "tradingsymbol": tradingsymbol,
                "strike": strike,
                "type": opt_type
            }

        except Exception:
            continue

    return meta

# ---------- MAIN ----------
def get_option_chain_keys():
    print("Fetching BANKNIFTY option instruments from CSV dump...")

    csv_text = fetch_instrument_dump()
    if not csv_text:
        print("❌ Failed to fetch instrument dump")
        return []

    all_keys = parse_banknifty_keys_from_csv(csv_text)
    if not all_keys:
        print("❌ No BANKNIFTY option keys found")
        return []

    meta = build_meta_from_csv(csv_text, all_keys)

    # Live Bank Nifty spot
    spot = fetch_banknifty_spot() or 56000
    print(f"📍 Spot used for strike selection: {spot:,.2f}")

    # Select strikes near spot (±2000 points)
    filtered = [
        (k, v) for k, v in meta.items()
        if abs(v["strike"] - spot) <= 2000
    ]

    # Sort by distance from spot
    filtered = sorted(
        filtered,
        key=lambda x: abs(x[1]["strike"] - spot)
    )

    # Take nearest 40 instruments
    selected = [k for k, _ in filtered[:40]]

    ce_count = sum(1 for k in selected if meta[k]["type"] == "CE")
    pe_count = sum(1 for k in selected if meta[k]["type"] == "PE")

    print(
        f"✅ Selected: {len(selected)} keys "
        f"(CE={ce_count}, PE={pe_count})"
    )

    return selected


if __name__ == "__main__":
    result = get_option_chain_keys()
    print(f"\nFinal Keys Found: {len(result)}")
    for k in result[:5]:
        print(" ", k)