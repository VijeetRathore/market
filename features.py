def compute_features(df):
    df["PCR"] = df["PE_OI"].sum() / max(df["CE_OI"].sum(), 1)

    df["OI_DIFF"] = df["PE_OI"] - df["CE_OI"]

    df["VOL_SPIKE"] = df["PE_VOL"] > df["PE_VOL"].rolling(5).mean()

    return df