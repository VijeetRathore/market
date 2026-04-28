import pandas as pd
import numpy as np
from datetime import datetime


def compute_features(df):
    """
    df columns expected (per tick, indexed by time):
      instrument_key, strike, option_type (CE/PE), ltp, oi, volume
    
    Returns a single-row dict with all computed features.
    """
    if df.empty:
        return {}

    ce = df[df["option_type"] == "CE"].copy()
    pe = df[df["option_type"] == "PE"].copy()

    features = {}

    # ── 1. PCR (ATM ±500pt only to avoid OTM distortion) ──
    total_ce_oi = ce["oi"].sum()
    total_pe_oi = pe["oi"].sum()
    features["pcr"] = total_pe_oi / max(total_ce_oi, 1)

    # ── 2. OI Change momentum ──
    # Positive = OI building up (fresh positions), Negative = unwinding
    features["ce_oi_change"] = ce["oi_change"].sum() if "oi_change" in ce.columns else 0
    features["pe_oi_change"] = pe["oi_change"].sum() if "oi_change" in pe.columns else 0

    # Net OI pressure: positive = put writers dominant (bullish), negative = call writers dominant (bearish)
    features["oi_pressure"] = features["pe_oi_change"] - features["ce_oi_change"]

    # ── 3. Price Momentum (last 3 ticks of underlying) ──
    if "underlying_ltp" in df.columns:
        prices = df["underlying_ltp"].dropna().tail(4).tolist()
        if len(prices) >= 3:
            diffs = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
            # All 3 ticks same direction = strong momentum
            features["price_momentum"] = sum(diffs)
            features["momentum_consistent"] = all(d > 0 for d in diffs) or all(d < 0 for d in diffs)
        else:
            features["price_momentum"] = 0
            features["momentum_consistent"] = False
    else:
        features["price_momentum"] = 0
        features["momentum_consistent"] = False

    # ── 4. ATM Skew (IV difference CE vs PE at ATM) ──
    # Higher PE IV than CE IV = market fearing downside
    if "iv" in df.columns:
        atm_ce = ce.sort_values("atm_distance").head(1)
        atm_pe = pe.sort_values("atm_distance").head(1)
        if not atm_ce.empty and not atm_pe.empty:
            features["atm_iv_skew"] = float(atm_pe["iv"].iloc[0]) - float(atm_ce["iv"].iloc[0])
        else:
            features["atm_iv_skew"] = 0
    else:
        features["atm_iv_skew"] = 0

    # ── 5. Volume Confirmation ──
    # Volume spike = current volume > 2x rolling average
    if "volume" in ce.columns and "vol_avg" in ce.columns:
        ce_vol_spike = (ce["volume"] > ce["vol_avg"] * 2).any()
        pe_vol_spike = (pe["volume"] > pe["vol_avg"] * 2).any()
    else:
        ce_vol_spike = False
        pe_vol_spike = False

    features["ce_vol_spike"] = ce_vol_spike
    features["pe_vol_spike"] = pe_vol_spike

    # ── 6. Time filters ──
    now = datetime.now().time()
    features["in_trading_window"] = (
        datetime.strptime("09:30", "%H:%M").time() <= now <=
        datetime.strptime("15:00", "%H:%M").time()
    )
    features["near_expiry_risk"] = (
        now >= datetime.strptime("15:00", "%H:%M").time()
    )

    return features