import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import FinanceDataReader as fdr
import requests

st.set_page_config(page_title="11원칙 퀀트 대시보드 v22.0", page_icon="🧭", layout="wide")

# ─────────────────────────────────────────
# 한글 이름 → 티커 매핑
# ─────────────────────────────────────────
US_NAME_MAP = {
    "애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "구글": "GOOGL", "알파벳": "GOOGL",
    "아마존": "AMZN", "메타": "META", "테슬라": "TSLA", "브로드컴": "AVGO", "이튼": "ETN",
    "버티브": "VRT", "스타벅스": "SBUX", "넷플릭스": "NFLX", "팔란티어": "PLTR",
    "일라이릴리": "LLY", "코카콜라": "KO", "AMD": "AMD", "퀄컴": "QCOM", "인텔": "INTC", "TSMC": "TSM",
    "아이온큐": "IONQ", "소파이": "SOFI", "크라우드스트라이크": "CRWD", "스노우플레이크": "SNOW",
    "암": "ARM", "ARM": "ARM", "슈퍼마이크로": "SMCI", "슈마컴": "SMCI",
    "웨스턴디지털": "WDC", "샌디스크": "SNDK"
}

@st.cache_data(ttl=86400)
def get_krx_mapping():
    # 수동 알리아스 추가 (자주 검색되나 API 장애 시를 대비한 하드코딩 백업)
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
    except:
        # API 통신 실패 시 에러 플래그 추가 후 반환 (캐시 삭제용)
        mapping["_ERROR_"] = True
        return mapping

KRX_DICT = get_krx_mapping()
if KRX_DICT.get("_ERROR_"):
    # 실패한 결과가 24시간 동안 캐시되는 것을 방지하기 위해 즉시 캐시 삭제
    get_krx_mapping.clear()

def get_kst_now():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)

# ─────────────────────────────────────────
# 확정 일정 캘린더 모듈 (국민연금 리밸런싱, FOMC 등)
# ─────────────────────────────────────────
def get_upcoming_events():
    # 2026년 하반기 기준 가상의 확정 일정 캘린더 (D-Day 연산을 위함)
    events = [
        {"date": "2026-07-28", "event": "🇺🇸 미국 FOMC 금리결정", "impact": "글로벌 매크로 변동성 확대"},
        {"date": "2026-07-31", "event": "🇰🇷 국민연금(NPS) 자산배분 리밸런싱 및 결산", "impact": "국내 대형주 수급 변동 주의 (외국인 동반 매도시 지수 하방 압력)"},
        {"date": "2026-09-10", "event": "🇰🇷 한국 선물옵션 동시만기일 (네 마녀의 날)", "impact": "장 막판 프로그램 매물 출회 및 외인 수급 변동성 극대화"},
        {"date": "2026-09-16", "event": "🇺🇸 미국 FOMC 금리결정", "impact": "금리 점도표 발표, 글로벌 증시 방향성 결정"},
        {"date": "2026-09-18", "event": "🇺🇸 미국 선물옵션 동시만기일", "impact": "미국장 대규모 거래량 동반 변동성 확대"},
        {"date": "2026-12-10", "event": "🇰🇷 한국 선물옵션 동시만기일", "impact": "연말 배당락 전 대규모 수급 교차"},
    ]
    now = get_kst_now().replace(tzinfo=None) # 시간대 제거 후 비교
    upcoming = []
    for e in events:
        edate = datetime.datetime.strptime(e["date"], "%Y-%m-%d")
        days_left = (edate - now).days
        # 오늘 기준 60일 이내에 있는 이벤트만 추출
        if 0 <= days_left <= 60:
            upcoming.append((e["date"], e["event"], e["impact"], days_left))
    # D-Day 임박 순 정렬
    upcoming.sort(key=lambda x: x[3])
    return upcoming

# ─────────────────────────────────────────
# CNN F&G
# ─────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_real_cnn_fg():
    try:
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
    except:
        return None, "데이터 수집 오류", None

# ─────────────────────────────────────────
# 매크로 차트 데이터 수집 
# ─────────────────────────────────────────
@st.cache_data(ttl=3600)
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
            df = yf.Ticker(v).history(period="10y")
            if not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                df = df[~df.index.duplicated(keep='last')]
            result[k] = df
        except: 
            result[k] = pd.DataFrame()
    return result

# ─────────────────────────────────────────
# RSI & MACD 연산기
# ─────────────────────────────────────────
def calc_rsi(close, period=14):
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs    = avg_g / avg_l
    return round(float((100 - 100 / (1 + rs)).iloc[-1]), 2)

def get_rolling_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def calc_macd(close):
    if len(close) < 35:
        return None, "N/A"
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    hist = macd - macd.ewm(span=9, adjust=False).mean()
    return round(float(macd.iloc[-1]), 2), "🟢상승" if hist.iloc[-1] > 0 else "🔴하락"

# ─────────────────────────────────────────
# 🇺🇸 레이어 1: 미국 전용 위험 탐지기
# ─────────────────────────────────────────
def calculate_us_risk_radar(vix_hist, vix3m_hist, hyg_hist, ief_hist, spy_hist):
    alerts = []
    danger_count = 0

    curr_vix   = float(vix_hist['Close'].iloc[-1])  if not vix_hist.empty  else None
    curr_vix3m = float(vix3m_hist['Close'].iloc[-1]) if not vix3m_hist.empty else None
    if curr_vix and curr_vix3m:
        if curr_vix > curr_vix3m * 1.05:
            alerts.append(("🔴", f"VIX 백워데이션 발생 ({curr_vix:.1f} > {curr_vix3m:.1f}). 단기 패닉 초입."))
            danger_count += 2
        elif curr_vix > curr_vix3m:
            alerts.append(("🟠", f"VIX 백워데이션 진입 중. 예비 주시."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"VIX 콘탱고 정상. 시장 구조 안정."))

    if curr_vix:
        if curr_vix >= 30:
            alerts.append(("🔴", f"VIX {curr_vix:.1f} — 공포 확산 구간."))
            danger_count += 2
        elif curr_vix >= 22:
            alerts.append(("🟠", f"VIX {curr_vix:.1f} — 불안 상승 구간."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"VIX {curr_vix:.1f} — 평온 구간."))

    credit_danger = False
    if not hyg_hist.empty and not ief_hist.empty:
        try:
            df_c = pd.concat([hyg_hist['Close'], ief_hist['Close']], axis=1).ffill().dropna()
            if len(df_c) >= 50:
                df_c.columns = ['HYG', 'IEF']
                df_c['R'] = df_c['HYG'] / df_c['IEF']
                ma20 = float(df_c['R'].rolling(20).mean().iloc[-1])
                ma50 = float(df_c['R'].rolling(50).mean().iloc[-1])
                curr = float(df_c['R'].iloc[-1])
                if curr < ma50 * 0.97:
                    alerts.append(("🔴", f"신용 스프레드 위험 이탈. 기관 투매 감지."))
                    danger_count += 2
                    credit_danger = True
                elif curr < ma20:
                    alerts.append(("🟠", f"신용 스프레드 단기 이탈. 주시 필요."))
                    danger_count += 1
                    credit_danger = True
                else:
                    alerts.append(("🟢", "신용 스프레드 안정 (정배열)."))
        except:
            alerts.append(("⚪", "신용 스프레드 산출 불가."))

    # SPY 급락 교차 검증 로직 (원인 분석)
    if not spy_hist.empty and len(spy_hist) >= 6:
        spy_1d_ret = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-2]) - 1) * 100
        spy_5d_ret = (float(spy_hist['Close'].iloc[-1]) / float(spy_hist['Close'].iloc[-6]) - 1) * 100
        
        if spy_1d_ret <= -1.5 or spy_5d_ret <= -3.0:
            if credit_danger:
                alerts.append(("🚨", f"글로벌 킬 스위치 발동: SPY 급락({spy_1d_ret:.1f}%) & 신용 경색. 진짜 위기."))
                danger_count += 3
            else:
                alerts.append(("⚪", f"SPY 급락({spy_1d_ret:.1f}%) 발생, 단 신용 시장 평온. (단순 차익실현 추정)"))
        else:
            alerts.append(("🟢", f"SPY 단기 매크로 추세 안정적 ({spy_1d_ret:+.1f}%)."))

    if danger_count >= 5:
        grade = "🚨 글로벌 마스터 킬 스위치 작동 — 시스템적 유동성 위기."
        color = "#ff0000"
    elif danger_count >= 3:
        grade = "🔴 글로벌 위기 경보 — 폭락 초입 가능성."
        color = "#ff4b4b"
    elif danger_count >= 2:
        grade = "🟠 글로벌 주의 단계 — 신규 진입 자제."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 글로벌 관찰 단계 — 경미한 이상 신호."
        color = "#fcca46"
    else:
        grade = "🟢 글로벌 마스터 이상 없음 — 매크로 환경 정상."
        color = "#21c354"

    return grade, color, alerts

# ─────────────────────────────────────────
# 🔥 신규: 🇰🇷 레이어 1: 한국 전용 위험 탐지기
# ─────────────────────────────────────────
def calculate_kr_risk_radar(vkospi_hist, usdkrw_hist, kospi_hist):
    alerts = []
    danger_count = 0

    # 1. 환율 급변동 (외국인 자본 이탈 강력 프록시)
    if not usdkrw_hist.empty and len(usdkrw_hist) >= 20:
        curr_krw = float(usdkrw_hist['Close'].iloc[-1])
        krw_5d_ago = float(usdkrw_hist['Close'].iloc[-6])
        krw_surge = (curr_krw - krw_5d_ago) / krw_5d_ago * 100
        krw_rsi = calc_rsi(usdkrw_hist['Close'], 14)
        krw_ma20 = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
        
        # 민감도 상향: 5일 1.5% 급등 또는 MA20 상향 이탈
        if krw_surge >= 1.5 or (curr_krw > krw_ma20 and krw_rsi and krw_rsi >= 65):
            alerts.append(("🔴", f"환율 단기 폭등/추세이탈 (+{krw_surge:.1f}%, RSI {krw_rsi:.1f}) — 외국인 엑소더스 징후."))
            danger_count += 2
        elif krw_surge >= 0.8 or (krw_rsi and krw_rsi >= 55):
            alerts.append(("🟠", f"환율 상승세 (+{krw_surge:.1f}%) — 외국인 수급 악화 조기 경보."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"환율 안정적 ({curr_krw:,.1f}원) — 외인 수급 이탈 우려 낮음."))

    # 2. VKOSPI 급등 (국내 파생 하락 베팅)
    if not vkospi_hist.empty and len(vkospi_hist) >= 6:
        curr_vk = float(vkospi_hist['Close'].iloc[-1])
        vk_5d_ago = float(vkospi_hist['Close'].iloc[-6])
        vk_surge = (curr_vk - vk_5d_ago) / vk_5d_ago * 100 if vk_5d_ago > 0 else 0
        
        if curr_vk >= 25 or vk_surge >= 25:
            alerts.append(("🔴", f"VKOSPI 급등 ({curr_vk:.1f}, +{vk_surge:.1f}%) — 기관/외인 하락 헷지 증가."))
            danger_count += 2
        elif curr_vk >= 18 or vk_surge >= 15:
            alerts.append(("🟠", f"VKOSPI 불안 ({curr_vk:.1f}) — 파생 변동성 확대."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"VKOSPI 평온 ({curr_vk:.1f}) — 하방 압력 낮음."))

    # 3. KOSPI 단기 급락 (프로그램/기관 투매 프록시)
    if not kospi_hist.empty and len(kospi_hist) >= 6:
        k_5d_ret = (float(kospi_hist['Close'].iloc[-1]) / float(kospi_hist['Close'].iloc[-6]) - 1) * 100
        if k_5d_ret <= -4:
            alerts.append(("🔴", f"KOSPI 5일 급락 ({k_5d_ret:.1f}%) — 프로그램 및 동반 투매 감지."))
            danger_count += 1
        elif k_5d_ret <= -2:
            alerts.append(("🟠", f"KOSPI 5일 하락 ({k_5d_ret:.1f}%) — 단기 매도 우위."))
        else:
            alerts.append(("🟢", f"KOSPI 단기 추세 ({k_5d_ret:+.1f}%) — 안정적."))

    if danger_count >= 4:
        grade = "🔴 한국 위기 경보 — 외인 이탈 및 폭락 초입 우려."
        color = "#ff4b4b"
    elif danger_count >= 2:
        grade = "🟠 한국 주의 단계 — 수급/환율 불안정."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 한국 관찰 단계 — 경미한 수급 꼬임 감지."
        color = "#fcca46"
    else:
        grade = "🟢 한국 이상 없음 — 국내 수급 환경 안정적."
        color = "#21c354"

    return grade, color, alerts

