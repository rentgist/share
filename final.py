import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import FinanceDataReader as fdr
import requests

st.set_page_config(page_title="11원칙 퀀트 대시보드 v17.4", page_icon="🧭", layout="wide")

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
    try:
        df = fdr.StockListing('KRX')
        mapping = {}
        for _, row in df.iterrows():
            market_suffix = ".KS" if row['Market'] == 'KOSPI' else ".KQ"
            mapping[str(row['Name']).upper()] = {
                "raw_code": row['Code'],
                "yf_code": row['Code'] + market_suffix
            }
        return mapping
    except: return {}

KRX_DICT = get_krx_mapping()

# ─────────────────────────────────────────
# 한국 시간(KST) 강제 적용 헬퍼 함수 (핵심 수정 사항)
# ─────────────────────────────────────────
def get_kst_now():
    # 클라우드가 미국에 있어도 무조건 한국 시간(UTC+9)을 반환하도록 강제
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)

# ─────────────────────────────────────────
# CNN F&G 오리지널 로직
# ─────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_real_cnn_fg():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
    except Exception:
        return None, "데이터 수집 오류 (CNN 서버 차단됨)", None

# ─────────────────────────────────────────
# 🔥 불장 전용 매매 시그널
# ─────────────────────────────────────────
def get_ai_signal(d):
    roe = float(d.get('ROE') or 0); op_m = float(d.get('Op_Margin') or 0)
    rsi = float(d.get('RSI') or 50); cp = float(d.get('Price') or 0)
    ma20 = float(d.get('MA20') or 0); ma20_gap = float(d.get('MA20_gap') or 0)
    vol = float(d.get('Vol_ratio') or 100); macd = d.get('MACD_dir') or ""
    
    q_pass = (roe > 0.05 and op_m > 0.05) 
    if not q_pass and (roe < 0 or op_m < 0): return "⚫ 경고 (펀더멘탈)"
    
    if rsi >= 75 and ma20_gap > 15: return "🔵 과매수 (익절/관망)"
    if 60 <= rsi < 75 and cp > ma20 and "상승" in macd and vol > 120: return "🚀 추세 탑승 (불타기)"
    if 45 <= rsi < 60 and cp >= ma20: return "🟢 얕은 눌림목 (분할매수)"
    if rsi < 45: return "🔥 바닥 줍줍 (적극매수)"
    return "🟡 방향성 탐색 (관망)"

def calculate_smart_target(d, ai_sig):
    cp = d.get('Price'); ma5 = d.get('MA5', cp); ma20 = d.get('MA20', cp)
    bb_upper = d.get('BB_upper', cp); bb_lower = d.get('BB_lower', cp)
    
    if "추세 탑승" in ai_sig: return max(ma5, cp * 0.98), "5일선 지지 (단기 모멘텀)"
    elif "눌림목" in ai_sig: return ma20, "20일 생명선 지지 (스윙 매수)"
    elif "바닥 줍줍" in ai_sig: return bb_lower, "볼린저 하단 (반등 노림)"
    elif "과매수" in ai_sig: return bb_upper, "볼린저 상단 (익절 목표가)"
    else: return "-", "홀딩(Wait)"

def get_tenbagger_signal(d):
    mcap = float(d.get('MarketCap') or 0); region = d.get('Region')
    rev_g = float(d.get('Rev_Growth') or 0); op_m = float(d.get('Op_Margin') or 0); peg = float(d.get('PEG') or 99)
    if region == "미국" and mcap >= 50_000_000_000: return "🐘 대형주 (제외)"
    if region == "한국" and mcap >= 5_000_000_000_000: return "🐘 대형주 (제외)"
    
    points = 0
    if rev_g >= 0.20: points += 1 
    if op_m >= 0.10: points += 1  
    if 0 < peg <= 1.5: points += 1 
    return "🚀 텐배거(1순위)" if points >= 3 else ("🌱 폭발적 성장" if points == 2 else "-")

# ─────────────────────────────────────────
# 데이터 수집 (한국 시간 KST 강제 패치)
# ─────────────────────────────────────────
def calc_rsi(close):
    if len(close) < 15: return None
    delta = close.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    rs = gain.ewm(com=13).mean() / loss.ewm(com=13).mean()
    return round(float(100 - (100 / (1 + rs)).iloc[-1]), 2)

def calc_macd(close):
    if len(close) < 35: return None, "N/A"
    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    hist = macd - macd.ewm(span=9).mean()
    return round(float(macd.iloc[-1]), 2), "🟢상승" if hist.iloc[-1] > 0 else "🔴하락"

