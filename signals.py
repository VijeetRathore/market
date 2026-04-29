def generate_signal(
    pcr,
    spot_price,
    atm_strike,
    support,
    resistance,
    max_pain,
    oi_summary,
    vol_spike=False
):
    call_writing = oi_summary.get("call_writing", 0)
    put_writing = oi_summary.get("put_writing", 0)
    call_unwinding = oi_summary.get("call_unwinding", 0)
    put_unwinding = oi_summary.get("put_unwinding", 0)

    bullish_score = 0
    bearish_score = 0

    # PCR Analysis
    if pcr > 1.3:
        bullish_score += 2
    elif pcr < 0.7:
        bearish_score += 2
    elif pcr > 1.1:
        bullish_score += 1
    elif pcr < 0.9:
        bearish_score += 1

    # OI Activity Analysis
    if put_writing > call_writing:
        bullish_score += 2
    elif call_writing > put_writing:
        bearish_score += 2

    if call_unwinding > 0:
        bullish_score += 1

    if put_unwinding > 0:
        bearish_score += 1

    # Price Position Analysis
    if spot_price:
        if resistance and spot_price > resistance:
            bullish_score += 3
        elif support and spot_price < support:
            bearish_score += 3

        if max_pain:
            if spot_price > max_pain:
                bullish_score += 1
            elif spot_price < max_pain:
                bearish_score += 1

    # Volume Confirmation
    if vol_spike:
        bullish_score += 1
        bearish_score += 1

    # Final Decision
    if bullish_score >= bearish_score + 2:
        signal = "BUY_CALL"
    elif bearish_score >= bullish_score + 2:
        signal = "BUY_PUT"
    else:
        signal = "HOLD"
        
    total_score = bullish_score + bearish_score
    score_diff = abs(bullish_score - bearish_score)

    if signal == "HOLD":
        confidence = max(50, 70 - (score_diff * 5))
    else:
        # Yeh pura block 'else' ke andar ek level aur aage hona chahiye
        if total_score == 0:
            confidence = 50
        else:
            confidence = min(
                95,
                round(55 + (score_diff / max(total_score, 1)) * 40)
            )

    if confidence >= 80:
        strength = "Strong"
    elif confidence >= 65:
        strength = "Moderate"
    else:
        strength = "Weak"

    return {
        "signal": signal,
        "confidence": confidence,
        "strength": strength,
        "bullish_score": bullish_score,
        "bearish_score": bearish_score,
    }


def get_trade_setup(signal, atm_strike, support=None, resistance=None):
    if not atm_strike:
        return None

    if signal == "BUY_CALL":
        return {
            "instrument": f"{int(atm_strike)} CE",
            "entry": "Above market price",
            "stop_loss": "-15%",
            "target_1": "+20%",
            "target_2": "+40%",
            "rr_ratio": "1:2.5"
        }

    if signal == "BUY_PUT":
        return {
            "instrument": f"{int(atm_strike)} PE",
            "entry": "Above market price",
            "stop_loss": "-15%",
            "target_1": "+20%",
            "target_2": "+40%",
            "rr_ratio": "1:2.5"
        }

    return {
        "instrument": "Wait & Watch",
        "entry": f"Above {int(resistance)} or Below {int(support)}" if support and resistance else "Breakout confirmation",
        "stop_loss": "After breakout confirmation",
        "target_1": "Next key level",
        "target_2": "Trail position",
        "rr_ratio": "Conditional"
    }
