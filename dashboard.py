import time
import pandas as pd
import streamlit as st
from option_chain import (
    get_option_chain_keys,
    fetch_instrument_dump,
    build_meta_from_csv,
)
from analytics import AnalyticsEngine
from signals import generate_signal, get_trade_setup
from live_data import fetch_live_data, fetch_banknifty_spot

st.set_page_config(
    page_title="BANKNIFTY Options Dashboard",
    page_icon="📈",
    layout="wide"
)


@st.cache_resource
def initialize_engine():
    keys = get_option_chain_keys()
    csv_text = fetch_instrument_dump()
    instrument_meta = build_meta_from_csv(csv_text, keys)
    engine = AnalyticsEngine(instrument_meta)
    return keys, instrument_meta, engine


def format_value(value, decimals=2):
    if value is None or value == 0:
        return "N/A"
    return f"{value:,.{decimals}f}"


def main():
    st.title("📊 BANKNIFTY Options Analytics Dashboard")
    st.caption("Live OI, PCR, Max Pain, Support/Resistance, Signal & Trade Setup Monitor")

    try:
        keys, instrument_meta, engine = initialize_engine()
    except Exception as e:
        st.error(f"Initialization failed: {e}")
        return

    st.sidebar.header("Controls")
    refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", 5, 60, 10)

    ce_count = sum(1 for v in instrument_meta.values() if v["type"] == "CE")
    pe_count = sum(1 for v in instrument_meta.values() if v["type"] == "PE")

    st.sidebar.metric("Tracked Instruments", len(instrument_meta))
    st.sidebar.metric("Call Options", ce_count)
    st.sidebar.metric("Put Options", pe_count)

    api_keys = [v["instrument_key"] for v in instrument_meta.values()]
    ticks = fetch_live_data(api_keys, instrument_meta)

    if not ticks:
        st.warning("No live data received. Please try again.")
        return

    engine.update_ticks(ticks)

    spot_price = fetch_banknifty_spot()
    atm_strike = engine.get_atm_strike(spot_price)
    support, resistance = engine.get_support_resistance()
    max_pain = engine.get_max_pain()
    atm_premium = engine.get_atm_premium_data(atm_strike)
    top_supports, top_resistances = engine.get_top_oi_levels()
    oi_summary = engine.detect_oi_changes()
    oi_change_df = engine.get_oi_change_table()

    pcr = engine.calculate_metrics()
    total_vol = sum(v.get("volume", 0) for v in engine.data.values())
    vol_spike = engine.detect_volume_spike(total_vol)

    engine.update_history(pcr, total_vol)

    # Generate Signal
    signal_data = generate_signal(
        pcr=pcr,
        spot_price=spot_price,
        atm_strike=atm_strike,
        support=support,
        resistance=resistance,
        max_pain=max_pain,
        oi_summary=oi_summary,
        vol_spike=vol_spike
        )

    signal = signal_data["signal"]
    confidence = signal_data["confidence"]
    strength = signal_data["strength"]

    # Market Bias
    if signal == "BUY_CALL":
        st.success("🟢 Market Bias: Bullish")
    elif signal == "BUY_PUT":
        st.error("🔴 Market Bias: Bearish")
    else:
        st.warning("🟡 Market Bias: Neutral")

