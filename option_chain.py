import requests
import gzip
import re
from datetime import datetime, timedelta
from config import TOKEN

BASE = "https://api.upstox.com/v2"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

BANKNIFTY_KEYS_TO_TRY = [
    "NSE_INDEX|Nifty Bank",
    "NSE_INDEX|BANKNIFTY",
]

DUMP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/csv,application/octet-stream,*/*",
    "Authorization": f"Bearer {TOKEN}",
}

DUMP_URLS = [
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.csv.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE_FO.csv",
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv",
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


def get_banknifty_ltp():
    try:
        url = f"{BASE}/market-quote/ltp"
        params = {"instrument_key": "NSE_INDEX|Nifty Bank"}
        res = requests.get(url, headers=HEADERS, params=params, timeout=10)
        data = res.json()
        ltp = data["data"]["NSE_INDEX:Nifty Bank"]["last_price"]
        return float(ltp)
    except Exception as e:
        print(f"LTP fetch failed: {e}")
        return None


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
    for expiry in expiries:
        for inst_key in BANKNIFTY_KEYS_TO_TRY:
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
                    return all_keys
    return []


# ---------- Method B: Instrument Search ----------

def try_instrument_search():
    urls_to_try = [
        f"{BASE}/instruments",
        f"{BASE}/instruments/search?query=BANKNIFTY&exchange=NSE_FO",
        f"{BASE}/instruments/NSE_FO",
    ]
    for url in urls_to_try:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code != 200:
                continue
            data = _safe_json(res)
            items = data if isinstance(data, list) else data.get("data", [])
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
                return keys
        except Exception:
            continue
    return []


# ---------- Method C: CSV Dump ----------

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


def parse_csv(csv_text, ltp=None, atm_range=1500):
    """
    Returns (keys list, strike_map dict)
    strike_map: {instrument_key: {"strike": int, "option_type": "CE"/"PE"}}
    """
    if not csv_text:
        return [], {}

    lines = csv_text.splitlines()
    if not lines:
        return [], {}

    raw_header = lines[0].strip().lstrip("\ufeff")
    header = [h.strip().strip('"').strip("'").lower() for h in raw_header.split(",")]
    col = {name: i for i, name in enumerate(header)}

    key_col     = col["instrument_key"] if "instrument_key" in col else None
    name_col    = col["name"] if "name" in col else (col["tradingsymbol"] if "tradingsymbol" in col else None)
    ts_col      = col["tradingsymbol"] if "tradingsymbol" in col else None
    expiry_col  = col["expiry"] if "expiry" in col else col.get("expiry_date")
    type_col    = col["instrument_type"] if "instrument_type" in col else None
    strike_col  = col["strike"] if "strike" in col else None
    opttype_col = col["option_type"] if "option_type" in col else None

    if key_col is None or name_col is None:
        print(f"  Cannot find required columns")
        return [], {}

    today = datetime.now().date()
    atm = round(ltp / 100) * 100 if ltp else None
    keys = []
    strike_map = {}

    for line in lines[1:]:
        parts = [p.strip().strip('"').strip("'") for p in line.split(",")]
        try:
            inst_key   = parts[key_col]
            name       = parts[name_col] if name_col is not None else ""
            inst_type  = parts[type_col] if type_col is not None else ""
            expiry_str = parts[expiry_col] if expiry_col is not None else ""
            strike_str = parts[strike_col] if strike_col is not None else "0"
            ts         = parts[ts_col] if ts_col is not None else ""

            # Option type: prefer dedicated column, fallback to tradingsymbol suffix
            if opttype_col is not None:
                opt_type = parts[opttype_col].strip()
            else:
                m = re.search(r'(CE|PE)$', ts.upper())
                opt_type = m.group(1) if m else None

            if inst_type not in ("OPTIDX", "OPTSTK", "OPT"):
                continue
            if "BANKNIFTY" not in name.upper():
                continue
            if not expiry_str:
                continue

            exp_date = datetime.strptime(expiry_str[:10], "%Y-%m-%d").date()
            if not (0 <= (exp_date - today).days <= 14):
                continue

            strike = int(float(strike_str)) if strike_str else 0

            # ATM range filter
            if atm and abs(strike - atm) > atm_range:
                continue

            if inst_key:
                keys.append(inst_key)
                if strike and opt_type in ("CE", "PE"):
                    strike_map[inst_key] = {
                        "strike": strike,
                        "option_type": opt_type,
                    }
        except Exception:
            continue

    print(f"CSV parse: {len(keys)} keys, {len(strike_map)} mapped (ATM ±{atm_range} from {atm})")
    return keys, strike_map


def try_instrument_dump(ltp=None):
    csv_text = fetch_instrument_dump()
    if not csv_text:
        return [], {}
    return parse_csv(csv_text, ltp=ltp, atm_range=1500)


# ---------- MAIN ----------

# Module-level cache so websocket.py can access strike_map
_strike_map = {}


def get_option_chain_keys():
    global _strike_map

    ltp = get_banknifty_ltp()
    if ltp:
        print(f"BankNifty LTP: {ltp}")

    # Method A
    keys = try_option_chain_keys()
    if keys:
        print(f"Method A success: {len(keys)} keys")
        return keys

    # Method B
    keys = try_instrument_search()
    if keys:
        print(f"Method B success: {len(keys)} keys")
        return keys

    # Method C
    keys, strike_map = try_instrument_dump(ltp=ltp)
    if keys:
        _strike_map = strike_map
        print(f"Method C success: {len(keys)} keys")
        return keys

    print("All 3 methods failed.")
    return []


def get_strike_map():
    return _strike_map


def get_ltp():
    return get_banknifty_ltp()