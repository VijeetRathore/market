import json
import websocket
import threading
import requests


# 🔹 Get authorized WS URL (v3)
def get_ws_url(token):
    url = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
    headers = {"Authorization": f"Bearer {token}"}

    res = requests.get(url, headers=headers)
    data = res.json()

    if "data" not in data or "authorized_redirect_uri" not in data["data"]:
        raise Exception(f"Auth failed: {data}")

    return data["data"]["authorized_redirect_uri"]


class MarketFeed:
    def __init__(self, token, instrument_keys, on_tick):
        self.token = token
        self.instrument_keys = instrument_keys
        self.on_tick = on_tick
        self.ws = None

    def _on_open(self, ws):
        print("✅ WS Connected")

        sub_msg = {
            "guid": "someguid",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": self.instrument_keys
            }
        }

        ws.send(json.dumps(sub_msg))

    def _on_message(self, ws, message):
        try:
            if isinstance(message, bytes):
                try:
                    message = message.decode("utf-8")
                except:
                    return

            data = json.loads(message)

            feeds = data.get("data", {}).get("feeds", {})
            parsed = {}

            for key, val in feeds.items():
                ff = val.get("ff", {})
                market = ff.get("marketFF", {})

                ltp = market.get("ltp")
                volume = market.get("vtt", 0)

                if ltp is None:
                    continue

                parsed[key] = {
                    "ltp": ltp,
                    "volume": volume
                }

            if parsed:
                self.on_tick(parsed)

        except Exception as e:
            print("Parse error:", e)

    def _on_error(self, ws, error):
        print("WS Error:", error)

    def _on_close(self, ws, close_status_code, close_msg):
        print("❌ WS Closed")

    # 🔥 FIXED start() method inside class
    def start(self):
        ws_url = get_ws_url(self.token)

        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        thread = threading.Thread(target=self.ws.run_forever)
        thread.daemon = True
        thread.start()