# Dashboard Metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    col1.metric("Spot", format_value(spot_price))
    col2.metric("ATM", format_value(atm_strike, 0))
    col3.metric("PCR", f"{pcr:.2f}")
    col4.metric("Support", format_value(support, 0))
    col5.metric("Resistance", format_value(resistance, 0))
    col6.metric("Max Pain", format_value(max_pain, 0))
    
    # ATM Premium Tracker
    if atm_premium:
        st.subheader("💰 ATM Premium Tracker")
        
        p1, p2, p3, p4 = st.columns(4)
        
        p1.metric("ATM CE Premium", f"₹{atm_premium['ce_ltp']:,.2f}")
        p2.metric("ATM PE Premium", f"₹{atm_premium['pe_ltp']:,.2f}")
        p3.metric(
            "Combined Premium",
            f"₹{atm_premium['combined_premium']:,.2f}"
        )
        p4.metric("Volatility Bias", atm_premium["bias"])

    st.markdown("---")

    # Trading Signal
    if signal == "BUY_CALL":
        st.success(f"📈 Signal: {signal}")
    elif signal == "BUY_PUT":
        st.error(f"📉 Signal: {signal}")
    else:
        st.warning(f"⏸️ Signal: {signal}")

    # Signal Confidence
    st.subheader("📊 Signal Confidence")

    col_conf1, col_conf2 = st.columns([3, 1])

    with col_conf1:
        st.progress(confidence / 100)

    with col_conf2:
        st.metric("Confidence", f"{confidence}%")

    if strength == "Strong":
        st.success(f"💪 Signal Strength: {strength}")
    elif strength == "Moderate":
        st.warning(f"⚡ Signal Strength: {strength}")
    else:
        st.info(f"🔹 Signal Strength: {strength}")

    # Trade Setup Recommendation
    trade_setup = get_trade_setup(
        signal=signal,
        atm_strike=atm_strike,
        support=support,
        resistance=resistance
    )

    st.subheader("🎯 Suggested Trade Setup")

    if trade_setup:
        c1, c2, c3, c4, c5 = st.columns(5)

        c1.metric("Instrument", trade_setup["instrument"])
        c2.metric("Entry", trade_setup["entry"])
        c3.metric("Stop Loss", trade_setup["stop_loss"])
        c4.metric("Target 1", trade_setup["target_1"])
        c5.metric("Target 2", trade_setup["target_2"])

        st.info(f"Risk-Reward Ratio: {trade_setup['rr_ratio']}")
    else:
        st.info("No trade setup available at the moment.")

    # Breakout / Breakdown Alert Panel
    st.subheader("🚨 Breakout Alert Levels")

    bullish_trigger = resistance
    bearish_trigger = support

    if spot_price and bullish_trigger and bearish_trigger:
        up_move = bullish_trigger - spot_price
        down_move = spot_price - bearish_trigger

        up_pct = (up_move / spot_price) * 100
        down_pct = (down_move / spot_price) * 100

        b1, b2 = st.columns(2)

        with b1:
            st.success("🟢 Bullish Breakout Trigger")
            st.metric(
                "Above",
                f"{bullish_trigger:,.0f}",
                f"{up_move:,.2f} pts ({up_pct:.2f}%)"
            )

        with b2:
            st.error("🔴 Bearish Breakdown Trigger")
            st.metric(
                "Below",
                f"{bearish_trigger:,.0f}",
                f"{down_move:,.2f} pts ({down_pct:.2f}%)"
            )

    # Signal Reasoning
    st.subheader("🧠 Signal Reasoning")

    reasons = []

    if pcr > 1.2:
        reasons.append("PCR is bullish (more Put OI than Call OI)")
    elif pcr < 0.8:
        reasons.append("PCR is bearish (more Call OI than Put OI)")
    else:
        reasons.append("PCR is neutral")

    if spot_price and support and spot_price > support:
        reasons.append(f"Spot is above support ({int(support)})")

    if spot_price and resistance and spot_price < resistance:
        reasons.append(f"Spot is below resistance ({int(resistance)})")

    if spot_price and max_pain:
        if spot_price > max_pain:
            reasons.append(f"Spot is trading above Max Pain ({int(max_pain)})")
        elif spot_price < max_pain:
            reasons.append(f"Spot is trading below Max Pain ({int(max_pain)})")

    if oi_summary.get("call_writing", 0) > oi_summary.get("put_writing", 0):
        reasons.append("Higher Call Writing observed")
    elif oi_summary.get("put_writing", 0) > oi_summary.get("call_writing", 0):
        reasons.append("Higher Put Writing observed")

    if vol_spike:
        reasons.append("Volume spike detected")

    for reason in reasons:
        st.write(f"• {reason}")

    # OI Levels
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🟢 Top Support Levels")
        st.write(", ".join(str(int(x[0])) for x in top_supports))

    with col2:
        st.subheader("🔴 Top Resistance Levels")
        st.write(", ".join(str(int(x[0])) for x in top_resistances))

    # OI Activity Summary
    st.subheader("🧾 OI Activity Summary")
    st.json(oi_summary)

    # OI Change Momentum Table
    st.subheader("🔥 Top OI Changes (Last Refresh)")
    
    if not oi_change_df.empty:
            st.dataframe(
                oi_change_df,
                width="stretch",
                hide_index=True
            )
    else:
        st.info("No significant OI changes detected yet.")

    # Live Option Chain Snapshot
    st.subheader("📋 Live Option Chain Snapshot (ATM ± 5 Strikes)")

    chain = engine.build_option_chain()
    rows = []

    if chain:
        strikes = sorted(chain.keys())

        if atm_strike is not None:
            nearest_strike = min(strikes, key=lambda x: abs(x - atm_strike))
            atm_index = strikes.index(nearest_strike)
        else:
            atm_index = len(strikes) // 2

        selected_strikes = strikes[max(0, atm_index - 5): atm_index + 6]

        for strike in selected_strikes:
            ce = chain.get(strike, {}).get("CE", {})
            pe = chain.get(strike, {}).get("PE", {})

            rows.append({
                "Strike": int(strike),
                "CE OI": ce.get("oi", 0),
                "CE Vol": ce.get("volume", 0),
                "CE LTP": ce.get("ltp", 0),
                "PE LTP": pe.get("ltp", 0),
                "PE Vol": pe.get("volume", 0),
                "PE OI": pe.get("oi", 0),
            })

        if rows:
            option_df = pd.DataFrame(rows)

            def highlight_atm(row):
                if atm_strike is not None and row["Strike"] == int(atm_strike):
                    return ["background-color: #FFF3CD"] * len(row)
                return [""] * len(row)

            styled_df = option_df.style.apply(highlight_atm, axis=1)

            st.dataframe(
                styled_df,
                width="stretch",
                hide_index=True
            )
        else:
            st.info("No option chain rows available.")
    else:
        st.warning("Option chain data not available.")

    # OI Visualization
    if rows:
        st.subheader("📊 Open Interest by Strike")
        oi_chart_df = option_df.set_index("Strike")[["CE OI", "PE OI"]]
        st.bar_chart(oi_chart_df)

    # Historical Charts
    history_df = engine.get_dataframe()
    if not history_df.empty:
        history_df["datetime"] = pd.to_datetime(history_df["time"], unit="s")
        history_df["Time"] = history_df["datetime"].dt.strftime("%H:%M:%S")
        history_df = history_df.set_index("Time")

        st.subheader("📈 PCR Trend")
        st.line_chart(history_df["PCR"])

        st.subheader("📊 Volume Trend")
        st.line_chart(history_df["volume"])

    # Auto Refresh
    time.sleep(refresh_interval)
    st.rerun()


if __name__ == "__main__":
    main()