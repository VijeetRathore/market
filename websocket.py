import asyncio
import json
import uuid
import requests
import websockets
import numpy as np
from datetime import datetime

from config import TOKEN
from option_chain import get_option_chain_keys, get_strike_map
from signals import generate_signal
from MarketDataFeedV3_pb2 import FeedResponse

UNDERLYING_KEY = "NSE_INDEX|Nifty Bank"

prev_oi = {}
price_history = []
vol_history = {}


def get_ws_url():
    url = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    res = requests.get(url, headers=headers, timeout=10)
    data = res.json()
    if "data" not in data:
        raise Exception(f"Auth failed: {data}")
    return data["data"]["authorized_redirect_uri"]


def build_subscribe_msg(instrument_keys, mode="full"):
    """Build subscription request as binary bytes — same as Upstox SDK"""
    request = {
        "guid": str(uuid.uuid4()),
        "method": "sub",
        "data": {
            "instrumentKeys": instrument_keys,
            "mode": mode,
        }
    }
    return json.dumps(request).encode("utf-8")


def parse_feed(raw_bytes, strike_map):
    feed_response = FeedResponse()
    feed_response.ParseFromString(raw_bytes)

    msg_type = feed_response.type
    feeds_count = len(feed_response.feeds)

    print(f"[MSG] type={msg_type} | feeds={feeds_count}")

    if feeds_count == 0:
        return []

    rows = []

    for key, feed in feed_response.feeds.items():
        ff = feed.fullFeed

        if ff.HasField("marketFF"):
            mff = ff.marketFF
            ltp = mff.ltpc.ltp
            oi  = mff.oi
            vol = mff.vtt
        elif ff.HasField("indexFF"):
            iff = ff.indexFF
            ltp = iff.ltpc.ltp
            oi  = 0
            vol = 0
        else:
            ltp = feed.ltpc.ltp if feed.HasField("ltpc") else 0
            oi  = 0
            vol = 0

        print(f"  {key} | ltp={ltp:.2f} | oi={oi:.0f} | vol={vol}")

        if key == UNDERLYING_KEY or "Nifty Bank" in key:
            price_history.append(float(ltp))
            if len(price_history) > 10:
                price_history.pop(0)
            continue

        if key not in strike_map:
            continue

        strike   = strike_map[key]["strike"]
        opt_type = strike_map[key]["option_type"]

        oi_change = float(oi) - prev_oi.get(key, float(oi))
        prev_oi[key] = float(oi)

        if key not in vol_history:
            vol_history[key] = []
        vol_history[key].append(float(vol))
        if len(vol_history[key]) > 5:
            vol_history[key].pop(0)
        vol_avg = np.mean(vol_history[key])

        rows.append({
            "option_type": opt_type,
            "oi":          float(oi),
            "oi_change":   oi_change,
            "volume":      float(vol),
            "vol_avg":     vol_avg,
        })

    return rows


async def start_ws():
    while True:
        try:
            keys = get_option_chain_keys()
            strike_map = get_strike_map()

            print(f"Subscribing: {len(keys)} keys | Strike map: {len(strike_map)} entries")

            if not keys:
                print("No keys. Retrying in 5s...")
                await asyncio.sleep(5)
                continue

            subscribe_keys = list(set(keys + [UNDERLYING_KEY]))
            ws_url = get_ws_url()

            async with websockets.connect(
                ws_url,
                additional_headers={"Authorization": f"Bearer {TOKEN}"}
            ) as ws:

                print("✅ WS Connected")

                # Send as binary — critical for Upstox v3
                sub_msg = build_subscribe_msg(subscribe_keys, mode="full")
                await ws.send(sub_msg)
                print(f"Subscription sent ({len(sub_msg)} bytes binary)")

                tick_count = 0

                while True:
                    msg = await ws.recv()

                    if not isinstance(msg, bytes):
                        print(f"[NON-BYTES] {type(msg)}: {str(msg)[:80]}")
                        continue

                    try:
                        rows = parse_feed(msg, strike_map)
                    except Exception as e:
                        print(f"Parse error: {e}")
                        continue

                    if not rows:
                        continue

                    tick_count += 1

                    ce = [r for r in rows if r["option_type"] == "CE"]
                    pe = [r for r in rows if r["option_type"] == "PE"]

                    ce_oi = sum(r["oi"] for r in ce)
                    pe_oi = sum(r["oi"] for r in pe)
                    pcr   = pe_oi / max(ce_oi, 1)

                    oi_pressure = (
                        sum(r["oi_change"] for r in pe) -
                        sum(r["oi_change"] for r in ce)
                    )

                    ce_vol_spike = any(r["volume"] > r["vol_avg"] * 2 for r in ce)
                    pe_vol_spike = any(r["volume"] > r["vol_avg"] * 2 for r in pe)

                    if len(price_history) >= 4:
                        prices = price_history[-4:]
                        diffs  = [prices[i+1] - prices[i] for i in range(3)]
                        momentum    = sum(diffs)
                        momentum_ok = all(d > 0 for d in diffs) or all(d < 0 for d in diffs)
                    else:
                        momentum    = 0
                        momentum_ok = False

                    now = datetime.now().time()
                    in_window = (
                        datetime.strptime("09:30", "%H:%M").time() <= now <=
                        datetime.strptime("15:00", "%H:%M").time()
                    )

                    features = {
                        "pcr":                 pcr,
                        "oi_pressure":         oi_pressure,
                        "price_momentum":      momentum,
                        "momentum_consistent": momentum_ok,
                        "ce_vol_spike":        ce_vol_spike,
                        "pe_vol_spike":        pe_vol_spike,
                        "atm_iv_skew":         0,
                        "in_trading_window":   in_window,
                        "near_expiry_risk":    False,
                    }

                    signal = generate_signal(features)

                    spot = price_history[-1] if price_history else 0
                    print(
                        f"📊 #{tick_count} Spot={spot:.0f} | PCR={pcr:.2f} | "
                        f"OI_P={oi_pressure:.0f} | MOM={momentum:.1f}({momentum_ok}) | "
                        f"SIGNAL={signal}"
                    )

        except Exception as e:
            print(f"WS Error: {e}")
            await asyncio.sleep(3)