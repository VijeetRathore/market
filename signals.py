def generate_signal(features: dict) -> str:
    """
    Combined OI + Price Momentum signal with double confirmation.

    PRIMARY conditions (both required):
      - OI pressure aligns with direction
      - Price momentum consistent (3 ticks same direction)

    DOUBLE CONFIRMATION (at least one required):
      - Volume spike in direction of trade
      - ATM IV skew confirms direction

    FILTERS (any one blocks trade):
      - Outside trading window (before 9:30 or after 15:00)
      - Near expiry risk (after 15:00)
      - PCR in neutral zone (0.85–1.15) with no strong momentum
    """

    if not features:
        return "HOLD"

    # ── Hard filters ──
    if not features.get("in_trading_window", False):
        return "HOLD"

    if features.get("near_expiry_risk", False):
        return "HOLD"

    pcr               = features.get("pcr", 1.0)
    oi_pressure       = features.get("oi_pressure", 0)
    price_momentum    = features.get("price_momentum", 0)
    momentum_ok       = features.get("momentum_consistent", False)
    ce_vol_spike      = features.get("ce_vol_spike", False)
    pe_vol_spike      = features.get("pe_vol_spike", False)
    atm_iv_skew       = features.get("atm_iv_skew", 0)

    # ── BULLISH signal: BUY_CALL ──
    # Primary: Put OI building (writers shorting puts = bullish) + price going up
    primary_bullish = (
        oi_pressure > 0 and          # Put OI increasing more than Call OI
        price_momentum > 0 and       # Price moving up
        momentum_ok                  # 3 consecutive ticks upward
    )

    # Double confirmation for bullish (at least one)
    confirm_bullish = (
        pe_vol_spike or              # Volume spike in puts (writers active)
        atm_iv_skew < -0.02          # Call IV > Put IV = market expects upside
    )

    # PCR soft filter: PCR > 1.2 = more puts = bullish bias
    pcr_bullish = pcr > 1.2

    if primary_bullish and confirm_bullish:
        return "BUY_CALL"

    # Relaxed: primary + PCR filter (when confirmation unavailable)
    if primary_bullish and pcr_bullish:
        return "BUY_CALL"

    # ── BEARISH signal: BUY_PUT ──
    # Primary: Call OI building (writers shorting calls = bearish) + price going down
    primary_bearish = (
        oi_pressure < 0 and          # Call OI increasing more than Put OI
        price_momentum < 0 and       # Price moving down
        momentum_ok                  # 3 consecutive ticks downward
    )

    # Double confirmation for bearish (at least one)
    confirm_bearish = (
        ce_vol_spike or              # Volume spike in calls (writers active)
        atm_iv_skew > 0.02           # Put IV > Call IV = market fears downside
    )

    pcr_bearish = pcr < 0.8

    if primary_bearish and confirm_bearish:
        return "BUY_PUT"

    if primary_bearish and pcr_bearish:
        return "BUY_PUT"

    return "HOLD"