@st.cache_data(ttl=180) # 캐시 주기를 3분으로 단축하여 실시간성 강화
def get_stock_data(query, is_kr=False):
    base = {"Name": query, "error": None}
    try:
        # 🔥 여기서 미국/한국 서버 상관없이 무조건 KST 기준으로 날짜를 계산합니다!
        kst_now = get_kst_now()
        start = (kst_now - datetime.timedelta(days=180)).strftime('%Y-%m-%d')
        
        if is_kr:
            kr_info = KRX_DICT.get(str(query).strip().upper())
            if kr_info: raw_code, yf_code = kr_info["raw_code"], kr_info["yf_code"]
            else: raw_code, yf_code = query, f"{query}.KS"
            hist = fdr.DataReader(raw_code, start=start).dropna()
            info = yf.Ticker(yf_code).info
        else:
            ticker = US_NAME_MAP.get(str(query).strip().upper(), query).upper()
            tk = yf.Ticker(ticker)
            hist = tk.history(period="6mo").dropna()
            info = tk.info

        if hist.empty or len(hist) < 20: base["error"] = "데이터 부족"; return base

        close = hist['Close']; high = hist['High']; low = hist['Low']; vol = hist['Volume']
        price = float(close.iloc[-1]); prev = float(close.iloc[-2])
        
        base["Price"] = int(price) if is_kr else round(price, 2)
        base["Change"] = round((price - prev) / prev * 100, 2)
        base["RSI"] = calc_rsi(close)
        base["MACD_dir"] = calc_macd(close)[1]
        
        ma5 = close.rolling(5).mean().iloc[-1]; ma20 = close.rolling(20).mean().iloc[-1]
        std = close.rolling(20).std().iloc[-1]
        base["MA5"] = ma5; base["MA20"] = ma20
        base["BB_upper"] = ma20 + 2*std; base["BB_lower"] = ma20 - 2*std
        base["Vol_ratio"] = round(float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-2] * 100), 1)
        base["MA20_gap"] = round((price - ma20) / ma20 * 100, 2)

        base.update({"MarketCap": info.get('marketCap', 0), "PER": info.get('trailingPE'), "PBR": info.get('priceToBook'),
                     "ROE": info.get('returnOnEquity'), "Op_Margin": info.get('operatingMargins'), 
                     "Debt": info.get('debtToEquity'), "PEG": info.get('pegRatio'), "Rev_Growth": info.get('revenueGrowth')})
    except Exception as e: base["error"] = str(e)
    return base

# ─────────────────────────────────────────
# 포맷 헬퍼
# ─────────────────────────────────────────
def fmt_mcap(mcap, region):
    if not mcap or mcap == 0: return "N/A"
    return f"${mcap/1e9:.1f}B" if region == "미국" else (f"{mcap/1e12:.2f}조 원" if mcap >= 1e12 else f"{mcap/1e8:.0f}억 원")

def fmt_price(val, region):
    if val is None or val == "-": return "-"
    return f"{int(val):,}원" if region == "한국" else f"${float(val):,.2f}"

def fmt(val, sfx="", pfx="", dig=2, na="N/A"):
    return na if val is None or (isinstance(val, float) and np.isnan(val)) else f"{pfx}{val:.{dig}f}{sfx}" if isinstance(val, float) else f"{pfx}{val}{sfx}"

def pct(val): return fmt(float(val)*100, "%", dig=1) if val else "N/A"

def color_df(val):
    if isinstance(val, str) and '%' in val:
        try:
            num = float(val.replace('%', '').replace(',', ''))
            return 'color: #ff4b4b' if num > 0 else 'color: #0068c9' if num < 0 else ''
        except: pass
    if val in ["🔥 바닥 줍줍 (적극매수)", "🚀 추세 탑승 (불타기)", "🚀 텐배거(1순위)"]: return 'background-color: #ffcccc; font-weight: bold; color: black'
    if val in ["🟢 얕은 눌림목 (분할매수)", "🌱 폭발적 성장"]: return 'background-color: #ccffcc; font-weight: bold; color: black'
    if val == "⚫ 경고 (펀더멘탈)": return 'background-color: #555555; font-weight: bold; color: white'
    if val == "🔵 과매수 (익절/관망)": return 'color: blue; font-weight: bold'
    if val == "🐘 대형주 (제외)": return 'color: gray; font-style: italic'
    return ''

# ─────────────────────────────────────────
# UI 메인
# ─────────────────────────────────────────
st.title("🧭 11원칙 퀀트 트레이딩 대시보드 v17.4")
st.caption("클라우드 서버 시차(KST 강제 적용) 버그 수정본")

tab1, tab4, tab2, tab3 = st.tabs(["📊 실시간 포트폴리오", "🚀 오늘의 텐배거 레이더", "🌐 매크로 & F&G Index", "🤖 AI 참모 리포트"])

