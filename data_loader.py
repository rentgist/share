import json
import os
import requests
import datetime
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
import streamlit as st
from tenacity import retry, stop_after_attempt, wait_exponential

from config import US_NAME_MAP, get_kst_now
from indicators import calc_rsi, calc_macd
from signals import parse_insider, short_interest_label, get_comprehensive_risk_grade

# ─────────────────────────────────────────
# KRX 맵핑
# ─────────────────────────────────────────
@st.cache_data(ttl=86400)
def get_krx_mapping():
    mapping = {
        "LS ELECTRIC": {"raw_code": "010120", "yf_code": "010120.KS"},
        "LS일렉트릭": {"raw_code": "010120", "yf_code": "010120.KS"},
        "현대차": {"raw_code": "005380", "yf_code": "005380.KS"},
        "현대자동차": {"raw_code": "005380", "yf_code": "005380.KS"},
        "삼성전자": {"raw_code": "005930", "yf_code": "005930.KS"},
        "카카오": {"raw_code": "035720", "yf_code": "035720.KS"},
        "네이버": {"raw_code": "035420", "yf_code": "035420.KS"},
        "NAVER": {"raw_code": "035420", "yf_code": "035420.KS"}
    }
    try:
        df = fdr.StockListing('KRX')
        for _, row in df.iterrows():
            market_suffix = ".KS" if row['Market'] == 'KOSPI' else ".KQ"
            mapping[str(row['Name']).upper()] = {
                "raw_code": row['Code'],
                "yf_code": row['Code'] + market_suffix
            }
        return mapping
    except Exception:
        mapping["_ERROR_"] = True
        return mapping

KRX_DICT = get_krx_mapping()
if KRX_DICT.get("_ERROR_"):
    get_krx_mapping.clear()

# ─────────────────────────────────────────
# 일정 관리
# ─────────────────────────────────────────
def get_upcoming_events():
    events_path = os.path.join(os.path.dirname(__file__), "events.json")
    if not os.path.exists(events_path):
        return []
    
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception:
        return []

    now = get_kst_now().replace(tzinfo=None)
    upcoming = []
    for e in events:
        try:
            edate = datetime.datetime.strptime(e["date"], "%Y-%m-%d")
            days_left = (edate - now).days
            if 0 <= days_left <= 60:
                upcoming.append((e["date"], e["event"], e["impact"], days_left))
        except Exception:
            continue
            
    upcoming.sort(key=lambda x: x[3])
    return upcoming

# ─────────────────────────────────────────
# 매크로 지표
# ─────────────────────────────────────────
@st.cache_data(ttl=600)  # 기존 1800초에서 600초로 축소
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_real_cnn_fg():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://edition.cnn.com/",
        "Origin": "https://edition.cnn.com"
    }
    response = requests.get(url, headers=headers, timeout=5)
    if response.status_code != 200:
        return None, "API 차단됨", None
    data = response.json()
    current_score = round(data['fear_and_greed']['score'])
    rating = data['fear_and_greed']['rating'].title()
    hist_data = data['fear_and_greed_historical']['data']
    df_fg = pd.DataFrame(hist_data)
    df_fg['Date'] = pd.to_datetime(df_fg['x'], unit='ms')
    df_fg.set_index('Date', inplace=True)
    return current_score, rating, df_fg['y']

@st.cache_data(ttl=600)  # 기존 3600초에서 600초로 축소 (실시간성 확보)
def get_macro_charts():
    result = {}
    tickers = {
        "vix_10y": "^VIX", 
        "vix3m_10y": "^VIX3M", 
        "spy_10y": "SPY", 
        "hyg_10y": "HYG", 
        "ief_10y": "IEF",
        "rsp_10y": "RSP",
        "kospi_10y": "^KS11",
        "vkospi_10y": "^VKOSPI",
        "usdkrw_10y": "KRW=X"
    }
    for k, v in tickers.items():
        try: 
            # 재시도 로직을 내부에 감쌀 수도 있지만, 단일 종목 호출이므로 여기서 간단히 처리
            df = fetch_ticker_history(v, period="10y")
            if not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                df = df[~df.index.duplicated(keep='last')]
            result[k] = df
        except Exception:
            result[k] = pd.DataFrame()
    return result