# ─────────────────────────────────────────
# 진바닥 탐지기 (미국/한국)
# ─────────────────────────────────────────
def calculate_us_bottom_finder(spy_hist, vix_hist, cnn_score):
    score = 0
    details = []

    if spy_hist is None or spy_hist.empty:
        return 0, "데이터 부족", [], "알 수 없음"

    spy_close = spy_hist['Close']
    curr_spy  = float(spy_close.iloc[-1])
    high_252  = float(spy_close.rolling(252, min_periods=1).max().iloc[-1])
    drawdown  = ((curr_spy / high_252) - 1) * 100

    if drawdown > -5: market_phase = f"📈 고점권 (Drawdown {drawdown:.1f}%)"
    elif drawdown > -12: market_phase = f"📉 단기 조정 (Drawdown {drawdown:.1f}%)"
    elif drawdown > -20: market_phase = f"🟠 깊은 조정 (Drawdown {drawdown:.1f}%)"
    else: market_phase = f"🔴 약세장/폭락 진행 (Drawdown {drawdown:.1f}%)"

    if drawdown <= -25: score += 35; details.append(f"🟢 대세 하락장 낙폭 ({drawdown:.1f}%) [+35점]")
    elif drawdown <= -15: score += 22; details.append(f"🟢 깊은 조정 ({drawdown:.1f}%) [+22점]")
    elif drawdown <= -8: score += 10; details.append(f"🟡 단기 조정 ({drawdown:.1f}%) [+10점]")
    else: details.append(f"⚪ 고점 근처 ({drawdown:.1f}%) [+0점]")

    spy_rsi = calc_rsi(spy_close, 14)
    if spy_rsi:
        if spy_rsi <= 30: score += 20; details.append(f"🟢 SPY RSI 극단 과매도 ({spy_rsi:.1f}) [+20점]")
        elif spy_rsi <= 38: score += 12; details.append(f"🟢 SPY RSI 과매도 ({spy_rsi:.1f}) [+12점]")
        elif spy_rsi <= 45: score += 5;  details.append(f"🟡 SPY RSI 과매도 진입 ({spy_rsi:.1f}) [+5점]")
        else: details.append(f"⚪ SPY RSI 정상 ({spy_rsi:.1f}) [+0점]")

    curr_vix = float(vix_hist['Close'].iloc[-1]) if not vix_hist.empty else None
    if curr_vix:
        if curr_vix >= 40: score += 25; details.append(f"🟢 VIX 극단 패닉 ({curr_vix:.1f}) [+25점]")
        elif curr_vix >= 32: score += 20; details.append(f"🟢 VIX 패닉 투매 ({curr_vix:.1f}) [+20점]")
        elif curr_vix >= 26: score += 12; details.append(f"🟡 VIX 공포 확산 ({curr_vix:.1f}) [+12점]")
        elif curr_vix >= 22: score += 5;  details.append(f"🟡 VIX 상승 주의 ({curr_vix:.1f}) [+5점]")
        else: details.append(f"⚪ VIX 평온 ({curr_vix:.1f}) [+0점]")

    if cnn_score is not None:
        if cnn_score <= 15: score += 20; details.append(f"🟢 F&G 역사적 패닉 ({cnn_score}) [+20점]")
        elif cnn_score <= 25: score += 15; details.append(f"🟢 F&G 극단 공포 ({cnn_score}) [+15점]")
        elif cnn_score <= 35: score += 8;  details.append(f"🟡 F&G 공포 구간 ({cnn_score}) [+8점]")
        elif cnn_score <= 45: score += 3;  details.append(f"⚪ F&G 약한 공포 ({cnn_score}) [+3점]")
        else: details.append(f"⚪ F&G 중립~탐욕 ({cnn_score}) [+0점]")

    score = min(int(score), 100)

    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강력 매수 신호 (역사적 바닥 근접)"
    elif score >= 50: verdict = "🟢 분할 매수 구간 (역발상 타점)"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"

    return score, verdict, details, market_phase

def calculate_kr_bottom_finder(kospi_hist, vkospi_hist, usdkrw_hist):
    score = 0
    details = []
    max_possible_score = 100

    if kospi_hist is None or kospi_hist.empty:
        return 0, "데이터 부족", [], "알 수 없음"

    kospi_close = kospi_hist['Close']
    curr_kospi  = float(kospi_close.iloc[-1])
    high_252  = float(kospi_close.rolling(252, min_periods=1).max().iloc[-1])
    drawdown  = ((curr_kospi / high_252) - 1) * 100

    if drawdown > -5: market_phase = f"📈 고점권 (Drawdown {drawdown:.1f}%)"
    elif drawdown > -12: market_phase = f"📉 단기 조정 (Drawdown {drawdown:.1f}%)"
    elif drawdown > -20: market_phase = f"🟠 깊은 조정 (Drawdown {drawdown:.1f}%)"
    else: market_phase = f"🔴 약세장/폭락 진행 (Drawdown {drawdown:.1f}%)"

    if drawdown <= -20: score += 35; details.append(f"🟢 KOSPI 대세 하락장 ({drawdown:.1f}%) [+35점]")
    elif drawdown <= -12: score += 22; details.append(f"🟢 KOSPI 깊은 조정 ({drawdown:.1f}%) [+22점]")
    elif drawdown <= -7: score += 10; details.append(f"🟡 KOSPI 단기 조정 ({drawdown:.1f}%) [+10점]")
    else: details.append(f"⚪ 고점 근처 ({drawdown:.1f}%) [+0점]")

    kr_rsi = calc_rsi(kospi_close, 14)
    if kr_rsi:
        if kr_rsi <= 30: score += 20; details.append(f"🟢 KOSPI 극단 과매도 ({kr_rsi:.1f}) [+20점]")
        elif kr_rsi <= 40: score += 12; details.append(f"🟢 KOSPI 과매도 ({kr_rsi:.1f}) [+12점]")
        elif kr_rsi <= 45: score += 5;  details.append(f"🟡 KOSPI 과매도 진입 ({kr_rsi:.1f}) [+5점]")
        else: details.append(f"⚪ KOSPI RSI 정상 ({kr_rsi:.1f}) [+0점]")

    curr_vkospi = float(vkospi_hist['Close'].iloc[-1]) if not vkospi_hist.empty else None
    has_vkospi = False
    if curr_vkospi and not np.isnan(curr_vkospi):
        has_vkospi = True
        if curr_vkospi >= 25: score += 25; details.append(f"🟢 VKOSPI 패닉 투매 ({curr_vkospi:.1f}) [+25점]")
        elif curr_vkospi >= 20: score += 15; details.append(f"🟢 VKOSPI 공포 확산 ({curr_vkospi:.1f}) [+15점]")
        elif curr_vkospi >= 16: score += 5;  details.append(f"🟡 VKOSPI 상승 주의 ({curr_vkospi:.1f}) [+5점]")
        else: details.append(f"⚪ VKOSPI 평온 ({curr_vkospi:.1f}) [+0점]")
    else:
        max_possible_score -= 25
        details.append("⚪ VKOSPI 데이터 누락 (최종 점수에서 보정) [+0점]")

    if not usdkrw_hist.empty:
        krw_close = usdkrw_hist['Close']
        krw_rsi = calc_rsi(krw_close, 14)
        if krw_rsi:
            if krw_rsi <= 55: score += 20; details.append(f"🟢 환율 안정 및 원화 강세 ({krw_rsi:.1f}) [+20점]")
            elif krw_rsi <= 65: score += 10; details.append(f"🟡 환율 약세 구간 ({krw_rsi:.1f}) [+10점]")
            else: 
                details.append(f"🚨 환율 단기 폭등 위험 ({krw_rsi:.1f}) [+0점]")
                if krw_rsi > 70 and drawdown > -10:
                    score = min(score, 30)
                    details.append("💣 [Kill Switch] 코스피 낙폭 적은데 환율 초급등. 폭락 초입 가능성으로 30점 제한.")

    if not has_vkospi:
        score = int(score * (100.0 / 75.0))
        details.append("🔄 (VKOSPI 누락으로 남은 점수를 100점 만점 기준으로 환산 완료)")

    score = min(int(score), 100)

    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강력 매수 신호 (역사적 바닥 근접)"
    elif score >= 50: verdict = "🟢 분할 매수 구간 (역발상 타점)"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"

    return score, verdict, details, market_phase

def calculate_recovery_confirmation(rsp_hist, spy_hist, hyg_hist, ief_hist):
    signals = []
    recovery_score = 0

    if not rsp_hist.empty and not spy_hist.empty:
        try:
            df_b = pd.concat([rsp_hist['Close'], spy_hist['Close']], axis=1).ffill().dropna()
            df_b.columns = ['RSP', 'SPY']
            df_b['R'] = df_b['RSP'] / df_b['SPY']
            curr_r = float(df_b['R'].iloc[-1])
            ma50_r = float(df_b['R'].rolling(50, min_periods=1).mean().iloc[-1])
            if curr_r > ma50_r:
                pct_above = (curr_r - ma50_r) / ma50_r * 100
                signals.append(("🟢", f"시장 Breadth 회복 — 동일가중(RSP)이 MA50 +{pct_above:.1f}% 상회. 중소형주도 반등 동참."))
                recovery_score += 50
            else:
                pct_below = (ma50_r - curr_r) / ma50_r * 100
                signals.append(("🔴", f"Breadth 미회복 — 동일가중(RSP)이 MA50 -{pct_below:.1f}% 하회. 대형주만 오르는 편중 장세."))
        except:
            signals.append(("⚪", "Breadth 데이터 산출 불가."))

    credit_danger = False
    if not hyg_hist.empty and not ief_hist.empty:
        try:
            df_c = pd.concat([hyg_hist['Close'], ief_hist['Close']], axis=1).ffill().dropna()
            df_c.columns = ['HYG', 'IEF']
            df_c['R'] = df_c['HYG'] / df_c['IEF']
            curr  = float(df_c['R'].iloc[-1])
            ma20  = float(df_c['R'].rolling(20).mean().iloc[-1])
            ma50  = float(df_c['R'].rolling(50).mean().iloc[-1])
            if curr > ma20 > ma50:
                signals.append(("🟢", "신용시장 회복 확인 — HYG/IEF 정배열. 기관이 위험자산으로 복귀 중."))
                recovery_score += 50
            elif curr > ma50:
                signals.append(("🟡", "신용시장 부분 회복 — MA50 위. 아직 완전 정배열은 아님."))
                recovery_score += 25
            else:
                signals.append(("🔴", "신용시장 미회복 — 아직 기관 자금 복귀 확인 안 됨."))
        except:
            signals.append(("⚪", "Credit 데이터 산출 불가."))

    if recovery_score >= 100: verdict = "🟢 반등 신뢰도 높음 — Breadth + Credit 동시 회복"
    elif recovery_score >= 50: verdict = "🟡 반등 신뢰도 보통 — 일부만 회복"
    else: verdict = "🔴 반등 신뢰도 낮음 — 아직 회복 확인 안 됨"

    return verdict, signals, recovery_score

