subscribed_keys = []
import json
import threading
import websocket
from live_data import TOKEN

WS_URL = "wss://api.upstox.com/v2/feed/market-data"

live_data = {}

def on_message(ws, message):
    global live_data

    try:
        data = json.loads(message)

        feeds = data.get("feeds", {})
        for key, feed in feeds.items():
            market_ff = feed.get("ff", {}).get("marketFF", {})
            ltpc = market_ff.get("ltpc", {})
            e_feed = market_ff.get("eFeedDetails", {})

            live_data[key] = {
                "ltp": ltpc.get("ltp", 0),
                "oi": e_feed.get("oi", 0),
                "volume": e_feed.get("vtt", 0),
                "ltt": ltpc.get("ltt"),
            }

        if feeds:
            print(f"📥 Ticks received: {len(live_data)}")

    except Exception as e:
        print(f"❌ WebSocket parse error: {e}")


def on_open(ws):
    print("🟢 WebSocket Connected")

    subscribe_message = {
        "guid": "banknifty-live-feed",
        "method": "sub",
        "data": {
            "mode": "full",
            "instrumentKeys": subscribed_keys
        }
    }

    ws.send(json.dumps(subscribe_message))
    print(f"📡 Subscribed to {len(subscribed_keys)} instruments")

def start_ws(instrument_keys):
    global subscribed_keys
    subscribed_keys = instrument_keys

    def run():
        ws = websocket.WebSocketApp(
            WS_URL,
            header={
                "Authorization": f"Bearer {TOKEN}"
            },
            on_open=on_open,
            on_message=on_message
        )

        ws.run_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()