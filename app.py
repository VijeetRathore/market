import time
from option_chain import (
    get_option_chain_keys,
    fetch_instrument_dump,
    build_meta_from_csv,
)
from analytics import AnalyticsEngine
from signals import generate_signal
from live_data import fetch_live_data, fetch_banknifty_spot

# STEP 1: Fetch option keys
keys = get_option_chain_keys()
print("📊 Tracking:", len(keys))

# STEP 2: Build instrument metadata
csv_text = fetch_instrument_dump()
instrument_meta = build_meta_from_csv(csv_text, keys)

print("✅ Meta built:", len(instrument_meta))

ce_count = sum(1 for v in instrument_meta.values() if v["type"] == "CE")
pe_count = sum(1 for v in instrument_meta.values() if v["type"] == "PE")
print(f"📌 CE: {ce_count} | PE: {pe_count}")

# STEP 3: Initialize analytics engine
engine = AnalyticsEngine(instrument_meta)

# STEP 4: Main loop
while True:
    try:
        time.sleep(1)
        st.rerun()

        # Fetch live data
        api_keys = [v["instrument_key"] for v in instrument_meta.values()]
        from ws_stream import live_data, start_ws
        # start websocket once
        start_ws(api_keys)

        if not ticks:
            print("⚠️ No live data received")
            continue

        # Update engine
        ticks = live_data
        engine.update_ticks(ticks)

        # Spot / ATM
        spot_price = fetch_banknifty_spot()
        atm_strike = engine.get_atm_strike(spot_price)

        # OI Levels
        support, resistance = engine.get_support_resistance()
        max_pain = engine.get_max_pain()
        top_supports, top_resistances = engine.get_top_oi_levels()

        # OI Change Analysis
        oi_summary = engine.detect_oi_changes()

        # Metrics
        pcr = engine.calculate_metrics()
        total_vol = sum(v.get("volume", 0) for v in engine.data.values())
        vol_spike = engine.detect_volume_spike(total_vol)

        # Update history
        engine.update_history(pcr, total_vol)

        # Generate signal
        df = engine.get_dataframe()
        df["VOL_SPIKE"] = vol_spike
        signal = generate_signal(
            pcr=pcr,
            spot_price=spot_price,
            atm_strike=atm_strike,
            support=support,
            resistance=resistance,
            max_pain=max_pain,
            oi_summary=oi_summary,
            vol_spike=vol_spike
            )

        # Safe formatting
        spot_display = f"{spot_price:,.2f}" if spot_price else "N/A"
        atm_display = f"{atm_strike:.0f}" if atm_strike is not None else "N/A"
        support_display = f"{support:.0f}" if support is not None else "N/A"
        resistance_display = f"{resistance:.0f}" if resistance is not None else "N/A"
        max_pain_display = f"{max_pain:.0f}" if max_pain is not None else "N/A"

        print(
            f"📊 Spot: {spot_display} | "
            f"ATM: {atm_display} | "
            f"S: {support_display} | "
            f"R: {resistance_display} | "
            f"MP: {max_pain_display} | "
            f"PCR: {pcr:.2f} | "
            f"VOL: {total_vol:,} | "
            f"SIGNAL: {signal}"
        )

        print("🟢 Top Supports   :", [int(x[0]) for x in top_supports])
        print("🔴 Top Resistances:", [int(x[0]) for x in top_resistances])

        print(
            f"🧾 CW: {int(oi_summary['call_writing'])} | "
            f"PW: {int(oi_summary['put_writing'])} | "
            f"CU: {int(oi_summary['call_unwinding'])} | "
            f"PU: {int(oi_summary['put_unwinding'])}"
        )

        print("-" * 110)

    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
        break

    except Exception as e:
        print(f"❌ Runtime error: {e}")