# ─────────────────────────────────────────
# 백테스트 
# ─────────────────────────────────────────
def run_historical_backtest(spy_hist, vix_hist, vix3m_hist):
    if any(df.empty for df in [spy_hist, vix_hist, vix3m_hist]):
        return None

    df = pd.concat([
        spy_hist['Close'], vix_hist['Close'], vix3m_hist['Close'],
    ], axis=1).ffill().dropna()

    if df.empty or len(df) < 252:
        return None

    df.columns = ['SPY', 'VIX', 'VIX3M']
    df['SPY_High_252'] = df['SPY'].rolling(252, min_periods=1).max()
    df['Drawdown']     = (df['SPY'] / df['SPY_High_252'] - 1) * 100
    df['RSI']          = get_rolling_rsi(df['SPY'], 14).fillna(50)
    df['Fwd_3M_Ret']   = (df['SPY'].shift(-63)  / df['SPY'] - 1) * 100
    df['Fwd_6M_Ret']   = (df['SPY'].shift(-126) / df['SPY'] - 1) * 100

    scores = []
    for _, row in df.iterrows():
        s = 0
        dd = row['Drawdown']
        rsi = row['RSI']
        vix = row['VIX']

        if dd <= -25:   s += 35
        elif dd <= -15: s += 22
        elif dd <= -8:  s += 10

        if rsi <= 30:   s += 20
        elif rsi <= 38: s += 12
        elif rsi <= 45: s += 5

        if vix >= 40:   s += 25
        elif vix >= 32: s += 20
        elif vix >= 26: s += 12
        elif vix >= 22: s += 5

        scores.append(min(int((s / 80.0) * 100), 100))

    df['Score'] = scores

    res_70 = df[df['Score'] >= 70].dropna(subset=['Fwd_3M_Ret'])
    res_50 = df[(df['Score'] >= 50) & (df['Score'] < 70)].dropna(subset=['Fwd_3M_Ret'])

    def _stat(sub):
        if len(sub) == 0:
            return {"발생 횟수": 0, "평균 3M 수익률": 0, "평균 6M 수익률": 0, "승률 3M": 0}
        return {
            "발생 횟수":    len(sub),
            "평균 3M 수익률": round(sub['Fwd_3M_Ret'].mean(), 2),
            "평균 6M 수익률": round(sub['Fwd_6M_Ret'].dropna().mean(), 2) if len(sub['Fwd_6M_Ret'].dropna()) > 0 else 0,
            "승률 3M":       round((sub['Fwd_3M_Ret'] > 0).mean() * 100, 1),
        }

    event_dates = {
        "코로나 바닥": "2020-03-23",
        "2022 약세장 바닥": "2022-10-13",
        "2018 12월 조정": "2018-12-24",
    }
    event_scores = {}
    for name, d in event_dates.items():
        try:
            dt = pd.Timestamp(d)
            closest = df.index[df.index.get_indexer([dt], method='nearest')[0]]
            if abs((closest - dt).days) <= 5:
                event_scores[name] = int(df.loc[closest, 'Score'])
            else:
                event_scores[name] = "데이터 외 구간"
        except:
            event_scores[name] = None

    return {
        "70점 이상 (강력 매수)":    _stat(res_70),
        "50~69점 (분할 매수)":      _stat(res_50),
        "주요 이벤트 점수":          event_scores,
        "score_series":             df[['Score', 'Drawdown']],
    }

# ─────────────────────────────────────────
# 현금흐름 및 자본효율성 요약 해석기
# ─────────────────────────────────────────
def get_cashflow_interpretation(d):
    gm = d.get('Gross_Margin')
    roic = d.get('ROIC')
    fcf_y = d.get('FCF_Yield')
    buybacks = d.get('Buybacks')
    
    texts = []
    if gm is not None:
        if gm >= 0.50: texts.append(f"✅ 압도적 마진율로 독점적 지위 증명 (매출총이익률 {gm*100:.1f}%)")
        elif gm <= 0.20: texts.append(f"⚠️ 원가 부담이 큰 박리다매 구조 (매출총이익률 {gm*100:.1f}%)")
            
    if roic is not None:
        if roic >= 0.10: texts.append(f"✅ 훌륭한 자본 배치로 돈이 돈을 버는 구조 (ROIC {roic*100:.1f}%)")
        elif roic < 0.05 and roic > 0: texts.append(f"⚠️ 투하자본 대비 실제 수익성은 다소 낮음 (ROIC {roic*100:.1f}%)")
        elif roic < 0: texts.append("🚨 투하자본 대비 적자 발생")
            
    if fcf_y is not None:
        if fcf_y >= 0.05: texts.append(f"✅ 현금 창출력 대비 주가가 싼 매력적인 구간 (FCF Yield {fcf_y*100:.1f}%)")
        elif fcf_y <= 0.02 and fcf_y > 0: texts.append(f"💡 현금 대비 주가에 프리미엄(기대감)이 반영된 성장주")
        elif fcf_y < 0: texts.append("🚨 잉여현금흐름 마이너스 (보유 현금 소진 중)")
            
    if buybacks is not None and buybacks != 0:
        texts.append("✅ 자사주 매입을 통한 주가 방어 및 주주환원 적극 진행 중")
        
    if not texts: return "해당 지표의 데이터가 충분하지 않아 해석이 보류되었습니다."
    return " / ".join(texts)

# ─────────────────────────────────────────
# 섹터 ETF 기준선 & 상대강도
# ─────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_sector_baseline():
    benchmarks = {"S&P 500 (SPY)": "SPY", "반도체 (SOXX)": "SOXX", "유틸리티 (XLU)": "XLU"}
    res = {}
    for name, ticker in benchmarks.items():
        try:
            hist = yf.Ticker(ticker).history(period="3mo")['Close']
            res[name] = calc_rsi(hist, 14)
        except:
            res[name] = None
    return res

def relative_strength_label(my_rsi, spy_rsi):
    if my_rsi is None or spy_rsi is None:
        return "N/A"
    gap = my_rsi - spy_rsi
    if my_rsi > 65 and spy_rsi > 65:
        return f"🔵 동반 과매수 (시장 전체 과열, 차이 {gap:+.0f})"
    if my_rsi < 35 and spy_rsi < 35:
        return f"🟠 동반 과매도 (시장 전체 하락, 차이 {gap:+.0f})"
    if gap >= 10:  return f"💪 강한 주도주 (SPY 대비 +{gap:.0f})"
    if gap >= 5:   return f"📈 주도주 (SPY 대비 +{gap:.0f})"
    if gap <= -10: return f"📉 강한 소외주 (SPY 대비 {gap:.0f})"
    if gap <= -5:  return f"⚠️ 소외주 (SPY 대비 {gap:.0f})"
    return f"⚖️ 시장 동기화 (차이 {gap:+.0f})"

# ─────────────────────────────────────────
# 공매도 및 종합 리스크 등급 해석 로직
# ─────────────────────────────────────────
def short_interest_label(short_val):
    if short_val is None: return "N/A"
    s_pct = short_val * 100
    if s_pct >= 20:   tag = "🔴 매우 높음"
    elif s_pct >= 10: tag = "🟠 높음"
    elif s_pct >= 5:  tag = "🟡 보통"
    else:             tag = "✅ 낮음"
    return f"{s_pct:.1f}% ({tag})"

def get_comprehensive_risk_grade(short_val, beta_val):
    if short_val is None or beta_val is None: return "N/A"
    s_pct = short_val * 100
    is_high_short = s_pct >= 5.0 
    is_high_beta = beta_val >= 1.2 
    
    if not is_high_short and not is_high_beta: return "🟢 안정형 — 방어적 투자에 적합"
    elif not is_high_short and is_high_beta: return "🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐"
    elif is_high_short and not is_high_beta: return "🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요"
    else: return "🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중"

# ─────────────────────────────────────────
# 내부자 거래 — 직급 파싱 + SEC EDGAR 링크 생성
# ─────────────────────────────────────────
TITLE_MAP = {
    "ceo": "CEO (최고경영자)", "chief executive": "CEO (최고경영자)",
    "president": "President (대표)", "cfo": "CFO (최고재무책임자)",
    "chief financial": "CFO (최고재무책임자)", "coo": "COO (최고운영책임자)",
    "chief operating": "COO (최고운영책임자)", "cto": "CTO (최고기술책임자)",
    "chief technology": "CTO (최고기술책임자)", "cso": "CSO (최고전략책임자)",
    "chief strategy": "CSO (최고전략책임자)", "cmo": "CMO (최고마케팅책임자)",
    "chief marketing": "CMO (최고마케팅책임자)", "cpo": "CPO (최고상품책임자)",
    "chief product": "CPO (최고상품책임자)", "executive vice president": "EVP (수석부사장)",
    "evp": "EVP (수석부사장)", "senior vice president": "SVP (선임부사장)",
    "svp": "SVP (선임부사장)", "vice president": "VP (부사장)",
    "general counsel": "GC (법무총괄)", "director": "이사 (Director)",
    "chairman": "이사회 의장 (Chairman)", "board": "이사회 멤버",
    "10%": "10% 이상 주요주주", "beneficial": "수익적 소유자",
}

def normalize_title(raw_title: str) -> str:
    if not raw_title: return "직함 미상"
    lower = raw_title.lower().strip()
    for key, label in TITLE_MAP.items():
        if key in lower: return label
    return raw_title.strip()

def get_edgar_link(ticker: str) -> str:
    return (f"https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&company={ticker}&type=4"
            f"&dateb=&owner=include&count=10&search_text=")

def parse_insider(tk, ticker_str: str):
    edgar_url = get_edgar_link(ticker_str)
    status    = "내역 없음"
    detail    = ""
    try:
        insider_trans = tk.insider_transactions
        if insider_trans is None or insider_trans.empty:
            return "내역 없음", "", edgar_url

        for idx, row in insider_trans.head(30).iterrows():
            row_dict = {k.lower(): v for k, v in row.to_dict().items()}
            row_str  = str(row_dict)

            is_buy = ("buy" in row_str.lower() or "purchase" in row_str.lower())
            is_sell_or_exercise = ("sale" in row_str.lower() or "sell" in row_str.lower() or 
                                   "exercise" in row_str.lower() or "tax" in row_str.lower())

            if is_buy and not is_sell_or_exercise:
                name = (row_dict.get('insider') or row_dict.get('name') or 
                        row_dict.get('filer') or "이름 미상")
                raw_title = (row_dict.get('title') or row_dict.get('relationship') or 
                             row_dict.get('position') or row_dict.get('role') or "")
                title = normalize_title(str(raw_title))
                shares = (row_dict.get('shares') or row_dict.get('qty') or 
                          row_dict.get('quantity') or "미상")
                value = (row_dict.get('value') or row_dict.get('transaction value') or None)

                date_str = (idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10])
                status = "🟢 매수 기록 있음"
                value_str = f" / 거래금액 ${value:,.0f}" if value and isinstance(value, (int, float)) else ""
                detail = (f"[{date_str}] {name} — {title}\n        순수 매수 {shares}주{value_str}")
                break 

        if status == "내역 없음":
            try:
                first = insider_trans.iloc[0]
                row_dict = {k.lower(): v for k, v in first.to_dict().items()}
                trans_type = (row_dict.get('transaction') or row_dict.get('text') or "거래 기록 있음 (매수 아님)")
                status = f"⚪ {str(trans_type)[:30]}"
            except:
                status = "내역 없음"

    except Exception as e:
        status = f"조회 불가 ({str(e)[:30]})"

    return status, detail, edgar_url

