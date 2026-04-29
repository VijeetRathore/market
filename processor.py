from marketdata_pb2 import FeedResponse

async def process_tick(msg):
    if not isinstance(msg, bytes):
        return

    try:
        feed = FeedResponse()
        feed.ParseFromString(msg)

        if not feed.feeds:
            return

        print("📊 Feeds:", len(feed.feeds))

        for key, val in feed.feeds.items():
            ltp = val.ltpc.ltp if val.ltpc else 0
            oi = val.marketLevel.oi if val.marketLevel else 0
            print(f"{key} → LTP: {ltp} | OI: {oi}")

    except Exception as e:
        print("❌ Decode error:", e)