cnn_score, cnn_rating, cnn_history = get_real_cnn_fg()

with tab2:
    st.subheader("🌐 글로벌 매크로 및 시장 심리")
    with st.spinner("실시간 매크로 데이터를 복구 중입니다..."):
        usd_krw = get_stock_data("KRW=X")
        vix_1y = yf.Ticker("^VIX").history(period="1y")
        current_vix = round(float(vix_1y['Close'].iloc[-1]), 2) if not vix_1y.empty else "N/A"
        vix_change = round(((current_vix - float(vix_1y['Close'].iloc[-2])) / float(vix_1y['Close'].iloc[-2])) * 100, 2) if not vix_1y.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("환율 (USD/KRW)", fmt_price(usd_krw.get('Price'), "한국").replace("원", " 원"), f"{usd_krw.get('Change')}%")
    col2.metric("미국 VIX (변동성 지수)", current_vix, f"{vix_change}%", delta_color="inverse")
    
    if cnn_score is not None:
        if cnn_score <= 25: fg_color, fg_stat = "🔴", "극단적 공포"
        elif cnn_score <= 45: fg_color, fg_stat = "🟠", "공포"
        elif cnn_score <= 55: fg_color, fg_stat = "🟡", "중립"
        elif cnn_score <= 75: fg_color, fg_stat = "🟢", "탐욕"
        else: fg_color, fg_stat = "🟢", "극단적 탐욕"
        col3.metric("CNN Fear & Greed Index", f"{cnn_score} / 100", f"{fg_color} {fg_stat} ({cnn_rating})")
    else:
        col3.metric("CNN Fear & Greed Index", "N/A", cnn_rating)

    st.divider()
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        st.markdown("#### 📉 1. 최근 1년 VIX 추이")
        if not vix_1y.empty: st.line_chart(pd.DataFrame({"VIX": vix_1y['Close'], "🔴 위험선(30)": 30.0, "🟢 평온선(15)": 15.0}), height=300)
    with c_chart2:
        st.markdown("#### 🧭 2. 실제 CNN Fear & Greed 1년 추이")
        if cnn_history is not None: 
            st.line_chart(pd.DataFrame({"F&G Score": cnn_history, "🟢 탐욕(75)": 75.0, "🔴 공포(25)": 25.0}), height=300)
        else:
            st.warning("⚠️ 현재 CNN 서버에서 비정상적인 접근(크롤링)을 차단했습니다. 잠시 후 새로고침 해주세요.")

with tab1:
    st.subheader("🔍 관심 종목 스캔 (대장주 눌림목 분석기)")
    c1, c2 = st.columns(2)
    us_input = c1.text_input("🇺🇸 미국 주식", "엔비디아, 암, ARM, 샌디스크")
    kr_input = c2.text_input("🇰🇷 한국 주식", "LS ELECTRIC, 삼성전자, SK하이닉스, 알테오젠, 제주반도체, 태성")

    queries = [("미국", q.strip()) for q in us_input.split(",") if q.strip()] + [("한국", q.strip()) for q in kr_input.split(",") if q.strip()]
    
    all_data = []
    failed_queries = []
    with st.spinner("상승장 주도주 추세 및 모멘텀 분석 중..."):
        for region, q in queries:
            d = get_stock_data(q, is_kr=(region=="한국"))
            d["Region"] = region
            if not d.get("error"): all_data.append(d)
            else: failed_queries.append(q)

    if failed_queries: st.warning(f"⚠️ 다음 종목은 데이터를 찾지 못했습니다 (오타 확인): {', '.join(failed_queries)}")

    if all_data:
        signal_rows, tech_rows, fin_rows = [], [], []
        for d in all_data:
            ai_sig = get_ai_signal(d)
            tb_sig = get_tenbagger_signal(d)
            target_p, target_desc = calculate_smart_target(d, ai_sig)
            
            curr_price_str = fmt_price(d.get("Price"), d["Region"])
            target_str = "-" if target_p == "-" else fmt_price(target_p, d["Region"])
            
            signal_rows.append({"종목": d["Name"], "장투 시그널": ai_sig, "💡 스마트 타점": f"{target_desc} ({target_str})", "텐배거 등급": tb_sig, "현재가": curr_price_str, "시가총액": fmt_mcap(d.get("MarketCap"), d["Region"])})
            tech_rows.append({"종목": d["Name"], "등락률": fmt(d.get("Change"), "%", dig=2), "RSI": fmt(d.get("RSI")), "MACD": d.get("MACD_dir"), "거래강도": fmt(d.get("Vol_ratio"), "%", dig=1), "20일 이격": fmt(d.get("MA20_gap"), "%", dig=1)})
            fin_rows.append({"종목": d["Name"], "매출성장": pct(d.get("Rev_Growth")), "영업이익률": pct(d.get("Op_Margin")), "ROE": pct(d.get("ROE")), "PEG": fmt(d.get("PEG"), dig=2), "PER": fmt(d.get("PER"), dig=1)})

        st.markdown("#### 🎯 1. 11원칙 매매 시그널 & 눌림목 타점")
        st.dataframe(pd.DataFrame(signal_rows).set_index("종목").style.map(color_df), use_container_width=True)
        st.markdown("#### 📈 2. 기술적 지표 (차트/수급)")
        st.dataframe(pd.DataFrame(tech_rows).set_index("종목").style.map(color_df, subset=['등락률', '거래강도', '20일 이격']), use_container_width=True)
        st.markdown("#### 💰 3. 밸류에이션 (성장성/수익성)")
        st.dataframe(pd.DataFrame(fin_rows).set_index("종목"), use_container_width=True)