# ─────────────────────────────────────────
# 시그널 로직 (포트폴리오 장투용)
# ─────────────────────────────────────────
def get_ai_signal(d):
    rsi  = d.get('RSI_14')
    cp   = d.get('Price')
    ma20 = d.get('MA20')
    vol  = d.get('Vol_ratio')
    macd = d.get('MACD_dir') or ""
    roe  = d.get('ROE')
    op_m = d.get('Op_Margin')

    if rsi is None or cp is None or ma20 is None: return "⚪ 데이터 부족 (판단 보류)"

    rsi_f    = float(rsi)
    cp_f     = float(cp)
    ma20_f   = float(ma20)
    vol_f    = float(vol) if vol is not None else 100.0
    ma20_gap = (cp_f - ma20_f) / ma20_f * 100

    roe_f  = float(roe)  if roe  is not None else None
    op_m_f = float(op_m) if op_m is not None else None
    if roe_f is not None and op_m_f is not None:
        if roe_f < 0 and op_m_f < 0: return "⚫ 경고 (적자 기업)"

    if rsi_f >= 75 and ma20_gap > 15: return "🔵 과매수 (익절/관망)"
    if 60 <= rsi_f < 75 and cp_f > ma20_f and "상승" in macd and vol_f > 120: return "🚀 추세 탑승 (불타기)"
    if 45 <= rsi_f < 60 and cp_f >= ma20_f: return "🟢 얕은 눌림목 (분할매수)"
    if rsi_f < 45: return "🔥 바닥 줍줍 (적극매수)"
    return "🟡 방향성 탐색 (관망)"

def calculate_smart_target(d, ai_sig):
    cp       = d.get('Price')
    ma5      = d.get('MA5', cp)
    ma20     = d.get('MA20', cp)
    bb_upper = d.get('BB_upper', cp)
    bb_lower = d.get('BB_lower', cp)
    if "추세 탑승"  in ai_sig: return max(ma5, cp * 0.98), "5일선 지지"
    elif "눌림목"   in ai_sig: return ma20,     "20일선 스윙"
    elif "바닥 줍줍" in ai_sig: return bb_lower, "볼린저 하단"
    elif "과매수"   in ai_sig: return bb_upper,  "볼린저 상단"
    else: return "-", "홀딩(Wait)"

# 🔥 텐배거 로직 — 턴어라운드, 알짜 소부장, 그리고 Rule of 40 도입
def get_tenbagger_signal(d):
    mcap     = float(d.get('MarketCap') or 0)
    region   = d.get('Region')
    rev_g    = float(d.get('Rev_Growth') or 0)
    earn_g   = float(d.get('Earnings_Growth') or 0)
    peg      = float(d.get('PEG')        or 99)
    gap_high = float(d.get('Gap_High')   or 0)
    op_m     = d.get('Op_Margin')
    is_turnaround = d.get("Is_Turnaround", False)
    rule_40  = d.get("Rule_of_40")

    if region == "미국" and mcap >= 100_000_000_000:   return "-"
    if region == "한국" and mcap >= 10_000_000_000_000: return "-"
    
    # Rule of 40 달성 시 묻지도 따지지도 않고 강력한 가산점 및 예외 통과
    is_rule_40_passed = rule_40 is not None and rule_40 >= 40

    # 예외 조항: 매출 성장이 20% 미만이라도, 완벽한 턴어라운드거나 독점적 마진(20% 이상)이거나 Rule of 40 통과면 1차 통과
    if rev_g < 0.20:
        is_exception = False
        if is_turnaround:
            is_exception = True
        elif op_m is not None and float(op_m) >= 0.20:
            is_exception = True
        elif is_rule_40_passed:
            is_exception = True
            
        if not is_exception:
            return "-" 

    if gap_high < -35.0: return "-" 

    points = 0
    if rev_g >= 0.30: points += 1   
    if earn_g >= 0.30 or is_turnaround: points += 1    
    if 0 < peg <= 1.5: points += 1  
    if op_m is not None and float(op_m) >= 0.20: points += 1 # 독점적 마진 가산점
    if is_rule_40_passed: points += 2 # Rule of 40 달성 시 초강력 가산점
    
    if points >= 3: return "🔥 기관 최선호 대장주 (Rule of 40)" if is_rule_40_passed else "🔥 기관 최선호 대장주"
    if points >= 1: return "🌱 우량 고성장주 (Rule of 40)" if is_rule_40_passed else "🌱 우량 고성장주"
    return "-"

# ─────────────────────────────────────────
# 메인 데이터 수집
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
            hist = fdr.DataReader(raw_code, start=start).dropna()
            tk   = yf.Ticker(yf_code)
            info = tk.info
            ticker_str = raw_code
        else:
            ticker_str = US_NAME_MAP.get(str(query).strip().upper(), query).upper()
            tk         = yf.Ticker(ticker_str)
            hist       = tk.history(period="1y").dropna()
            info       = tk.info

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
            "PEG":             info.get('pegRatio'),
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
            except:
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
                except:
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
                except:
                    pass

                status, detail, edgar_url = parse_insider(tk, ticker_str)
                base["Insider_Buy"]    = status
                base["Insider_Detail"] = detail
                base["Edgar_URL"]      = edgar_url

    except Exception as e:
        base["error"] = str(e)
    return base

# ─────────────────────────────────────────
# 포맷 및 색상 맵핑
# ─────────────────────────────────────────
def fmt_mcap(mcap, region):
    if not mcap or mcap == 0: return "N/A"
    return f"${mcap/1e9:.1f}B" if region == "미국" else (
        f"{mcap/1e12:.2f}조 원" if mcap >= 1e12 else f"{mcap/1e8:.0f}억 원"
    )

def fmt_buyback(val, region):
    if val is None or pd.isna(val) or val == 0: return "N/A"
    val = abs(val) 
    return f"${val/1e9:.1f}B" if region == "미국" else (f"{val/1e12:.2f}조 원" if val >= 1e12 else f"{val/1e8:.0f}억 원")

def fmt_price(val, region):
    if val is None or val == "-": return "-"
    return f"{int(val):,}원" if region == "한국" else f"${float(val):,.2f}"

def fmt(val, sfx="", pfx="", dig=2, na="N/A"):
    if val is None or (isinstance(val, float) and np.isnan(val)) or val == "N/A":
        return na
    if isinstance(val, (int, float)):
        return f"{pfx}{val:.{dig}f}{sfx}"
    return f"{pfx}{val}{sfx}"

def pct(val):
    return fmt(float(val) * 100, "%", dig=1) if val is not None else "N/A"

def fmt_change(val):
    if val is None: return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}%"

def color_df(val):
    if not isinstance(val, str): return ''
    if val.endswith('%') and (val.startswith('+') or val.startswith('-')):
        try:
            num = float(val.replace('%','').replace('+',''))
            return 'color: #ff4b4b' if num > 0 else 'color: #0068c9' if num < 0 else ''
        except: pass
    if any(x in val for x in ["🔥 바닥 줍줍","🚀 추세 탑승","🚀 텐배거","🟢 매수 기록", "🔥 기관 최선호 대장주"]):
        return 'background-color: #ffcccc; font-weight: bold; color: black'
    if any(x in val for x in ["🟢 얕은 눌림목","🌱 폭발적 성장","💪","📈 주도주", "🟢 안정형", "🌱 우량 고성장주"]):
        return 'background-color: #ccffcc; font-weight: bold; color: black'
    if any(x in val for x in ["⚫ 경고","📉 강한 소외주", "🔴 고위험", "🔴 매우 높음"]):
        return 'background-color: #555555; font-weight: bold; color: white'
    if any(x in val for x in ["🟡 모멘텀형", "🟠 논란형", "🟠 높음", "🟡 보통"]):
        return 'background-color: #fff3cd; font-weight: bold; color: black'
    if any(x in val for x in ["🔵 과매수","🔵 동반 과매수"]):
        return 'color: blue; font-weight: bold'
    if "🐘 대형주" in val or "⚪ 데이터 부족" in val:
        return 'color: gray; font-style: italic'
    return ''

# ─────────────────────────────────────────
# UI — 전역 데이터 선초기화
# ─────────────────────────────────────────
st.title("🧭 11원칙 퀀트 트레이딩 대시보드 v22.0")
st.caption("v22.0: 글로벌 마스터 킬 스위치 (신용스프레드 교차 검증) + 환율 조기경보 탑재")

cnn_score, cnn_rating, cnn_history = get_real_cnn_fg()
sector_base = get_sector_baseline()
spy_rsi_val = sector_base.get("S&P 500 (SPY)")

macro_charts = get_macro_charts()
usd_krw      = macro_charts.get("usdkrw_10y", pd.DataFrame())

# 탭 구성
tab1, tab2, tab4, tab3, tab_port, tab5, tab_risk = st.tabs([
    "📊 실시간 포트폴리오",
    "🌐 매크로 & F&G Index",
    "🚀 오늘의 텐배거 레이더",
    "🤖 AI 참모 리포트",
    "💼 내 포트폴리오 장투 전략",
    "📖 11원칙 매매 가이드라인",
    "🚨 리스크 등급 가이드",
])

