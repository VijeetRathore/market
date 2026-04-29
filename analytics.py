import pandas as pd
from collections import defaultdict
import time


class AnalyticsEngine:
    def __init__(self, instrument_meta):
        self.meta = instrument_meta
        self.data = defaultdict(dict)
        self.history = []
        self.prev_oi = {}

    def update_ticks(self, ticks):
        for key, val in ticks.items():
            self.data[key] = val

    def build_option_chain(self):
        chain = {}

        for key, val in self.data.items():
            meta = self.meta.get(key)
            if not meta:
                continue

            strike = meta["strike"]
            opt_type = meta["type"]

            if strike not in chain:
                chain[strike] = {"CE": {}, "PE": {}}

            chain[strike][opt_type] = val

        return chain

    def calculate_metrics(self):
        total_call_oi = 0
        total_put_oi = 0

        for key, val in self.data.items():
            meta = self.meta.get(key)
            if not meta:
                continue

            oi = val.get("oi", 0)

            if meta["type"] == "CE":
                total_call_oi += oi
            elif meta["type"] == "PE":
                total_put_oi += oi

        if total_call_oi == 0:
            return 0

        return total_put_oi / total_call_oi

    def detect_volume_spike(self, current_volume):
        if len(self.history) < 5:
            return False

        avg = sum(x["volume"] for x in self.history[-5:]) / 5
        return current_volume > avg * 1.5

    def update_history(self, pcr, total_volume):
        self.history.append({
            "time": time.time(),
            "PCR": pcr,
            "volume": total_volume
        })

        if len(self.history) > 100:
            self.history.pop(0)

    def get_atm_strike(self, spot_price=None):
        strikes = sorted({meta["strike"] for meta in self.meta.values()})

        if not strikes:
            return None

        if not spot_price:
            return strikes[len(strikes) // 2]

        return min(strikes, key=lambda x: abs(x - spot_price))

    def get_support_resistance(self):
        chain = self.build_option_chain()

        support = None
        resistance = None
        max_put_oi = 0
        max_call_oi = 0

        for strike, data in chain.items():
            ce_oi = data.get("CE", {}).get("oi", 0)
            pe_oi = data.get("PE", {}).get("oi", 0)

            if pe_oi > max_put_oi:
                max_put_oi = pe_oi
                support = strike

            if ce_oi > max_call_oi:
                max_call_oi = ce_oi
                resistance = strike

        return support, resistance

    def get_max_pain(self):
        chain = self.build_option_chain()

        if not chain:
            return None

        strikes = sorted(chain.keys())
        pain_values = {}

        for expiry_price in strikes:
            total_pain = 0

            for strike in strikes:
                ce_oi = chain[strike].get("CE", {}).get("oi", 0)
                pe_oi = chain[strike].get("PE", {}).get("oi", 0)

                call_pain = max(0, expiry_price - strike) * ce_oi
                put_pain = max(0, strike - expiry_price) * pe_oi

                total_pain += call_pain + put_pain

            pain_values[expiry_price] = total_pain

        return min(pain_values, key=pain_values.get)
    
    def get_top_oi_levels(self, top_n=3):
        chain = self.build_option_chain()

        call_oi = []
        put_oi = []

        for strike, data in chain.items():
            ce_oi = data.get("CE", {}).get("oi", 0)
            pe_oi = data.get("PE", {}).get("oi", 0)

            call_oi.append((strike, ce_oi))
            put_oi.append((strike, pe_oi))

        top_resistance = sorted(call_oi, key=lambda x: x[1], reverse=True)[:top_n]
        top_support = sorted(put_oi, key=lambda x: x[1], reverse=True)[:top_n]

        return top_support, top_resistance

    def detect_oi_changes(self):
        summary = {
            "call_writing": 0,
            "put_writing": 0,
            "call_unwinding": 0,
            "put_unwinding": 0,
        }

        for key, val in self.data.items():
            meta = self.meta.get(key)
            if not meta:
                continue

            current_oi = val.get("oi", 0)
            previous_oi = self.prev_oi.get(key, current_oi)

            oi_change = current_oi - previous_oi

            if meta["type"] == "CE":
                if oi_change > 0:
                    summary["call_writing"] += oi_change
                elif oi_change < 0:
                    summary["call_unwinding"] += abs(oi_change)

            elif meta["type"] == "PE":
                if oi_change > 0:
                    summary["put_writing"] += oi_change
                elif oi_change < 0:
                    summary["put_unwinding"] += abs(oi_change)

            self.prev_oi[key] = current_oi

        return summary
    def get_atm_premium_data(self, atm_strike):
        """Returns ATM CE premium, ATM PE premium, combined premium, and straddle bias."""
        if atm_strike is None:
            return None

        chain = self.build_option_chain()
        if not chain or atm_strike not in chain:
            return None

        ce_data = chain.get(atm_strike, {}).get("CE", {})
        pe_data = chain.get(atm_strike, {}).get("PE", {})

        ce_ltp = ce_data.get("ltp", 0)
        pe_ltp = pe_data.get("ltp", 0)

        combined_premium = ce_ltp + pe_ltp

        if combined_premium > 600:
            bias = "Expensive"
        elif combined_premium < 300:
            bias = "Cheap"
        else:
            bias = "Neutral"

        return {
            "ce_ltp": ce_ltp,
            "pe_ltp": pe_ltp,
            "combined_premium": combined_premium,
            "bias": bias,
        }
    
    def get_oi_change_table(self, top_n=10):
        """Returns strike-wise OI changes for CE and PE. Useful for identifying fresh writing/unwinding."""
        rows = []
        chain = self.build_option_chain()
        
        if not chain:
            return pd.DataFrame()

        for strike in sorted(chain.keys()):
            ce_data = chain.get(strike, {}).get("CE", {})
            pe_data = chain.get(strike, {}).get("PE", {})

            # Metadata se keys fetch karna
            ce_key = next(
                (k for k, v in self.meta.items()
                 if v["strike"] == strike and v["type"] == "CE"),
                None
            )
            pe_key = next(
                (k for k, v in self.meta.items()
                 if v["strike"] == strike and v["type"] == "PE"),
                None
            )

            ce_current = ce_data.get("oi", 0)
            pe_current = pe_data.get("oi", 0)

            ce_prev = self.prev_oi.get(ce_key, ce_current)
            pe_prev = self.prev_oi.get(pe_key, pe_current)

            ce_change = ce_current - ce_prev
            pe_change = pe_current - pe_prev

            # OI Change Interpretation logic
            interpretation = "Neutral"
            if pe_change > ce_change and pe_change > 0:
                interpretation = "Bullish Build-up"
            elif ce_change > pe_change and ce_change > 0:
                interpretation = "Bearish Build-up"
            elif ce_change < 0 and pe_change < 0:
                interpretation = "Unwinding"

            rows.append({
                "Strike": int(strike),
                "CE OI Change": int(ce_change),
                "PE OI Change": int(pe_change),
                "Interpretation": interpretation
            })

        df = pd.DataFrame(rows)

        if not df.empty:
            # Sorting logic for Top N strikes
            df["Total Change"] = (
                df["CE OI Change"].abs() + df["PE OI Change"].abs()
            )
            df = df.sort_values(
                "Total Change",
                ascending=False
            ).head(top_n)
            
            df = df.drop(columns=["Total Change"])

        return df
    
    # Dono functions ka 'def' ek hi line (vertical alignment) mein hona chahiye
    def get_dataframe(self):
        return pd.DataFrame(self.history)