with tab4:
    st.subheader("🚀 섹터별 텐배거 마스터 레이더")
    UNIVERSE = {
        "🇺🇸 미국 AI & 클라우드": ["PLTR", "CRWD", "SNOW", "DDOG", "NET", "SOUN", "MDB", "ZS", "MNDY"],
        "🇺🇸 미국 혁신성장 (우주/바이오/핀테크)": ["IONQ", "SOFI", "RIVN", "CELH", "RKLB", "ASTS", "CRSP", "LUNR", "SYM", "HOOD"],
        "🇰🇷 한국 K-뷰티 & K-푸드 (수출 주도)": ["실리콘투", "클래시스", "파마리서치", "삼양식품", "브이티", "에이피알", "휴젤"],
        "🇰🇷 한국 바이오텍 & 헬스케어": ["알테오젠", "HLB", "리가켐바이오", "루닛", "뷰노", "제이엘케이"],
        "🇰🇷 한국 전력기기 & 로봇": ["HD현대일렉트릭", "레인보우로보틱스", "두산로보틱스", "LS ELECTRIC"]
    }
    selected_theme = st.selectbox("스캔할 유니버스(섹터)를 선택하세요:", list(UNIVERSE.keys()))
    if st.button("해당 섹터 레이더 가동"):
        with st.spinner(f"[{selected_theme}] 풀을 전수 스캔 중입니다..."):
            is_korea = "한국" in selected_theme
            radar_data = []
            for q in UNIVERSE[selected_theme]:
                d = get_stock_data(q, is_kr=is_korea); d["Region"] = "한국" if is_korea else "미국"
                if not d.get("error"): radar_data.append(d)
            radar_rows = []
            for d in radar_data:
                tb_sig = get_tenbagger_signal(d)
                if "🚀" in tb_sig or "🌱" in tb_sig:
                    radar_rows.append({"종목": d["Name"], "등급": tb_sig, "시가총액": fmt_mcap(d.get("MarketCap"), d["Region"]), "매출성장": pct(d.get("Rev_Growth")), "영업이익률": pct(d.get("Op_Margin")), "PEG": fmt(d.get("PEG"), dig=2)})
            if radar_rows:
                st.dataframe(pd.DataFrame(radar_rows).set_index("종목").style.map(color_df), use_container_width=True)
            else: st.warning("오늘은 해당 섹터에서 텐배거 기준을 통과한 종목이 없습니다.")

with tab3:
    st.subheader("🤖 AI 참모 전용 구조화 리포트")
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = [f"[11원칙 퀀트 분석 리포트 v17.4] ({now})\n", f"- F&G: {cnn_score}\n"]
    for d in all_data:
        ai_sig = get_ai_signal(d)
        tb_sig = get_tenbagger_signal(d)
        target_p, target_d = calculate_smart_target(d, ai_sig)
        lines += [f"┌─ [{d['Region']}] {d['Name']} (시그널: {ai_sig} / {tb_sig})", 
                  f"│ 가격: {fmt_price(d.get('Price'), d['Region'])} | 추천 타점: {target_d} ({fmt_price(target_p, d['Region'])})", 
                  f"│ ▶ 지표: 시총 {fmt_mcap(d.get('MarketCap'), d['Region'])} | RSI {fmt(d.get('RSI'))} | 거래강도 {fmt(d.get('Vol_ratio'), '%')}", 
                  f"└──────────────────────────────────────────────────"]
    lines.append("\n[요청] 대세 상승장 관점에서 위 종목들의 모멘텀과 눌림목 타점을 평가해줘.")
    st.code("\n".join(lines), language="text")