with tab_port:
    st.subheader("💼 내 포트폴리오 장투 전략 분석 (1~2년 기준)")
    st.caption("보유 종목과 매수가를 입력하면 현재 손익 현황 + 11원칙 종합평가 + AI 전달용 장투 전략 리포트를 생성합니다.")

    st.markdown("#### 📝 보유 종목 입력")
    st.info(
        "**입력 형식:** 종목명:매수가 (쉼표로 구분)\n\n"
        "🇺🇸 미국: `브로드컴:320.5, 버티브:250, TSMC:180`\n\n"
        "🇰🇷 한국: `LS ELECTRIC:185000, 피에스케이홀딩스:120000`"
    )

    col_us, col_kr = st.columns(2)
    port_us_raw = col_us.text_input("🇺🇸 미국 보유 종목 (달러 매수가)", "브로드컴:320.5, 버티브:250, TSMC:180")
    port_kr_raw = col_kr.text_input("🇰🇷 한국 보유 종목 (원화 매수가)", "LS ELECTRIC:185000")

    def parse_portfolio_input(raw: str, region: str):
        items = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if ":" not in chunk:
                continue
            parts = chunk.rsplit(":", 1)
            if len(parts) == 2:
                name = parts[0].strip()
                try:
                    price = float(parts[1].strip().replace(",", ""))
                    items.append((name, price, region))
                except ValueError:
                    pass
        return items

    port_items = (
        parse_portfolio_input(port_us_raw, "미국") +
        parse_portfolio_input(port_kr_raw, "한국")
    )

    if st.button("🔍 장투 전략 분석 시작", type="primary"):
        if not port_items:
            st.warning("종목을 올바른 형식으로 입력해 주세요.")
        else:
            port_data = []
            with st.spinner("보유 종목 데이터 수집 중... (재무제표 교차 검증 중)"):
                for name, buy_price, region in port_items:
                    d = get_stock_data(name, is_kr=(region == "한국"), fast_mode=False)
                    d["Region"]    = region
                    d["BuyPrice"]  = buy_price
                    if not d.get("error"):
                        port_data.append(d)
                    else:
                        st.warning(f"⚠️ '{name}' 데이터 조회 실패: {d.get('error')}")

            if not port_data:
                st.error("조회된 종목이 없습니다. 종목명을 확인해 주세요.")
            else:
                st.markdown("---")
                st.markdown("### 📊 1. 현재 손익 현황")

                pnl_rows = []
                for d in port_data:
                    buy_p   = d["BuyPrice"]
                    cur_p   = d.get("Price")
                    region  = d["Region"]
                    if cur_p is None:
                        continue
                    cur_p_f = float(cur_p)
                    pnl_pct = round((cur_p_f - buy_p) / buy_p * 100, 2)
                    pnl_sign = "+" if pnl_pct >= 0 else ""

                    ma20    = d.get("MA20")
                    bb_low  = d.get("BB_lower")

                    def _dist(ref):
                        if ref is None: return "N/A"
                        return f"{round((cur_p_f - float(ref)) / float(ref) * 100, 1):+.1f}%"

                    pnl_rows.append({
                        "종목":        d["Name"],
                        "지역":        "🇺🇸" if region == "미국" else "🇰🇷",
                        "매수가":      f"${buy_p:,.2f}" if region == "미국" else f"{int(buy_p):,}원",
                        "현재가":      fmt_price(cur_p, region),
                        "수익률":      f"{pnl_sign}{pnl_pct:.2f}%",
                        "20일선 위치": _dist(ma20),
                        "볼밴 하단까지": _dist(bb_low),
                        "52주 위치":   f"{d.get('W52_pos', 'N/A')}%",
                    })

                pnl_df = pd.DataFrame(pnl_rows).set_index("종목")

                def color_pnl(val):
                    if isinstance(val, str) and val.endswith('%') and (val.startswith('+') or val.startswith('-') or (val[0].isdigit())):
                        try:
                            num = float(val.replace('%','').replace('+',''))
                            if num > 0:   return 'color: #ff4b4b; font-weight: bold'
                            elif num < 0: return 'color: #0068c9; font-weight: bold'
                        except: pass
                    return ''

                st.dataframe(pnl_df.style.map(color_pnl, subset=["수익률","20일선 위치","볼밴 하단까지"]), use_container_width=True)

                st.markdown("---")
                st.markdown("### 🧭 2. 종목별 종합 분석")

                for d in port_data:
                    buy_p   = d["BuyPrice"]
                    cur_p   = d.get("Price")
                    region  = d["Region"]
                    if cur_p is None: continue

                    cur_p_f  = float(cur_p)
                    pnl_pct  = round((cur_p_f - buy_p) / buy_p * 100, 2)
                    ai_sig   = get_ai_signal(d)
                    tb_sig   = get_tenbagger_signal(d) 
                    rs_txt   = relative_strength_label(d.get("RSI_14"), spy_rsi_val)
                    risk_g   = d.get("Risk_Grade", "N/A")
                    rsi14    = d.get("RSI_14")
                    w52      = d.get("W52_pos")

                    fund_score = 0
                    fund_detail = []
                    rev_g  = d.get("Rev_Growth") or 0
                    op_m   = d.get("Op_Margin")  or 0
                    roe_v  = d.get("ROE")         or 0
                    peg_v  = d.get("PEG")         or 99
                    per_v  = d.get("PER")
                    
                    gap_high = float(d.get("Gap_High") or 0)
                    is_turnaround = d.get("Is_Turnaround", False)

                    if float(rev_g) >= 0.20:
                        fund_score += 1; fund_detail.append("✅ 매출성장 20%↑")
                    else:
                        fund_detail.append(f"❌ 매출성장 미달 ({pct(rev_g)})")

                    if float(op_m) >= 0.10:
                        fund_score += 1; fund_detail.append("✅ 영업이익률 10%↑")
                    else:
                        if is_turnaround:
                            fund_score += 1; fund_detail.append("🔄 흑자전환 기대 (Forward EPS 턴어라운드)")
                        else:
                            fund_detail.append(f"❌ 영업이익률 미달 ({pct(op_m)})")

                    if float(roe_v) >= 0.05:
                        fund_score += 1; fund_detail.append("✅ ROE 5%↑")
                    else:
                        fund_detail.append(f"❌ ROE 미달 ({pct(roe_v)})")

                    if 0 < float(peg_v) <= 1.5:
                        fund_score += 1; fund_detail.append(f"✅ PEG {float(peg_v):.2f} (저평가)")
                    else:
                        fund_detail.append(f"⚠️ PEG {fmt(peg_v, dig=2)} (고평가 or N/A)")

                    if per_v and float(per_v) < 30:
                        fund_score += 1; fund_detail.append(f"✅ PER {float(per_v):.1f} (합리적)")
                    else:
                        fund_detail.append(f"⚠️ PER {fmt(per_v, dig=1)} (높음 or N/A)")

                    hold_signals = []
                    if fund_score >= 4: hold_signals.append("💎 펀더멘탈 우수")
                    elif fund_score >= 2: hold_signals.append("⚠️ 펀더멘탈 보통")
                    else: hold_signals.append("🚨 펀더멘탈 약함")

                    if rsi14 and float(rsi14) < 45: hold_signals.append("🔥 기술적 저점 구간")
                    elif rsi14 and float(rsi14) > 70: hold_signals.append("⚠️ 기술적 과매수")

                    if w52 and float(w52) <= 30: hold_signals.append("📍 52주 하단권 (매수 기회)")
                    
                    if gap_high < -30.0 and cnn_score is not None and cnn_score <= 25:
                        hold_signals.append("🚨 위기 투매 발생 (11원칙 낙폭 과대 줍줍 구간)")

                    if d.get("Insider_Buy") == "🟢 매수 기록 있음": hold_signals.append("🟢 내부자 매수 확인")

                    if pnl_pct >= 20: hold_signals.append("💰 수익 구간 (일부 익절 고려)")
                    elif pnl_pct <= -15: hold_signals.append("🔻 손실 구간 (손절 or 물타기 검토)")

                    if fund_score >= 3 and (rsi14 is None or float(rsi14) < 70):
                        lt_verdict = "🟢 장투 유지 적합"
                        verdict_color = "#ccffcc"
                    elif fund_score >= 2 and pnl_pct > -20:
                        lt_verdict = "🟡 조건부 유지 (펀더멘탈 모니터링 필요)"
                        verdict_color = "#fff9cc"
                    else:
                        lt_verdict = "🔴 재검토 필요 (펀더멘탈 약화 or 손실 심화)"
                        verdict_color = "#ffdddd"

                    with st.expander(
                        f"{'🇺🇸' if region=='미국' else '🇰🇷'} **{d['Name']}** | "
                        f"매수 {f'${buy_p:,.2f}' if region=='미국' else f'{int(buy_p):,}원'} → "
                        f"현재 {fmt_price(cur_p, region)} | "
                        f"수익률 {'+' if pnl_pct>=0 else ''}{pnl_pct:.2f}% | {lt_verdict}",
                        expanded=True
                    ):
                        st.markdown(
                            f"<div style='background:{verdict_color};padding:10px;border-radius:8px;"
                            f"font-size:16px;font-weight:bold;text-align:center;'>{lt_verdict}</div>",
                            unsafe_allow_html=True
                        )
                        st.markdown("")

                        c_left, c_right = st.columns(2)
                        with c_left:
                            st.markdown("**📋 펀더멘탈 체크 (11원칙)**")
                            for item in fund_detail:
                                st.markdown(f"- {item}")
                            st.markdown(f"**→ 펀더멘탈 점수: {fund_score}/5**")
                            
                            st.markdown("")
                            st.markdown("**💡 현금흐름 & 자본 효율성 (Quality)**")
                            interp_text = get_cashflow_interpretation(d)
                            for chunk in interp_text.split(" / "):
                                st.markdown(f"- {chunk}")

                        with c_right:
                            st.markdown("**📡 기술·리스크 종합 신호**")
                            for sig in hold_signals:
                                st.markdown(f"- {sig}")
                            st.markdown(f"- 시장대비 강도: {rs_txt}")
                            st.markdown(f"- 종합 리스크: {risk_g}")
                            st.markdown(f"- 매매 시그널: {ai_sig}")
                            st.markdown(f"- 선행 성장성: 예상 성장률 {pct(d.get('Earnings_Growth'))} / Fwd PER {fmt(d.get('Forward_PER'), dig=1)}")

                        news = d.get("Latest_News", "N/A")
                        if news and news != "N/A":
                            st.markdown(f"**📰 최신 뉴스:** {news[:100]}...")

                        ne = d.get("Next_Earning", "N/A")
                        if ne and ne != "N/A":
                            try:
                                days = (datetime.datetime.strptime(ne, "%Y-%m-%d") - datetime.datetime.now()).days
                                if 0 <= days <= 30:
                                    st.warning(f"📅 실적 발표 {days}일 후 ({ne}) — 발표 전후 변동성 확대 가능")
                                else:
                                    st.caption(f"📅 다음 실적 발표: {ne}")
                            except:
                                st.caption(f"📅 다음 실적 발표: {ne}")

                st.markdown("---")
                st.markdown("### 🤖 3. AI 전달용 장투 전략 리포트")
                st.caption("아래 텍스트를 복사하여 챗봇에 붙여넣으면 더욱 완벽한 분석을 받을 수 있습니다.")

                now_str = get_kst_now().strftime('%Y-%m-%d %H:%M KST')
                port_lines = [
                    f"[내 포트폴리오 장투 전략 분석 요청] ({now_str})",
                    f"투자 기간 목표: 1~2년 (장기투자)",
                    f"현재 시장: CNN F&G {cnn_score} ({cnn_rating}), SPY RSI {fmt(spy_rsi_val, dig=1)}",
                    "",
                    "【보유 종목 현황】",
                ]
                for d in port_data:
                    buy_p  = d["BuyPrice"]
                    cur_p  = d.get("Price")
                    region = d["Region"]
                    if cur_p is None: continue
                    pnl_pct = round((float(cur_p) - buy_p) / buy_p * 100, 2)
                    ai_sig  = get_ai_signal(d)
                    risk_g  = d.get("Risk_Grade", "N/A")
                    rsi14   = d.get("RSI_14")
                    w52     = d.get("W52_pos")

                    port_lines += [
                        f"",
                        f"▶ {d['Name']} ({region})",
                        f"  - 매수가: {'$' if region=='미국' else ''}{buy_p:,.2f}{'원' if region=='한국' else ''}",
                        f"  - 현재가: {fmt_price(cur_p, region)} | 수익률: {'+' if pnl_pct>=0 else ''}{pnl_pct:.2f}%",
                        f"  - 펀더멘탈: 매출성장 {pct(d.get('Rev_Growth'))} | 매출총이익률 {pct(d.get('Gross_Margin'))} | 영업이익률 {pct(d.get('Op_Margin'))}",
                        f"  - 자본/현금: ROIC {pct(d.get('ROIC'))} | ROE {pct(d.get('ROE'))} | FCF Yield {pct(d.get('FCF_Yield'))} | 자사주매입 {fmt_buyback(d.get('Buybacks'), d['Region'])}",
                        f"  - 밸류에이션: PER {fmt(d.get('PER'),dig=1)} | Fwd PER {fmt(d.get('Forward_PER'),dig=1)} | PEG {fmt(d.get('PEG'),dig=2)} | PBR {fmt(d.get('PBR'),dig=2)}",
                        f"  - 기술/리스크: RSI(14일) {fmt(rsi14,dig=1)} | 52주 위치 {w52}% | 리스크 {risk_g} | 내부자 {d.get('Insider_Buy','N/A')}",
                        f"  - 어닝: {d.get('Earnings_Beat','N/A')} | 다음실적일: {d.get('Next_Earning','N/A')}",
                    ]

                port_lines += [
                    "",
                    "【장투 전략 분석 요청】",
                    "위 보유 종목들에 대해 1~2년 장기투자 관점으로 다음을 심층 분석해 줘.",
                    "",
                    "1. [가치와 성장 듀얼 분석 (Turnaround & Bubble Check)]",
                    "   - 각 종목의 '과거 영업이익률/PER'과 '미래 예상 이익성장률/Forward PER/PEG'를 교차 비교해 진짜 성장과 가짜 거품을 구별해 줘.",
                    "",
                    "2. [현금흐름 및 자본 효율성 (Quality Check)]",
                    "   - FCF Yield, ROIC, 매출총이익률(Gross Margin)을 분석하여 기업의 실제 현금 창출력과 해자(Moat)를 평가해 줘.",
                    "   - 경영진의 자신감을 나타내는 '자사주 매입' 내역과 '내부자 매수' 여부를 연계해 수급 안정성을 확인해 줘.",
                    "",
                    "3. [최종 매매 시나리오 제안]",
                    "   - 현재 손실/수익률과 시장 상황(F&G, SPY RSI)을 종합하여 지금 당장 '적극 매수(물타기)', '관망(타점 대기)', '비중 축소' 해야 할 종목들을 분류하고 구체적인 액션 플랜을 제시해 줘."
                ]

                st.code("\n".join(port_lines), language="text")

