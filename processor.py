import pandas as pd
import numpy as np
from datetime import datetime
from marketdata_pb2 import FeedResponse
from features import compute_features
from signals import generate_signal

tick_store = {}
prev_oi = {}
price_history = []
vol_history = {}

UNDERLYING_KEY = "NSE_INDEX|Nifty Bank"


def _update_price_history(ltp):
    price_history.append(ltp)
    if len(price_history) > 10:
        price_history.pop(0)


def _get_strike_and_type(instrument_key):
    import re
    match = re.search(r'BANKNIFTY\d{5}(\d+)(CE|PE)', instrument_key.upper())
    if match:
        return int(match.group(1)), match.group(2)
    return None, None


async def process_tick(msg, strike_map=None):
    if not isinstance(msg, bytes):
        print(f"[SKIP] msg type: {type(msg)}")
        return None

    try:
        feed = FeedResponse()
        feed.ParseFromString(msg)

        print(f"[TICK] feeds count: {len(feed.feeds)}")

        if not feed.feeds:
            return None

        underlying_ltp = None
        rows = []

        for key, val in feed.feeds.items():
            ltp = val.ltpc.ltp if val.ltpc else 0
            oi  = val.marketLevel.oi if val.marketLevel else 0
            vol = val.marketLevel.volume if val.marketLevel else 0

            print(f"  RAW: {key} | ltp={ltp} | oi={oi} | vol={vol}")

            if key == UNDERLYING_KEY or "Nifty Bank" in key:
                underlying_ltp = ltp
                _update_price_history(ltp)
                continue

            if strike_map and key in strike_map:
                strike   = strike_map[key]["strike"]
                opt_type = strike_map[key]["option_type"]
            else:
                strike, opt_type = _get_strike_and_type(key)

            if strike is None or opt_type is None:
                print(f"  [SKIP] no strike info for {key}")
                continue

            oi_change = oi - prev_oi.get(key, oi)
            prev_oi[key] = oi

            if key not in vol_history:
                vol_history[key] = []
            vol_history[key].append(vol)
            if len(vol_history[key]) > 5:
                vol_history[key].pop(0)
            vol_avg = np.mean(vol_history[key])

            rows.append({
                "instrument_key": key,
                "strike": strike,
                "option_type": opt_type,
                "ltp": ltp,
                "oi": oi,
                "oi_change": oi_change,
                "volume": vol,
                "vol_avg": vol_avg,
                "underlying_ltp": price_history[-1] if price_history else 0,
            })

        if not rows:
            print(f"  [WARN] No rows built. price_history={price_history[-3:]}")
            return None

        df = pd.DataFrame(rows)

        if price_history:
            atm = round(price_history[-1] / 100) * 100
            df["atm_distance"] = abs(df["strike"] - atm)

        if len(price_history) >= 2:
            df["underlying_ltp"] = price_history[-1]

        features = compute_features(df)
        signal   = generate_signal(features)

        print(f"  [SIGNAL] {signal} | PCR={features.get('pcr',0):.2f} | OI_P={features.get('oi_pressure',0):.0f} | MOM={features.get('price_momentum',0):.1f} | MOK={features.get('momentum_consistent')}")

        if signal != "HOLD":
            print(f"\n🚨 SIGNAL: {signal}")

        return signal

    except Exception as e:
        print(f"Decode error: {e}")
        return None