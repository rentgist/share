import pandas as pd

# ─────────────────────────────────────────
# RSI & MACD 연산기
# 단일 진실 원천(Single Source of Truth): get_rolling_rsi
# ─────────────────────────────────────────
def get_rolling_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs    = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def calc_rsi(close, period=14):
    """시계열 RSI의 마지막 값(스칼라). get_rolling_rsi에서 파생 — 로직 중복 제거."""
    if close is None or len(close) < period + 1:
        return None
    val = get_rolling_rsi(close, period).iloc[-1]
    if pd.isna(val):
        return None
    return round(float(val), 2)

def calc_macd(close):
    if len(close) < 35:
        return None, "N/A"
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    return round(float(macd.iloc[-1]), 2), "🟢상승" if hist.iloc[-1] > 0 else "🔴하락"