with tab5:
    st.header("📖 11원칙 퀀트 매매 가이드라인 (오리지널 철학)")
    st.markdown("""
이 대시보드는 사용자님의 정통 가치투자 철학(위기 줍줍, 턴어라운드)과 기계적인 퀀트 필터링을 결합한 하이브리드 시스템입니다.

**[ 펀더멘탈: 실적과 턴어라운드 ]**
- **1원칙 (3개년 우상향):** 매출 and 영업이익 지속 상승.
- **2원칙 (시가총액 비교):** 시장/섹터 대비 시총 규모가 적정하게 낮을 것.
- **3원칙 (턴어라운드 기대):** 현재 마진이 낮아도 미래 개선이 뚜렷하면 투자 가능.
- **4원칙 (비즈니스 모델):** 단독 매출인지, 연결/종속 업체인지 파악하고 시장 점유율 이해.

**[ 투자 시계열과 위기 관리 ]**
- **5원칙 (3년 장기 투자):** 수확은 3년 뒤. 일부만 현금화하여 재투자 비율 스스로 설정.
- **6원칙 (글로벌 위기 줍줍):** 시장 붕괴 고점 대비 20~30% 하락 시 분할 매수, 50% 밑이면 과감히 매수.
- **7원칙 (하락장 리밸런싱):** 시장 전체가 하락할 때 기존 비중 조절 및 신규 종목 편입.
    """)

with tab_risk:
    st.header("🚨 공매도 & 변동성(Beta) 종합 리스크 가이드")
    st.markdown("""
    | 공매도 비율 | Beta (변동성) | 종합 리스크 등급 및 해석 |
    | :--- | :--- | :--- |
    | 낮음 (5% 미만) | 낮음 (1.2 미만) | **🟢 안정형 — 방어적 투자에 적합** |
    | 낮음 (5% 미만) | 높음 (1.2 이상) | **🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐** |
    | 높음 (5% 이상) | 낮음 (1.2 미만) | **🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요** |
    | 높음 (5% 이상) | 높음 (1.2 이상) | **🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중** |
    """)

with tab2:
    st.subheader("🌐 글로벌 매크로 및 시장 심리")

    vix_10y = macro_charts.get("vix_10y", pd.DataFrame())
    vix3m_10y = macro_charts.get("vix3m_10y", pd.DataFrame())
    spy_10y = macro_charts.get("spy_10y", pd.DataFrame())
    hyg_10y = macro_charts.get("hyg_10y", pd.DataFrame())
    ief_10y = macro_charts.get("ief_10y", pd.DataFrame())
    rsp_10y = macro_charts.get("rsp_10y", pd.DataFrame())
    kospi_10y = macro_charts.get("kospi_10y", pd.DataFrame())
    vkospi_10y = macro_charts.get("vkospi_10y", pd.DataFrame())

    current_vix, vix_change = "N/A", 0
    if not vix_10y.empty:
        current_vix = round(float(vix_10y['Close'].iloc[-1]), 2)
        vix_change  = round(((current_vix - float(vix_10y['Close'].iloc[-2])) / float(vix_10y['Close'].iloc[-2])) * 100, 2)

    current_spy, spy_change = "N/A", 0
    if not spy_10y.empty:
        current_spy = round(float(spy_10y['Close'].iloc[-1]), 2)
        spy_change  = round(((current_spy - float(spy_10y['Close'].iloc[-2])) / float(spy_10y['Close'].iloc[-2])) * 100, 2)
        
    current_vkospi = "N/A"
    if not vkospi_10y.empty:
        current_vkospi = round(float(vkospi_10y['Close'].iloc[-1]), 2)

    col1, col2, col3, col4 = st.columns(4)
    if not usd_krw.empty:
        curr_usdkrw = round(float(usd_krw['Close'].iloc[-1]), 2)
        usdkrw_change = round(((curr_usdkrw - float(usd_krw['Close'].iloc[-2])) / float(usd_krw['Close'].iloc[-2])) * 100, 2)
        col1.metric("환율 (USD/KRW)", f"{curr_usdkrw:,.2f} 원", f"{usdkrw_change:+.2f}%")
    else:
        col1.metric("환율 (USD/KRW)", "N/A", "N/A")
        
    col2.metric("미국 VIX / 한국 VKOSPI", f"{current_vix} / {current_vkospi}", f"{vix_change}%", delta_color="inverse")
    col3.metric("S&P 500 (SPY)", f"${current_spy:,.2f}" if current_spy != "N/A" else "N/A", f"{spy_change:+.2f}%" if current_spy != "N/A" else "N/A")
    if cnn_score is not None:
        if cnn_score <= 25:   fg_color, fg_stat = "🔴", "극단적 공포"
        elif cnn_score <= 45: fg_color, fg_stat = "🟠", "공포"
        elif cnn_score <= 55: fg_color, fg_stat = "🟡", "중립"
        elif cnn_score <= 75: fg_color, fg_stat = "🟢", "탐욕"
        else:                 fg_color, fg_stat = "🟢", "극단적 탐욕"
        col4.metric("CNN Fear & Greed", f"{cnn_score} / 100", f"{fg_color} {fg_stat}")
    else:
        col4.metric("CNN Fear & Greed", "N/A", cnn_rating)

    st.divider()
    st.markdown("#### 🧭 시장 진단 시스템 v22.0 — 글로벌 통합 매크로 구조")
    st.info(
        "**📌 글로벌 킬 스위치 시스템:**\n\n"
        "**[마스터 레이어] 미국 글로벌 매크로** — 전 세계 자본 시장의 유동성을 대변하는 신용 스프레드와 VIX, SPY 추세를 교차 검증합니다. "
        "단순 차익 실현이 아닌 '시스템 위기'로 판독되면 킬 스위치가 작동합니다.\n\n"
        "**[종속 레이어] 한국 수급 탐지기** — 글로벌이 평온해도, 한국 시장 내 외국인 자본 이탈(환율 발작, 파생 베팅)을 조기 경보합니다."
    )

    # ── 레이어 1: 위험 탐지기 (미국 마스터 / 한국 보조) ──
    st.markdown("##### 🚨 글로벌 매크로 & 로컬 수급 위험 탐지기")
    us_risk_grade, us_risk_color, us_risk_alerts = calculate_us_risk_radar(vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y)
    kr_risk_grade, kr_risk_color, kr_risk_alerts = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

    st.markdown(f"<div style='background:{us_risk_color}22; border-left: 6px solid {us_risk_color}; padding:15px; border-radius:8px; font-weight:bold; font-size:1.1em; margin-bottom:10px;'>🇺🇸 [글로벌 마스터] {us_risk_grade}</div>", unsafe_allow_html=True)
    for icon, msg in us_risk_alerts:
        st.markdown(f"<div style='font-size:0.95em; margin-left:15px; margin-bottom:5px;'>{icon} {msg}</div>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown(f"<div style='background:{kr_risk_color}22; border-left: 4px solid {kr_risk_color}; padding:10px; border-radius:6px; font-weight:bold; margin-bottom:10px;'>🇰🇷 [로컬 종속 레이어] {kr_risk_grade}</div>", unsafe_allow_html=True)
    for icon, msg in kr_risk_alerts:
        st.markdown(f"<div style='font-size:0.9em; margin-left:15px; margin-bottom:3px;'>{icon} {msg}</div>", unsafe_allow_html=True)

    # ── 확정 일정 캘린더 모듈 (점수 미반영) ──
    events = get_upcoming_events()
    if events:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("##### 📅 주요 시장 이벤트 캘린더 (확정 일정)")
        st.caption("※ 아래 이벤트는 수급과 변동성을 키울 수 있는 확정된 일정입니다. (점수 미반영 / 참고용)")
        for date_str, event_name, impact, d_left in events:
            if d_left == 0:
                badge = "🔥 D-Day"
            else:
                badge = f"⏳ D-{d_left}"
            st.info(f"**[{badge}] {date_str}** : {event_name} — *{impact}*")

    st.divider()

    # ── 레이어 2: 바닥 탐지기 ──
    st.markdown("##### 📉 레이어 2: 바닥 탐지기 (이 하락이 바닥인가?)")
    
    us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)
    kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)
    
    us_color = "#21c354" if us_score >= 70 else "#fcca46" if us_score >= 50 else "#aaaaaa"
    kr_color = "#21c354" if kr_score >= 70 else "#fcca46" if kr_score >= 50 else "#aaaaaa"

    b_col1, b_col2 = st.columns(2)
    with b_col1:
        st.markdown(f"**🇺🇸 미국 진바닥 확률 (US Market)**")
        st.markdown(
            f"<div style='text-align:center; padding:20px; border-radius:10px; border:2px solid {us_color}; margin-bottom: 10px;'>"
            f"<h1 style='margin:0; font-size:3em; color:{us_color};'>{us_score}%</h1>"
            f"<h4 style='margin:0;'>{us_verdict}</h4>"
            f"<p style='margin-top:15px; font-size:18px; font-weight:bold; color:#555;'>현재 국면: {us_phase}</p>"
            f"</div>", unsafe_allow_html=True
        )
        with st.expander("🔍 미국장 연산 근거 (Drawdown + RSI + VIX + CNN)"):
            for detail in us_details: st.markdown(f"- {detail}")

    with b_col2:
        st.markdown(f"**🇰🇷 한국 진바닥 확률 (KOSPI)**")
        st.markdown(
            f"<div style='text-align:center; padding:20px; border-radius:10px; border:2px solid {kr_color}; margin-bottom: 10px;'>"
            f"<h1 style='margin:0; font-size:3em; color:{kr_color};'>{kr_score}%</h1>"
            f"<h4 style='margin:0;'>{kr_verdict}</h4>"
            f"<p style='margin-top:15px; font-size:18px; font-weight:bold; color:#555;'>현재 국면: {kr_phase}</p>"
            f"</div>", unsafe_allow_html=True
        )
        with st.expander("🔍 한국장 연산 근거 (Drawdown + RSI + VKOSPI + 환율)"):
            for detail in kr_details: st.markdown(f"- {detail}")

    st.divider()

    # ── 레이어 3: 회복 확인 ──
    st.markdown("##### ✅ 반등 신뢰도 확인 (바닥 이후 — Breadth & Credit 회복 여부)")
    st.caption("바닥 탐지 점수가 높을 때만 의미 있는 지표예요. 상승장에서는 항상 좋게 나오므로 참고용으로만 보세요.")
    rec_verdict, rec_signals, rec_score = calculate_recovery_confirmation(
        rsp_10y, spy_10y, hyg_10y, ief_10y
    )
    st.markdown(f"**{rec_verdict}**")
    for icon, msg in rec_signals:
        st.markdown(f"- {icon} {msg}")

    st.divider()

    # ── 백테스트 (10년 데이터 기반 완화 컷) ──
    with st.expander("🔬 과거 10년 백테스트 (미국 바닥 탐지기 기준)"):
        st.markdown(
            "바닥 탐지기 점수(Drawdown + RSI + VIX)를 과거 10년에 매일 적용한 결과입니다. "
            "**주요 이벤트에서 얼마나 점수가 나왔는지 확인**해보세요 — 모델 신뢰도 검증에 핵심입니다."
        )
        bt = run_historical_backtest(spy_10y, vix_10y, vix3m_10y)

        if bt:
            st.markdown("**📌 주요 시장 이벤트에서의 바닥 탐지 점수**")
            ev_cols = st.columns(len(bt["주요 이벤트 점수"]))
            for i, (name, ev_score) in enumerate(bt["주요 이벤트 점수"].items()):
                if ev_score is not None and isinstance(ev_score, int):
                    color = "#21c354" if ev_score >= 50 else "#fcca46" if ev_score >= 35 else "#ff4b4b"
                    ev_cols[i].markdown(
                        f"<div style='text-align:center; padding:10px; border-radius:8px; border:1px solid {color};'>"
                        f"<b>{name}</b><br>"
                        f"<span style='font-size:1.8em; color:{color};'>{ev_score}점</span>"
                        f"</div>", unsafe_allow_html=True
                    )
                else:
                    ev_cols[i].markdown(f"**{name}**: {ev_score}")

            st.markdown("")
            bt_col1, bt_col2 = st.columns(2)

            stat_70 = bt["70점 이상 (강력 매수)"]
            bt_col1.markdown("**🔥 70점 이상 (강력 매수 구간)**")
            if stat_70["발생 횟수"] > 0:
                bt_col1.markdown(f"- 시그널 발생: 과거 10년간 **{stat_70['발생 횟수']}일**")
                bt_col1.markdown(f"- 평균 3개월 수익률: **+{stat_70['평균 3M 수익률']:.2f}%**")
                bt_col1.markdown(f"- 평균 6개월 수익률: **+{stat_70['평균 6M 수익률']:.2f}%**")
                bt_col1.markdown(f"- 투자 승률 (3M): **{stat_70['승률 3M']:.1f}%**")
            else:
                bt_col1.info("과거 10년간 70점 이상 달성 없음")

            stat_50 = bt["50~69점 (분할 매수)"]
            bt_col2.markdown("**🟢 50~69점 (분할 매수 구간)**")
            if stat_50["발생 횟수"] > 0:
                bt_col2.markdown(f"- 시그널 발생: 과거 10년간 **{stat_50['발생 횟수']}일**")
                bt_col2.markdown(f"- 평균 3개월 수익률: **+{stat_50['평균 3M 수익률']:.2f}%**")
                bt_col2.markdown(f"- 평균 6개월 수익률: **+{stat_50['평균 6M 수익률']:.2f}%**")
                bt_col2.markdown(f"- 투자 승률 (3M): **{stat_50['승률 3M']:.1f}%**")
            else:
                bt_col2.info("해당 구간 시그널 발생 없음")

            if "score_series" in bt and not bt["score_series"].empty:
                st.markdown("**📈 바닥 탐지 점수 시계열 (10년)**")
                score_df = bt["score_series"].copy()
                score_df.columns = ["바닥 탐지 점수", "Drawdown(%)"]
                st.line_chart(score_df[["바닥 탐지 점수"]], height=200, color=["#fcca46"])
                st.caption("점수가 50~70% 이상으로 치솟는 시점 = 역사적 매수 기회. 2018년, 2020년(코로나), 2022년 바닥을 확인하세요.")

            st.caption("※ 백테스트는 과거 통계이며 미래 수익을 보장하지 않습니다. CNN F&G는 과거 데이터 없어 제외.")
        else:
            st.warning("백테스트에 필요한 10년치 데이터가 부족합니다.")

    st.divider()

    st.markdown("#### 📊 시장 심리 & 지수 — 최근 10년 추이")
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        st.markdown("**① VIX (공포 지수) — 10년**")
        if not vix_10y.empty:
            st.line_chart(
                pd.DataFrame({
                    "VIX": vix_10y['Close'],
                    "🔴 위험선(30)": 30.0,
                    "🟢 평온선(15)": 15.0,
                }),
                height=280,
                color=["#1f77b4", "#ff4b4b", "#21c354"]
            )
        else:
            st.warning("VIX 데이터를 불러오지 못했습니다.")
            
    with c_chart2:
        st.markdown("**② S&P 500 (SPY) — 10년**")
        if not spy_10y.empty:
            st.line_chart(
                pd.DataFrame({"S&P 500 (SPY)": spy_10y['Close']}),
                height=280,
                color=["#ff7f0e"]
            )
            spy_high = round(float(spy_10y['Close'].max()), 2)
            spy_low  = round(float(spy_10y['Close'].min()), 2)
            spy_pos  = round((current_spy - spy_low) / (spy_high - spy_low) * 100, 1) if current_spy != "N/A" else "N/A"
            st.caption(f"10년 고점 ${spy_high:,.2f} / 저점 ${spy_low:,.2f} | 현재 10년 범위 내 위치: **{spy_pos}%**")
        else:
            st.warning("S&P 500 데이터를 불러오지 못했습니다.")

    st.markdown("**③ CNN Fear & Greed Index (최근 1~2년)**")
    if cnn_history is not None:
        st.line_chart(
            pd.DataFrame({
                "F&G Score": cnn_history,
                "🟢 탐욕구간(75)": 75.0,
                "🔴 공포구간(25)": 25.0,
            }),
            height=280,
            color=["#1f77b4", "#21c354", "#ff4b4b"]
        )
        st.caption("25 이하 = 극단적 공포 (역발상 매수 구간) | 75 이상 = 극단적 탐욕 (현금 확보 구간). CNN 서버 정책상 최대 제공 기간이 1~2년으로 제한될 수 있습니다.")
    else:
        st.warning("⚠️ CNN 서버 차단 중. 잠시 후 새로고침 해주세요.")

