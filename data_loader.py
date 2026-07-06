import json
import os
import requests
import datetime
import numpy as np
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

# ─────────────────────────────────────────
# 🆕 VKOSPI 전용 로더 (야후 ^VKOSPI 상장폐지 처리 대응)
# 폴백 체인: ① yfinance → ② KRX 정보데이터시스템 직조회 → ③ KOSPI 실현변동성 프록시
# ─────────────────────────────────────────
KRX_DATA_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

def fetch_vkospi_krx(years=3):
    """
    KRX 정보데이터시스템(data.krx.co.kr)에서 VKOSPI(코스피200 변동성지수)를 직접 조회.
    지수 코드를 하드코딩하지 않고 파인더 API로 매번 자가 탐색 → KRX 개편에도 견고.
    WAF/네트워크 차단 시 예외를 던져 상위 폴백 체인이 이어받는다.
    """
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201030108",
    })
    # 세션 쿠키 부트스트랩
    # timeout=(연결, 읽기) — KRX WAF가 응답을 블랙홀시키는 경우에도 대시보드 로딩이
    # 최악 수 초 내로 끝나도록 짧게 제한 (실패 시 즉시 프록시 폴백)
    sess.get("https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201030108", timeout=(2, 3))

    # ① 지수 코드 자가 탐색
    finder = sess.post(KRX_DATA_URL, data={
        "bld": "dbms/COM/finder_equidx", "locale": "ko_KR", "searchText": "변동성",
    }, timeout=(2, 3)).json()
    cand = [b for b in finder.get("block1", []) if "변동성" in str(b.get("codeName", ""))]
    if not cand:
        raise ValueError("KRX에서 VKOSPI 지수 코드 미발견")
    b = cand[0]

    # ② 시세 조회
    end   = get_kst_now().strftime("%Y%m%d")
    start = (get_kst_now() - datetime.timedelta(days=365 * years)).strftime("%Y%m%d")
    res = sess.post(KRX_DATA_URL, data={
        "bld": "dbms/MDC/STAT/standard/MDCSTAT00301",
        "locale": "ko_KR",
        "indIdx":  b.get("group_code", ""),
        "indIdx2": b.get("short_code", ""),
        "strtDd": start, "endDd": end,
        "share": "2", "money": "3", "csvxls_isNo": "false",
    }, timeout=(2, 4)).json()
    rows = res.get("output", [])
    if not rows:
        raise ValueError("KRX VKOSPI 시세 응답 없음")

    df = pd.DataFrame(rows)
    df["Date"]  = pd.to_datetime(df["TRD_DD"], format="%Y/%m/%d", errors="coerce")
    df["Close"] = pd.to_numeric(df["CLSPRC_IDX"].astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=["Date", "Close"]).set_index("Date").sort_index()[["Close"]]
    if df.empty:
        raise ValueError("KRX VKOSPI 파싱 결과 없음")
    return df


def build_vkospi_proxy(kospi_df):
    """
    최후 폴백: KOSPI 실현변동성 프록시 (연율화 %, ×1.15 변동성 리스크 프리미엄 보정).
    VKOSPI는 KOSPI200 내재변동성이므로 스케일이 같아 기존 임계값(25/20/16) 그대로 유효.

    ⚠️ 후행성 완화: 균등가중 20일 std는 블랙스완 '첫날'의 충격이 1/20로 희석되어 반응이 느리다.
    → EWMA 변동성(RiskMetrics λ≈0.94)을 병행 계산해 둘 중 큰 값을 채택:
      공포는 빨리 오르고 천천히 식는 실제 변동성 지수의 거동을 모사.
    그래도 옵션 내재변동성(선행) 대비 본질적 후행성은 남으므로 UI에 프록시임을 명시한다.
    """
    if kospi_df is None or kospi_df.empty or len(kospi_df) < 25:
        return pd.DataFrame()
    close = kospi_df['Close'].replace(0, np.nan).dropna()  # 0.0 종가 글리치 제거
    rets = close.pct_change().clip(-0.15, 0.15)             # ±15% 초과 = 데이터 오류로 간주 (지수 역사상 최대 일간 변동 ~±12%)
    rets = rets.replace([np.inf, -np.inf], np.nan)

    rv20  = rets.rolling(20).std()                           # 일반 이동표준편차 (지연됨)
    rvewm = rets.ewm(alpha=0.06, min_periods=20).std()       # 반감기 0.94 수준의 지수 가중
    rv = pd.concat([rv20, rvewm], axis=1).max(axis=1) * np.sqrt(252) * 100
    rv = rv.clip(upper=95.0)                                 # VIX 스케일 상한 캡 (100↑는 의미 상실)
    return pd.DataFrame({"Close": rv}).dropna()


@st.cache_data(ttl=599)  # 캐시 무효화를 위해 ttl 1초 변경 (600 -> 599)
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

    # ── VKOSPI 3단 폴백 체인 ──
    vkospi_source = "yfinance (^VKOSPI)"
    if result.get("vkospi_10y", pd.DataFrame()).empty:
        try:
            vk = fetch_vkospi_krx()
            vk.index = pd.to_datetime(vk.index).normalize()
            result["vkospi_10y"] = vk
            vkospi_source = "KRX 정보데이터시스템 직조회"
        except Exception:
            pass
    if result.get("vkospi_10y", pd.DataFrame()).empty:
        proxy = build_vkospi_proxy(result.get("kospi_10y", pd.DataFrame()))
        if not proxy.empty:
            result["vkospi_10y"] = proxy
            vkospi_source = "프록시 (KOSPI 실현변동성 EWMA·20일 병행, 과거 수익률 기반 후행지표)"
        else:
            vkospi_source = "없음 (전체 소스 실패)"
    result["vkospi_source"] = vkospi_source

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