@st.cache_data(ttl=1800)
def get_sector_baseline():
    benchmarks = {"S&P 500 (SPY)": "SPY", "반도체 (SOXX)": "SOXX", "유틸리티 (XLU)": "XLU"}
    res = {}
    for name, ticker in benchmarks.items():
        try:
            hist = fetch_ticker_history(ticker, period="3mo")['Close']
            res[name] = calc_rsi(hist, 14)
        except Exception:
            res[name] = None
    return res

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_ticker_history(ticker_str, period="1y"):
    return yf.Ticker(ticker_str).history(period=period)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_fdr_history(raw_code, start):
    return fdr.DataReader(raw_code, start=start)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_ticker_info(tk):
    """
    yfinance .info 방어 계층: rate limit(429) 시 빈 dict가 조용히 반환되는 것을
    '오류'로 승격시켜 지수 백오프 재시도를 유발한다. (가장 자주 병목되는 구간)
    """
    info = tk.info
    if not info or not isinstance(info, dict) or len(info) <= 2:
        raise ValueError("info 응답이 비어 있음 (rate limit 추정)")
    return info

# ─────────────────────────────────────────
# 개별 종목 데이터 (yfinance 병목 해결을 위한 retry 적용)
# ─────────────────────────────────────────
@st.cache_data(ttl=600) 
def get_stock_data(query, is_kr=False, fast_mode=False):
    base = {"Name": query, "error": None}
    try:
        kst_now = get_kst_now()
        start   = (kst_now - datetime.timedelta(days=365)).strftime('%Y-%m-%d')

        if is_kr:
            kr_info = KRX_DICT.get(str(query).strip().upper())
            if kr_info: raw_code, yf_code = kr_info["raw_code"], kr_info["yf_code"]
            else:        raw_code, yf_code = query, f"{query}.KS"
            hist = fetch_fdr_history(raw_code, start=start).dropna()
            tk   = yf.Ticker(yf_code)
            ticker_str = raw_code
        else:
            ticker_str = US_NAME_MAP.get(str(query).strip().upper(), query).upper()
            tk         = yf.Ticker(ticker_str)
            hist       = fetch_ticker_history(ticker_str, period="1y").dropna()

        # .info는 429가 가장 잘 터지는 구간 → 재시도 계층으로 감싸고,
        # 최종 실패해도 가격/기술 지표는 살리는 Graceful Degradation
        try:
            info = fetch_ticker_info(tk)
        except Exception:
            info = {}

        if hist.empty or len(hist) < 30:
            base["error"] = "데이터 부족"
            return base

        close = hist['Close']
        vol   = hist['Volume']
        price = float(close.iloc[-1])
        prev  = float(close.iloc[-2])

        high_52w  = float(close.max())
        low_52w   = float(close.min())
        w52_range = high_52w - low_52w
        w52_pos   = round((price - low_52w) / w52_range * 100, 1) if w52_range > 0 else 50.0
        gap_high  = round((price - high_52w) / high_52w * 100, 1)

        base["Price"]    = int(price) if is_kr else round(price, 2)
        base["Change"]   = round((price - prev) / prev * 100, 2)
        base["RSI_7"]    = calc_rsi(close, 7)
        base["RSI_14"]   = calc_rsi(close, 14)
        base["RSI_21"]   = calc_rsi(close, 21)
        base["W52_pos"]  = w52_pos
        base["Gap_High"] = gap_high
        base["MACD_dir"] = calc_macd(close)[1]

        ma5  = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        std  = close.rolling(20).std().iloc[-1]
        base["MA5"]       = ma5
        base["MA20"]      = ma20
        base["BB_upper"]  = ma20 + 2 * std
        base["BB_lower"]  = ma20 - 2 * std
        base["Vol_ratio"] = round(float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-2] * 100), 1)
        base["MA20_gap"]  = round((price - ma20) / ma20 * 100, 2)
        base["_ticker"]   = ticker_str

        t_eps = info.get('trailingEps')
        f_eps = info.get('forwardEps')
        is_turnaround = False
        if t_eps is not None and f_eps is not None:
            if float(t_eps) <= 0 and float(f_eps) > 0:
                is_turnaround = True
        base["Is_Turnaround"] = is_turnaround

        base.update({
            "MarketCap":       info.get('marketCap', 0),
            "PER":             info.get('trailingPE'),
            "Forward_PER":     info.get('forwardPE'),
            "Forward_EPS":     f_eps,
            "Earnings_Growth": info.get('earningsGrowth'),
            "PBR":             info.get('priceToBook'),
            "ROE":             info.get('returnOnEquity'),
            "Op_Margin":       info.get('operatingMargins'),
            # yfinance 최신 버전은 'pegRatio' 대신 'trailingPegRatio'를 반환 → 폴백 처리
            "PEG":             info.get('trailingPegRatio') or info.get('pegRatio'),
            "Rev_Growth":      info.get('revenueGrowth'),
        })

        base["Gross_Margin"] = info.get('grossMargins')
        
        fcf = info.get('freeCashflow')
        mcap = info.get('marketCap')
        shares = info.get('sharesOutstanding')
        
        base["FCF_Yield"] = (fcf / mcap) if fcf and mcap else None
        base["FCFPS"] = (fcf / shares) if fcf and shares else None
        
        rev_g = info.get('revenueGrowth')
        op_m = info.get('operatingMargins')
        if rev_g is not None and op_m is not None:
            base["Rule_of_40"] = (rev_g + op_m) * 100
        else:
            base["Rule_of_40"] = None
            
        base["EV_EBITDA"] = info.get('enterpriseToEbitda')
        ev = info.get('enterpriseValue')
        if ev and fcf and fcf > 0:
            base["EV_FCF"] = ev / fcf
        else:
            base["EV_FCF"] = None

        base["ROIC"] = None
        base["Buybacks"] = None
        for k in ["Earnings_Beat","Next_Earning","Short_Interest","Beta",
                  "Latest_News","Insider_Buy","Insider_Detail","Edgar_URL", "Risk_Grade"]:
            base[k] = "N/A"
        base["Insider_Detail"] = ""
        base["Edgar_URL"]      = ""

        if not fast_mode:
            try:
                inc = tk.financials
                bs = tk.balance_sheet
                cf = tk.cashflow

                if inc is not None and not inc.empty and bs is not None and not bs.empty:
                    op_inc = 0
                    if 'Operating Income' in inc.index: op_inc = inc.loc['Operating Income'].iloc[0]
                    elif 'Operating Income Loss' in inc.index: op_inc = inc.loc['Operating Income Loss'].iloc[0]
                    
                    pre_tax = inc.loc['Pretax Income'].iloc[0] if 'Pretax Income' in inc.index else 0
                    tax_prov = inc.loc['Tax Provision'].iloc[0] if 'Tax Provision' in inc.index else 0
                    tax_rate = tax_prov / pre_tax if pre_tax and pre_tax > 0 else 0.21

                    tot_assets = bs.loc['Total Assets'].iloc[0] if 'Total Assets' in bs.index else 0
                    cur_liab = 0
                    if 'Current Liabilities' in bs.index: cur_liab = bs.loc['Current Liabilities'].iloc[0]
                    elif 'Total Current Liabilities' in bs.index: cur_liab = bs.loc['Total Current Liabilities'].iloc[0]

                    inv_cap = tot_assets - cur_liab
                    if inv_cap > 0 and pd.notna(op_inc):
                        base["ROIC"] = (op_inc * (1 - tax_rate)) / inv_cap

                if cf is not None and not cf.empty:
                    for row_name in ['Repurchase Of Capital Stock', 'Repurchase Of Stock', 'Stock Repurchased']:
                        if row_name in cf.index:
                            val = cf.loc[row_name].iloc[0]
                            if pd.notna(val):
                                base["Buybacks"] = val
                                break
            except Exception:
                pass

            if not is_kr:
                try:
                    earns = tk.get_earnings_dates(limit=12)
                    beats, valid = 0, 0
                    if earns is not None and not earns.empty:
                        past = earns[earns.index < pd.Timestamp.now(tz='UTC')].head(8)
                        for _, row in past.iterrows():
                            rep = row.get('Reported EPS')
                            est = row.get('Estimate')
                            if pd.notna(rep) and pd.notna(est):
                                valid += 1
                                if rep > est: beats += 1
                        if valid > 0:
                            win_rate = (beats / valid) * 100
                            base["Earnings_Beat"] = f"{valid}전 {beats}승 ({win_rate:.0f}%)"
                        future = earns[earns.index > pd.Timestamp.now(tz='UTC')].sort_index()
                        if not future.empty:
                            base["Next_Earning"] = future.index[0].strftime('%Y-%m-%d')
                except Exception:
                    pass

                short_raw = info.get('shortPercentOfFloat')
                beta_raw = info.get('beta')
                base["Short_Interest"] = short_interest_label(short_raw)

                if beta_raw:
                    tag = "🎢 고변동성" if beta_raw >= 1.2 else ("🛡️ 방어적" if beta_raw <= 0.8 else "⚖️ 시장수준")
                    base["Beta"] = f"{beta_raw:.2f} ({tag})"

                base["Risk_Grade"] = get_comprehensive_risk_grade(short_raw, beta_raw)

                try:
                    news_data = tk.news
                    if news_data:
                        base["Latest_News"] = (
                            news_data[0].get('content', {}).get('title')
                            or news_data[0].get('title', 'N/A')
                        )
                except Exception:
                    pass

                status, detail, edgar_url = parse_insider(tk, ticker_str)
                base["Insider_Buy"]    = status
                base["Insider_Detail"] = detail
                base["Edgar_URL"]      = edgar_url

    except Exception as e:
        base["error"] = str(e)
    return base