with tab1:
    st.subheader("🔍 관심 종목 스캔")
    c1, c2 = st.columns(2)
    us_input = c1.text_input("🇺🇸 미국 주식", "TSMC, 브로드컴, 버티브")
    kr_input = c2.text_input("🇰🇷 한국 주식", "LS ELECTRIC")

    queries = (
        [("미국", q.strip()) for q in us_input.split(",") if q.strip()] +
        [("한국", q.strip()) for q in kr_input.split(",") if q.strip()]
    )

    all_data, failed_queries = [], []
    with st.spinner("분석 중 (재무제표 교차 검증 포함)..."):
        for region, q in queries:
            d = get_stock_data(q, is_kr=(region == "한국"), fast_mode=False)
            d["Region"] = region
            if not d.get("error"): all_data.append(d)
            else: failed_queries.append(q)

    if failed_queries:
        st.warning(f"⚠️ 데이터 조회 실패 (오타 확인): {', '.join(failed_queries)}")

    if all_data:
        signal_rows, tech_rows, fin_rows, risk_rows = [], [], [], []
        insider_blocks = []

        for d in all_data:
            ai_sig = get_ai_signal(d)
            tb_sig = get_tenbagger_signal(d)
            target_p, target_desc = calculate_smart_target(d, ai_sig)
            curr_price_str = fmt_price(d.get("Price"), d["Region"])
            target_str     = "-" if target_p == "-" else fmt_price(target_p, d["Region"])

            signal_rows.append({
                "종목":        d["Name"],
                "장투 시그널": ai_sig,
                "💡 타점":     f"{target_desc} ({target_str})",
                "현재가":      curr_price_str,
                "등락률":      fmt_change(d.get("Change")),
                "시가총액":    fmt_mcap(d.get("MarketCap"), d["Region"]),
            })

            rs_txt = relative_strength_label(d.get("RSI_14"), spy_rsi_val)

            w52_pos = d.get("W52_pos")
            if w52_pos is not None:
                if w52_pos <= 15:   pos_label = f"📍 {w52_pos}% (52주 바닥권)"
                elif w52_pos <= 30: pos_label = f"📍 {w52_pos}% (하단 30%)"
                elif w52_pos >= 85: pos_label = f"📍 {w52_pos}% (고점권)"
                elif w52_pos >= 70: pos_label = f"📍 {w52_pos}% (상단 30%)"
                else:               pos_label = f"📍 {w52_pos}% (중간권)"
            else:
                pos_label = "N/A"

            tech_rows.append({
                "종목":           d["Name"],
                "시장대비 강도":  rs_txt,
                "52주 위치":      pos_label,
                "고점 대비":      fmt(d.get("Gap_High"), "%", dig=1),
                "RSI(7일)":      fmt(d.get("RSI_7"),  dig=1),
                "RSI(14일)":     fmt(d.get("RSI_14"), dig=1),
                "RSI(21일)":     fmt(d.get("RSI_21"), dig=1),
                "MACD":          d.get("MACD_dir", "N/A"),
                "거래강도":       fmt(d.get("Vol_ratio"), "%", dig=1),
                "20일 이격":      fmt(d.get("MA20_gap"), "%", dig=1),
            })

            fin_rows.append({
                "종목":          d["Name"],
                "Rule of 40":    fmt(d.get("Rule_of_40"), "%", dig=1) if d.get("Rule_of_40") is not None else "N/A",
                "EV/EBITDA":     fmt(d.get("EV_EBITDA"), "x", dig=1),
                "EV/FCF":        fmt(d.get("EV_FCF"), "x", dig=1),
                "매출총이익률":  pct(d.get("Gross_Margin")),
                "영업이익률":    pct(d.get("Op_Margin")),
                "ROIC":          pct(d.get("ROIC")),
                "FCF Yield":     pct(d.get("FCF_Yield")),
                "FCF/Share":     fmt(d.get("FCFPS"), pfx="$" if d["Region"] == "미국" else "₩", dig=2),
                "자사주 매입":   fmt_buyback(d.get("Buybacks"), d["Region"]),
                "Forward PER":   fmt(d.get("Forward_PER"), dig=1),
                "PEG":           fmt(d.get("PEG"), dig=2),
            })

            risk_rows.append({
                "종목":            d["Name"],
                "종합 리스크 등급": d.get("Risk_Grade", "N/A"),
                "다음 실적일":     d.get("Next_Earning", "N/A"),
                "내부자 매수":     d.get("Insider_Buy",  "N/A"),
                "어닝 서프라이즈 (최근 8Q)": d.get("Earnings_Beat","N/A"),
                "공매도 비율":     d.get("Short_Interest","N/A"),
                "Beta":           d.get("Beta",          "N/A"),
                "최신 헤드라인":   (str(d.get("Latest_News",""))[:50]+"...") if len(str(d.get("Latest_News",""))) > 50 else d.get("Latest_News","N/A"),
            })

            if d.get("Insider_Buy") == "🟢 매수 기록 있음" and d.get("Insider_Detail"):
                insider_blocks.append({
                    "name":   d["Name"],
                    "detail": d["Insider_Detail"],
                    "url":    d.get("Edgar_URL", ""),
                })
            elif d.get("Edgar_URL"):
                insider_blocks.append({
                    "name":   d["Name"],
                    "detail": "",
                    "url":    d.get("Edgar_URL", ""),
                })

        st.markdown("#### 🎯 1. 11원칙 매매 시그널 & 눌림목 타점")
        st.dataframe(
            pd.DataFrame(signal_rows).set_index("종목").style.map(color_df),
            use_container_width=True
        )

        st.markdown("#### 📈 2. 기술적 지표 (상대강도 + 멀티RSI + 52주 위치)")
        st.dataframe(
            pd.DataFrame(tech_rows).set_index("종목").style.map(
                color_df, subset=["시장대비 강도","고점 대비","거래강도","20일 이격"]
            ),
            use_container_width=True
        )
        st.caption(
            "💡 **시장대비 강도**: SPY ETF RSI(14일)와 비교. 양수 = 시장보다 강함. "
            "| **52주 위치**: 0% = 52주 최저, 100% = 최고. "
            "| **고점 대비**: 52주 고점에서 얼마나 내려왔는지 (음수)."
        )

        st.markdown("#### 🚨 3. 리스크 관리 (종합 등급 · 실적일 · 내부자 · 공매도 · Beta · 뉴스)")
        st.dataframe(
            pd.DataFrame(risk_rows).set_index("종목").style.map(
                color_df, subset=["종합 리스크 등급", "내부자 매수"]
            ),
            use_container_width=True
        )

        if insider_blocks:
            st.markdown("#### 🔗 내부자 거래 상세 & SEC EDGAR 원문 링크")
            for block in insider_blocks:
                with st.expander(f"📋 {block['name']} — 내부자 거래 상세"):
                    if block["detail"]:
                        st.info(block["detail"])
                    else:
                        st.write("최근 순수 매수 기록 없음 (매도·행사·자동매매만 감지됨)")
                    if block["url"]:
                        st.markdown(
                            f"**[📄 SEC EDGAR Form 4 원문 보기 →]({block['url']})**\n\n",
                            unsafe_allow_html=True
                        )

        st.markdown("#### 💰 4. 단위경제 및 현금흐름 밸류에이션")
        st.dataframe(pd.DataFrame(fin_rows).set_index("종목"), use_container_width=True)
        
        st.markdown("#### 💡 4-1. 단위경제 & 현금흐름 자동 해석 (워런 버핏의 시각)")
        for d in all_data:
            interpretation = get_cashflow_interpretation(d)
            st.info(f"**{d['Name']}** : {interpretation}")

with tab4:
    st.subheader("🚀 섹터별 텐배거 마스터 레이더 (미래 지표 및 트렌드 필터)")
    UNIVERSE = {
        "🇺🇸 미국 AI & 클라우드":              ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
        "🇺🇸 미국 혁신성장 (우주/바이오/핀테크)": ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
        "🇰🇷 한국 반도체 소부장 (HBM/AI)":        ["피에스케이홀딩스", "한미반도체", "테크윙", "HPSP", "이수페타시스", "에이직랜드", "디아이", "원익IPS", "동진쎄미켐", "주성엔지니어링", "리노공업", "하나마이크론"],
        "🇰🇷 한국 K-뷰티 & K-푸드":            ["실리콘투","클래시스","파마리서치","삼양식품","브이티","에이피알","휴젤"],
        "🇰🇷 한국 바이오텍 & 헬스케어":          ["알테오젠","HLB","리가켐바이오","루닛","뷰노","제이엘케이"],
        "🇰🇷 한국 전력기기 & 로봇":             ["HD현대일렉트릭","레인보우로보틱스","두산로보틱스","LS ELECTRIC"],
    }
    selected_theme = st.selectbox("스캔할 섹터:", list(UNIVERSE.keys()))
    if st.button("해당 섹터 레이더 가동"):
        with st.spinner(f"[{selected_theme}] 전수 스캔 중 (경량 스캔 모드 활성화)..."):
            is_korea = "한국" in selected_theme
            radar_data = []
            for q in UNIVERSE[selected_theme]:
                d = get_stock_data(q, is_kr=is_korea, fast_mode=True)
                d["Region"] = "한국" if is_korea else "미국"
                if not d.get("error"): radar_data.append(d)
            radar_rows = []
            for d in radar_data:
                tb_sig = get_tenbagger_signal(d)
                if tb_sig != "-": 
                    radar_rows.append({
                        "종목":           d["Name"], "등급": tb_sig,
                        "시가총액":       fmt_mcap(d.get("MarketCap"), d["Region"]),
                        "매출성장":       pct(d.get("Rev_Growth")),
                        "이익성장(예상)": pct(d.get("Earnings_Growth")),
                        "영업이익률":     pct(d.get("Op_Margin")),
                        "Forward PER":    fmt(d.get("Forward_PER"), dig=1),
                        "PEG":            fmt(d.get("PEG"), dig=2),
                    })
            if radar_rows:
                st.dataframe(
                    pd.DataFrame(radar_rows).set_index("종목").style.map(color_df),
                    use_container_width=True
                )
                
                st.markdown("#### 🤖 텐배거 심층 분석용 AI 프롬프트")
                st.caption("아래 텍스트를 복사하여 AI(ChatGPT, Claude, Gemini 등)에게 붙여넣고 최적의 투자 종목을 추천받으세요.")
                
                tb_lines = [
                    f"[섹터 텐배거 스캔 결과: {selected_theme}]",
                    "아래는 워런 버핏과 피터 린치의 성장주/가치주 필터링을 통과한 '텐배거 후보' 기업들의 데이터야.",
                    "",
                    "【후보 종목 데이터】"
                ]
                for d in radar_data:
                    tb_sig = get_tenbagger_signal(d)
                    if tb_sig != "-":
                        rev_g = pct(d.get('Rev_Growth'))
                        earn_g = pct(d.get('Earnings_Growth'))
                        op_m = pct(d.get('Op_Margin'))
                        fwd_per = fmt(d.get('Forward_PER'), dig=1)
                        peg = fmt(d.get('PEG'), dig=2)
                        turnaround = "O" if d.get('Is_Turnaround') else "X"
                        
                        tb_lines.append(f"▶ {d['Name']} (등급: {tb_sig})")
                        tb_lines.append(f"  - 시가총액: {fmt_mcap(d.get('MarketCap'), d['Region'])}")
                        tb_lines.append(f"  - 성장성: 매출성장 {rev_g} | 예상이익성장 {earn_g} | 턴어라운드 {turnaround}")
                        tb_lines.append(f"  - 수익성 & 밸류에이션: 영업이익률 {op_m} | Forward PER {fwd_per} | PEG {peg}")
                        tb_lines.append("")
                        
                tb_lines += [
                    "【분석 요청사항】",
                    "1. 위 후보 기업들의 '매출/이익 성장성'과 '마진율(영업이익률)', '밸류에이션(PEG, Forward PER)'을 종합적으로 비교해 줘.",
                    "2. 현재 시점에서 장기 투자(1~3년) 목적으로 가장 투자 매력도(Risk vs Return)가 높은 1순위, 2순위 기업을 선정하고 그 이유를 논리적으로 설명해 줘.",
                    "3. 각 기업이 가진 치명적인 리스크나 주의해야 할 변수가 있다면 함께 짚어줘."
                ]
                st.code("\n".join(tb_lines), language="text")
                
            else:
                st.warning("⚠️ 현재 조건(지하실 역추세 및 실적/마진 기준)을 통과한 진성 우량주가 이 섹터에 존재하지 않습니다.")

with tab3:
    st.subheader("🤖 AI 참모 전용 구조화 리포트 v22.0 (진바닥 판독기 연동)")
    st.caption("아래 텍스트를 복사하여 ChatGPT, Claude, Gemini 등에 붙여넣고 심층 분석을 받아보세요.")
    
    now = get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')
    lines = [
        f"[11원칙 퀀트 분석 리포트 v22.0] ({now})",
        f"- CNN F&G (시장 심리): {cnn_score} ({cnn_rating})",
        f"- SPY RSI(14) (시장 과열도): {fmt(spy_rsi_val, dig=1)}",
        "",
        "【스캔 종목 데이터】"
    ]
    
    for d in all_data:
        ai_sig = get_ai_signal(d)
        tb_sig = get_tenbagger_signal(d)
        target_p, target_d = calculate_smart_target(d, ai_sig)
        rs_txt = relative_strength_label(d.get("RSI_14"), spy_rsi_val)
        w52    = d.get("W52_pos")
        w52_str = f"{w52}%" if w52 is not None else "N/A"

        rev_g   = pct(d.get('Rev_Growth'))
        gm      = pct(d.get('Gross_Margin'))
        op_m    = pct(d.get('Op_Margin'))
        earn_g  = pct(d.get('Earnings_Growth'))
        roe     = pct(d.get('ROE'))
        roic    = pct(d.get('ROIC'))
        fcf_y   = pct(d.get('FCF_Yield'))
        fcf_ps  = fmt(d.get("FCFPS"), pfx="$" if d["Region"] == "미국" else "₩", dig=2)
        bb_str  = fmt_buyback(d.get("Buybacks"), d["Region"])
        per     = fmt(d.get('PER'), dig=1)
        fwd_per = fmt(d.get('Forward_PER'), dig=1)
        peg     = fmt(d.get('PEG'), dig=2)

        lines += [
            f"┌─ [{d['Region']}] {d['Name']} (단기 시그널: {ai_sig} / 텐배거 등급: {tb_sig})",
            f"│ 1. 가격 및 타점: 현재가 {fmt_price(d.get('Price'), d['Region'])} | 추천 타점: {target_d} ({fmt_price(target_p, d['Region'])})",
            f"│ 2. 기술적 지표: RSI(7/14/21) {fmt(d.get('RSI_7'),dig=1)} / {fmt(d.get('RSI_14'),dig=1)} / {fmt(d.get('RSI_21'),dig=1)} | 시장대비: {rs_txt}",
            f"│ 3. 추세 및 위치: 52주 위치 {w52_str} | 고점 대비 {fmt(d.get('Gap_High'),'%',dig=1)} 하락",
            f"│ 4. 단위경제 & 효율성: 매출총이익률(Gross Margin) {gm} | ROIC {roic} | ROE {roe}",
            f"│ 5. 펀더멘탈(과거vs미래): 매출성장 {rev_g} | 영업이익률 {op_m} | 🎯예상이익 성장률 {earn_g}",
            f"│ 6. 현금흐름 & 주주환원: FCF Yield {fcf_y} | FCF per Share {fcf_ps} | 자사주 매입 {bb_str}",
            f"│ 7. 밸류에이션: PER {per} | 🎯Forward PER {fwd_per} | 🎯PEG {peg}",
            f"│ 8. 리스크 및 수급: 종합 리스크 {d.get('Risk_Grade', 'N/A')} | 내부자 {d.get('Insider_Buy','N/A')} | 공매도 {d.get('Short_Interest','N/A')} | Beta {d.get('Beta','N/A')}",
            f"└──────────────────────────────────────────────────",
        ]

    lines += [
        "",
        "【AI 참모 심층 분석 요청사항】",
        "위 데이터를 바탕으로 나의 11원칙 퀀트 투자 룰에 맞춰 다음을 심층 분석해 줘.",
        "",
        "1. [가치와 성장 듀얼 분석 (Turnaround & Bubble Check)]",
        "   - '과거 영업이익률/PER'과 '미래 예상 이익성장률/Forward PER/PEG'를 교차 비교해 진짜 성장과 가짜 거품을 구별해 줘.",
        "",
        "2. [현금흐름 및 자본 효율성 (Quality Check)]",
        "   - FCF Yield, ROIC, 매출총이익률(Gross Margin)을 분석하여 기업의 실제 현금 창출력과 해자(Moat)를 평가해 줘.",
        "   - 경영진의 자신감을 나타내는 '자사주 매입' 내역과 '내부자 매수' 여부를 연계해 수급 안정성을 확인해 줘.",
        "",
        "3. [리스크 및 수급 점검]",
        "   - 공매도 비율, Beta(변동성)를 종합하여 숨겨진 하방 리스크가 큰 종목을 경고해 줘.",
        "",
        "4. [기술적 타점 분석 및 최종 매매 시나리오]",
        "   - RSI 멀티타임프레임과 52주 위치, 시장대비 강도를 종합해 현재 가장 매수 신뢰도가 높은 종목을 선정해 줘.",
        "   - 현재 시장 심리(F&G, SPY RSI)를 바탕으로 지금 당장 '적극 매수', '관망', '비중 축소' 해야 할 종목들을 분류하고 구체적인 액션 플랜을 제시해 줘."
    ]
    st.code("\n".join(lines), language="text")