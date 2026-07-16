from dotenv import load_dotenv
load_dotenv()
import streamlit as st
import calendar_manager
import pandas as pd
import concurrent.futures
import numpy as np
import datetime
import altair as alt

from config import get_kst_now
from data_loader import (
    get_real_cnn_fg, 
    get_macro_charts, 
    get_sector_baseline, 
    get_stock_data,
    get_upcoming_events,
    get_investor_flow,
    get_1m_investor_flow
)
import sys
if "signals" in sys.modules:
    import importlib
    importlib.reload(sys.modules["signals"])
if "data_loader" in sys.modules:
    import importlib
    importlib.reload(sys.modules["data_loader"])

try:
    from signals import (
        calculate_us_risk_radar,
        calculate_kr_risk_radar,
        calculate_us_bottom_finder,
        calculate_kr_bottom_finder,
        calculate_recovery_confirmation,
        calculate_macro_risk_gauge,
        calculate_cashflow_signal,
        calculate_regime_classification,
        get_strategic_advice,
        run_historical_backtest,
        run_kr_historical_backtest,
        get_cashflow_interpretation,
        relative_strength_label,
        get_ai_signal,
        calculate_smart_target,
        get_tenbagger_signal,
        analyze_macro_flow,
        generate_economic_commentary
    )
except ImportError as e:
    st.error(f"🚨 ImportError 발생: {e}")
    st.stop()
except Exception as e:
    st.error(f"🚨 알 수 없는 오류 발생: {e}")
    st.stop()

st.set_page_config(page_title="ORION", page_icon="🛰", layout="wide")

# AI 리포트 전용 고대비 스타일 주입
st.markdown("""
<style>
    /* AI 리포트 영역 내의 본문 글씨를 선명한 검은색(#000000)으로 변경 */
    .ai-report-container, .ai-report-container p, .ai-report-container li {
        color: #000000 !important;
        font-size: 1.05rem !important;
        line-height: 1.7 !important;
    }
    /* AI 리포트 영역 내의 소제목 색상 및 강조 */
    .ai-report-container h1, .ai-report-container h2, .ai-report-container h3 {
        color: #0f172a !important;
        font-weight: 800 !important;
        margin-top: 15px !important;
        margin-bottom: 10px !important;
    }
</style>
""", unsafe_allow_html=True)

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
st.title("🛰 ORION")
st.caption("확률이 충분하지 않은 거래는 하지 않습니다.")

cnn_score, cnn_rating, cnn_history = get_real_cnn_fg()
sector_base = get_sector_baseline()
spy_rsi_val = sector_base.get("S&P 500 (SPY)")

macro_charts = get_macro_charts()
usd_krw      = macro_charts.get("usdkrw_10y", pd.DataFrame())
kospi_10y    = macro_charts.get("kospi_10y", pd.DataFrame())
vkospi_10y   = macro_charts.get("vkospi_10y", pd.DataFrame())
spy_10y      = macro_charts.get("spy_10y", pd.DataFrame())
vix_10y      = macro_charts.get("vix_10y", pd.DataFrame())
vix3m_10y    = macro_charts.get("vix3m_10y", pd.DataFrame())
hyg_10y      = macro_charts.get("hyg_10y", pd.DataFrame())
ief_10y      = macro_charts.get("ief_10y", pd.DataFrame())
rsp_10y      = macro_charts.get("rsp_10y", pd.DataFrame())

rsp_change_pct = None
if not rsp_10y.empty:
    rsp_close = rsp_10y['Close']
    if len(rsp_close) >= 2:
        rsp_change_pct = ((rsp_close.iloc[-1] - rsp_close.iloc[-2]) / rsp_close.iloc[-2]) * 100.0

# 🆕 장단기 금리차 & 반도체 업황 데이터 추출
tnx_10y   = macro_charts.get("tnx_10y", pd.DataFrame())
irx_10y   = macro_charts.get("irx_10y", pd.DataFrame())
mu_2y     = macro_charts.get("mu_2y", pd.DataFrame())
soxx_2y   = macro_charts.get("soxx_2y", pd.DataFrame())

us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)
kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)
kr_macro_score, kr_macro_status, kr_macro_details = calculate_macro_risk_gauge(kospi_10y, usd_krw)
kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

# 미국 리스크 레이더 및 반등 신뢰도 글로벌 사전 계산 (1번 탭의 복사용 프롬프트 등에서 호출하기 위함)
us_rec_verdict, us_rec_signals, us_rec_score = calculate_recovery_confirmation(rsp_10y, spy_10y, hyg_10y, ief_10y)
us_risk_grade, us_risk_color, us_risk_alerts, us_danger = calculate_us_risk_radar(
    vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y,
    tnx_hist=tnx_10y, irx_hist=irx_10y, mu_hist=mu_2y, soxx_hist=soxx_2y  # 🆕 장단기 금리차 & 반도체 업황
)

# 탭 구성
tab_sniper, tab_radar, tab_report, tab_port, tab_calendar = st.tabs(["🚦 ORION Signal", "🔍 종목 발굴 & 타이밍", "📊 마스터 리포트", "💼 포트폴리오", "📅 마켓 캘린더"])

with tab_sniper:
    st.subheader("🛰 ORION Signal")
    st.caption("ORION은 기다릴 때와 움직일 때를 구별합니다.")

    adv_head, adv_color, adv_actions = get_strategic_advice(
        kr_danger, kr_score, kr_verdict, kr_phase, recovery_score=kr_macro_score
    )

    st.markdown(
        f"<div style='background:{adv_color}22; border-left: 8px solid {adv_color}; "
        f"padding:20px; border-radius:10px; margin-bottom:20px;'>"
        f"<h2 style='margin-top:0; color:{adv_color};'>{adv_head}</h2>"
        f"<p style='font-size:0.95em; color:#888; margin-bottom:10px;'>위험도 {kr_danger}점 · 바닥확률 {kr_score}% · 매크로안전도 {kr_macro_score}점 · {kr_phase}</p>"
        f"<ul>" + "".join([f"<li style='font-size:1.05em; margin-bottom:5px;'>{a}</li>" for a in adv_actions]) + "</ul>"
        f"</div>", unsafe_allow_html=True
    )

    st.divider()
    st.markdown("### 💡 글로벌 매크로 & 수급 통합 지표")
    
    # 데이터 수집
    flow_data = get_investor_flow()  # (외국인, 기관, 개인)
    flow_1m = get_1m_investor_flow()
    
    # AI 브리핑을 위한 추가 데이터 구성
    extra_data = {
        'cnn_score': cnn_score,
        'cnn_rating': cnn_rating,
        'flow_1m': flow_1m,
    }
    
    phase, summary_dict = analyze_macro_flow(macro_charts, flow_data, extra_data=extra_data)
    
    # 3x2 Grid 레이아웃 (매크로 3개, 수급 3개)
    m_col1, m_col2, m_col3 = st.columns(3)
    m_col1.metric("🇺🇸 국채 10년물 금리", summary_dict['TNX_10Y'].split(' (')[0], summary_dict['TNX_10Y'].split(' (')[1].replace(')','').replace('p',''), delta_color="inverse")
    m_col2.metric("🛢️ WTI 원유", summary_dict['WTI_Crude'].split(' (')[0], summary_dict['WTI_Crude'].split(' (')[1].replace(')',''), delta_color="inverse")
    m_col3.metric("💵 원/달러 환율", summary_dict['USD_KRW'].split(' (')[0], summary_dict['USD_KRW'].split(' (')[1].replace(')',''), delta_color="inverse")
    
    # 🇰🇷 코스피 실시간 가격 및 5일선 현황 표시
    k_col1, k_col2, k_col3 = st.columns(3)
    if not kospi_10y.empty:
        current_kospi_val = round(float(kospi_10y['Close'].iloc[-1]), 2)
        kospi_5d_sma = round(float(kospi_10y['Close'].rolling(5).mean().iloc[-1]), 2)
        gap = current_kospi_val - kospi_5d_sma
        is_above = current_kospi_val >= kospi_5d_sma
        
        # 코스피 등락률 연산
        if len(kospi_10y['Close']) >= 2:
            prev_kospi = float(kospi_10y['Close'].iloc[-2])
            kospi_change_pts = current_kospi_val - prev_kospi
            kospi_change_pct = (kospi_change_pts / prev_kospi) * 100.0
            kospi_delta_str = f"{kospi_change_pct:+.2f}% ({kospi_change_pts:+.2f}p)"
        else:
            kospi_delta_str = "0.00% (0.00p)"
        
        k_col1.metric("🇰🇷 KOSPI 현재가", f"{current_kospi_val:,.2f}", delta=kospi_delta_str)
        k_col2.metric("📈 KOSPI 5일 이평선", f"{kospi_5d_sma:,.2f}")
        k_col3.metric(
            "🎯 5일선 안착 여부", 
            "안착 완료" if is_above else "미안착", 
            f"이격: {gap:+,.2f}p", 
            delta_color="normal" if is_above else "off"
        )
    else:
        k_col1.metric("🇰🇷 KOSPI 현재가", "데이터 없음")
        k_col2.metric("📈 KOSPI 5일 이평선", "데이터 없음")
        k_col3.metric("🎯 5일선 안착 여부", "확인 불가")
        
    f_col1, f_col2, f_col3 = st.columns(3)
    
    if summary_dict.get('flow_valid', True):
        def _get_metric_args(val):
            return {
                "label": "순매수" if val >= 0 else "순매도",
                "delta": "순매수" if val >= 0 else "-순매도"
            }
            
        f_col1.metric(f"👤 외국인 {_get_metric_args(summary_dict['Foreigner_raw'])['label']}", 
                      summary_dict['Foreigner'], 
                      _get_metric_args(summary_dict['Foreigner_raw'])['delta'])
        
        f_col2.metric(f"🏢 기관 {_get_metric_args(summary_dict['Institutional_raw'])['label']}", 
                      summary_dict['Institutional'], 
                      _get_metric_args(summary_dict['Institutional_raw'])['delta'])
        
        f_col3.metric(f"🧑 개인 {_get_metric_args(summary_dict['Retail_raw'])['label']}", 
                      summary_dict['Retail'], 
                      _get_metric_args(summary_dict['Retail_raw'])['delta'])
    else:
        # 데이터가 모두 0일 때 (KRX 시스템 점검 등)
        f_col1.metric("👤 외국인 수급", "⚠️ 점검 중", "데이터 없음", delta_color="off")
        f_col2.metric("🏢 기관 수급", "⚠️ 점검 중", "데이터 없음", delta_color="off")
        f_col3.metric("🧑 개인 수급", "⚠️ 점검 중", "데이터 없음", delta_color="off")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if "cfo_report_cache" not in st.session_state:
        st.session_state["cfo_report_cache"] = ""
 
    if st.button("🔄 CFO AI 시장 브리핑 생성", key="cfo_report_btn"):
        with st.spinner("거시경제 CFO AI가 시장 흐름을 분석하고 있습니다..."):
            st.session_state["cfo_report_cache"] = generate_economic_commentary(summary_dict, phase)
            
    if st.session_state["cfo_report_cache"]:
        ai_commentary = st.session_state["cfo_report_cache"]
        if "⚠️" in ai_commentary:
            st.error(ai_commentary)
        else:
            st.info(f"**[CFO 통합 브리핑] {phase}**\n\n{ai_commentary}")
    else:
        st.info("👈 버튼을 눌러 CFO AI 시장 분석 브리핑을 생성하세요.")

    st.divider()
    st.markdown("### 🤖 실시간 AI 종합 브리핑")
    
    if st.button("🔄 AI 종합 관제 리포트 생성 (뉴스 + 매크로 종합)", type="primary"):
        with st.spinner("Gemini 2.5 Flash가 글로벌 속보와 매크로 수치를 종합하여 리포트를 작성 중입니다..."):
            market_ctx = f"판정결과: {adv_head}\n위험도: {kr_danger}점\n바닥점수: {kr_score}점\n현재국면: {kr_phase}"
            
            try:
                import sys
                import importlib
                import ai_reporter
                importlib.reload(ai_reporter)
                from ai_reporter import generate_smart_control_room_report
                report = generate_smart_control_room_report(market_ctx)
                st.session_state["ai_report_cache"] = report
            except Exception as e:
                st.error(f"리포트 생성 모듈 로드 실패: {e}")

    if "ai_report_cache" in st.session_state:
        st.markdown("<div class='ai-report-container'>", unsafe_allow_html=True)
        st.markdown(st.session_state["ai_report_cache"])
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("👈 상단의 버튼을 눌러 최신 시황 리포트를 생성하세요.")

    # API Key 캐싱 디버깅을 위한 마스킹 정보 출력
    import os
    api_key_check = os.environ.get("GEMINI_API_KEY", "")
    if api_key_check:
        masked_key = api_key_check[:6] + "..." + api_key_check[-4:] if len(api_key_check) > 10 else "길이 부족"
        st.caption(f"⚙️ 현재 대시보드 서버가 인식한 API Key: `{masked_key}`")
    else:
        st.caption("⚙️ 현재 대시보드 서버가 인식한 API Key: `[없음]`")

    st.divider()

    st.markdown("### 📰 최근 글로벌 주요 뉴스 (AI 수집)")
    import os, json, requests
    
    news_data = []
    remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/news_archive.json"
    try:
        resp = requests.get(remote_url, timeout=5)
        if resp.status_code == 200:
            news_data = resp.json()
    except:
        pass
        
    if not news_data:
        news_file = os.path.join("..", "quant-alpha-engine", "data", "news_archive.json")
        if not os.path.exists(news_file):
            news_file = "data/news_archive.json"
        if os.path.exists(news_file):
            try:
                with open(news_file, "r", encoding="utf-8") as f:
                    news_data = json.load(f)
            except:
                pass
                
    if True:
        try:
            if news_data:
                import datetime
                recent_news = []
                now = datetime.datetime.now()
                for n in news_data:
                    dt_str = n.get("fetched_at", "")
                    try:
                        # Only include news within the last 3 days (72 hours)
                        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                        if (now - dt).days <= 3:
                            recent_news.append(n)
                    except:
                        # If date parsing fails, just include it to be safe
                        recent_news.append(n)
                
                news_data = sorted(recent_news, key=lambda x: (x.get("importance", 0), x.get("fetched_at", "")), reverse=True)
                for n in news_data[:20]:
                    title = n.get("title_ko", n.get("title", ""))
                    link = n.get("link", "#")
                    source = n.get("source", "N/A")
                    importance = n.get("importance", 0)
                    sentiment = n.get("sentiment", "중립")
                    
                    stars = "⭐" * importance
                    color = "red" if sentiment == "악재" else "green" if sentiment == "호재" else "gray"
                    
                    with st.expander(f"[{source}] {title} (중요도: {stars})"):
                        st.markdown(f"**판단 근거**: {n.get('reason', '')}")
                        st.markdown(f"**대응 액션**: <span style='color:{color}; font-weight:bold;'>{n.get('action_point', '')}</span>", unsafe_allow_html=True)
                        st.markdown(f"[원문 기사 보러가기]({link})")
            else:
                st.write("수집된 뉴스가 없습니다.")
        except Exception as e:
            st.error(f"뉴스 로드 중 오류: {e}")
    else:
        st.write("현재 수집된 뉴스 아카이브가 존재하지 않습니다.")

    st.divider()

    # ── [NEW] ORION 매크로 & 자금흐름 통합 국면 판별기 ──
    st.divider()
    st.markdown("### 🚦 ORION 통합 국면 판별기 (Regime Classifier)")
    
    c_macro, c_flow = st.columns(2)
    
    with c_macro:
        st.markdown("#### Step 1: 📊 매크로 위험도 (Risk Gauge)")
        st.markdown(f"**상태:** {kr_macro_status}")
        for icon, msg in kr_macro_details:
            st.write(f"{icon} {msg}")
            
    with c_flow:
        st.markdown("#### Step 2: 💸 자금흐름 강도 (Flow Signal)")
        
        # 수동 입력 폼
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            foreign_futures = st.number_input("① 외국인 선물 순매수 (계약)", value=0, step=100)
        with f_col2:
            oi_trend = st.radio("② 선물 미결제약정", ["증가 추세", "감소/정체"], index=1)
            
        kr_flow_score, kr_flow_status, kr_flow_details = calculate_cashflow_signal(foreign_futures, oi_trend, rsp_change_pct, kospi_10y)
        
        st.markdown(f"**상태:** {kr_flow_status}")
        for icon, msg in kr_flow_details:
            st.write(f"{icon} {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Step 3: 🎯 통합 판정 (Action Plan)")
    
    regime, action, r_color = calculate_regime_classification(kr_macro_score, kr_flow_score)
    
    st.markdown(
        f"<div style='background:{r_color}22; border-left: 8px solid {r_color}; padding:20px; border-radius:10px; margin-bottom:20px;'>"
        f"<h2 style='margin-top:0; color:{r_color};'>{regime}</h2>"
        f"<p style='font-size:1.1em; color:#333;'>{action}</p>"
        f"</div>", unsafe_allow_html=True
    )
    
    st.caption("※ 자금흐름(단기 수급) 50점 이상 시 선발대 투입 검토 가능 (⚠️ 경고 국면)")
    
    st.markdown("""
    <div style='background-color:#f8f9fa; padding:15px; border-radius:8px; border:1px solid #ddd; margin-bottom:25px;'>
        <h4 style='margin-top:0; color:#444;'>💡 대가들의 비중 조절 규칙 (Position Sizing)</h4>
        <ul style='font-size:0.95em; color:#555;'>
            <li><b>선발대(정찰병)만 투입 (현금의 10% ~ 20%)</b> : 아직 매크로 추세가 완전히 돌아서지 않았으므로 '본대' 투입은 금물입니다. 내일 5일선이 깨지면 가장 적은 손실로 빠르게 즉각 손절(Cut)할 수 있는 비중만 진입합니다.</li>
            <li><b>관찰 기간 (3~5일) 유지</b> : 이 수급이 '하루짜리 훼이크'인지, '진짜 추세 전환'인지 3~5일간 5일선 지지 여부를 확인해야 합니다 (위 통합 판정에 <b>실제 경과일이 자동 카운트</b>됩니다).</li>
            <li><b>본대 투입 타이밍 (조건부 GO → 강력 GO)</b> : 3~5일 뒤 KOSPI 20일선까지 돌파하며 매크로 점수도 50점 이상으로 올라오면(🟡 조건부 GO), 그때 남은 현금의 50%를 투입합니다. 모든 지표가 80점 이상을 가리키면(🟢 강력 GO) 풀매수를 진행합니다.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # ──────────────────────────────────────────────────────────
    # [웹 Gemini 복사용 프롬프트 생성기]
    # ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📋 웹 버전 Gemini Pro 복사용 프롬프트")
    st.caption("아래 텍스트 상자의 복사 버튼(우측 상단 아이콘)을 눌러 구글 웹 Gemini(Advanced 등)에 붙여넣으면, 최고 스펙 Pro 모델의 깊이 있는 마켓 브리핑을 무료로 받으실 수 있습니다!")
    
    # 최근 뉴스 포맷팅 (최대 60개)
    web_news_lines = []
    if news_data:
        for n in news_data[:60]:
            t = n.get("title_ko", n.get("title", ""))
            s = n.get("sentiment", "중립")
            i = n.get("importance", 0)
            a = n.get("action_point", "")
            web_news_lines.append(f"- [{s}/중요도:{i}] {t} (대응: {a})")
    web_news_text = "\n".join(web_news_lines) if web_news_lines else "최근 수집된 뉴스가 없습니다."

    # 프롬프트 조립용 지표 포맷팅
    kospi_str = f"{current_kospi_val:,.2f}" if 'current_kospi_val' in locals() and current_kospi_val else "N/A"
    kospi_5d_str = f"{kospi_5d_sma:,.2f}" if 'kospi_5d_sma' in locals() and kospi_5d_sma else "N/A"
    kospi_status_str = ("안착 완료" if is_above else f"미안착 (이격: {gap:+,.2f}p)") if 'is_above' in locals() and 'gap' in locals() else "N/A"
    
    
    rsp_val_str = f"{rsp_change_pct:+.2f}%" if rsp_change_pct is not None else "N/A"

    # 프롬프트 조립
    upcoming_events_str = calendar_manager.get_upcoming_events_string()
    web_prompt = f"""너는 대한민국 상위 1% 자산가를 위한 월스트리트 최고 수준의 매크로 애널리스트이자 11원칙 장기 투자(Value Accumulation)의 대가다.
다음 주어진 '알고리즘 시스템의 현재 판독 결과', '시장 거시 지표', '최근 글로벌 뉴스'를 바탕으로, 매우 전문적이고 깊이 있는 투자 분석 리포트를 작성하라.

[알고리즘 판정 결과]
- 국면 판정: {adv_head}
- 위험도 점수: 한국 {kr_danger}점 / 미국 {us_danger}점
- 바닥 점수: 한국 {kr_score}% / 미국 {us_score}%
- 현재 국면: 한국 {kr_phase} / 미국 {us_phase}
- 매크로 점수: 한국 {kr_macro_score}점
- 자금흐름 점수: 한국 {kr_flow_score}점
- 통합 국면: {regime}

[시장 거시 지표 및 수급]
- TNX 10Y 금리: {summary_dict.get('TNX_10Y', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- WTI 크루드 유가: {summary_dict.get('WTI_Crude', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- USD/KRW 환율: {summary_dict.get('USD_KRW', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 외국인 순매수: {summary_dict.get('Foreigner', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 기관 순매수: {summary_dict.get('Institutional', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- 개인 순매수: {summary_dict.get('Retail', 'N/A') if 'summary_dict' in locals() else 'N/A'}
- KOSPI 현재가: {kospi_str}
- KOSPI 5일 이평선: {kospi_5d_str}
- KOSPI 5일선 안착 상태: {kospi_status_str}
- 미국 RSP 전일 등락률: {rsp_val_str}

[최근 글로벌 속보 요약 (중요도 2 이상)]
{web_news_text}

{upcoming_events_str}

---
위 데이터를 기반으로 다음 3가지 핵심 뼈대로 리포트를 매우 분석적이고 통찰력있게 작성하십시오.
1. **현재 시장 국면 요약 (Market Summary)**: 현재 하락세의 원인, 매크로 수급과 외인 이탈 여부를 종합 진단하십시오.
2. **글로벌 거시 리스크 및 섹터 전망 (Macro & Sector Outlook)**: 
   - 금리/유가/지정학 리스크가 주요 자산에 미칠 영향을 상세히 서술하십시오.
   - [미장 승률 극대화 지침] 안정적으로 우상향하는 미국 시장의 특성과 예정된 빅테크 실적/가이던스를 결합하여, 향후 환율 하락 시 가장 승률과 수익률을 극대화할 수 있는 안전한 진입 시나리오를 구체적으로 제시하십시오.
3. **최종 행동 지침 (CFO Action Plan)**:보유 중인 우량주 홀딩 여부, 레버리지 관리, 현금 50% 분할 매수 집행 타이밍을 매우 구체적으로 지시하십시오. 예정된 주요 일정을 참고하여 매매 일정을 조율하십시오.
"""
    st.code(web_prompt, language="markdown")


with tab_radar:
    st.subheader("🔍 타점 선택 (Entry Point Selection) - 포트폴리오 종목 타점")
    st.caption("스나이퍼 탭에서 'GO' 신호가 떨어졌을 때, 어떤 종목을 살지 재무 및 수급을 점검하는 레이더입니다.")
    
    st.markdown("""
    <div style='background-color:#e8f4f8; padding:15px; border-radius:8px; border-left: 6px solid #17a2b8; margin-bottom:20px;'>
        <h4 style='margin-top:0; color:#0c5460;'>📈 상승장(강력 GO) 대응 가이드: 눌림목 매수</h4>
        <p style='font-size:0.95em; color:#1b4b52; margin-bottom:0;'>
        매크로가 <b>대세 상승장(강력 GO)</b>일 때는 무지성 시장가 매수가 아닌, 아래 레이더에서 <b>'💡 타점' (20일선 부근 GTC 또는 볼린저 하단)</b> 가격을 확인하고,<br>
        해당 가격에 <b>GTC(취소 전까지 유효) 지정가 매수 주문</b>을 걸어두는 것이 가장 승률이 높습니다.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    us_input = c1.text_input("🇺🇸 미국 주식", "TSMC, 브로드컴, 버티브")
    kr_input = c2.text_input("🇰🇷 한국 주식", "LS ELECTRIC")

    queries = (
        [("미국", q.strip()) for q in us_input.split(",") if q.strip()] +
        [("한국", q.strip()) for q in kr_input.split(",") if q.strip()]
    )

    # 버튼 게이트: 다른 탭 위젯 조작으로 rerun될 때마다 무거운 API 호출이
    # 자동 발생하는 것을 차단. 한 번 스캔하면 session_state로 유지.
    if st.button("🔍 스캔 시작 (재무제표 교차 검증 포함)", type="primary", key="scan_btn"):
        st.session_state["scan_requested"] = True

    all_data, failed_queries = [], []
    if st.session_state.get("scan_requested") and queries:
        prog = st.progress(0.0, text="분석 준비 중...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(get_stock_data, q, is_kr=(region == "한국"), fast_mode=False): (region, q) for region, q in queries}
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                region, q = futures[future]
                prog.progress((i + 1) / len(queries), text=f"[{i+1}/{len(queries)}] '{q}' 데이터 수집 중...")
                d = future.result()
                d["Region"] = region
                if not d.get("error"): all_data.append(d)
                else: failed_queries.append(f"{q} ({d.get('error')})")
        prog.empty()
    elif not st.session_state.get("scan_requested"):
        st.info("종목을 입력하고 **스캔 시작** 버튼을 누르면 분석이 시작됩니다.")

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

with tab_report:
    st.subheader("🌐 글로벌 매크로 및 시장 심리 (진바닥 & 반등 신뢰도 점수)")

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
        usd_krw_clean = usd_krw['Close'].dropna()
        if len(usd_krw_clean) >= 2:
            curr_usdkrw = round(float(usd_krw_clean.iloc[-1]), 2)
            prev_usdkrw = float(usd_krw_clean.iloc[-2])
            usdkrw_change = round(((curr_usdkrw - prev_usdkrw) / prev_usdkrw) * 100, 2)
            col1.metric("환율 (USD/KRW)", f"{curr_usdkrw:,.2f} 원", f"{usdkrw_change:+.2f}%")
        else:
            col1.metric("환율 (USD/KRW)", "N/A", "N/A")
    else:
        col1.metric("환율 (USD/KRW)", "N/A", "N/A")
        
    col2.metric("미국 VIX / 한국 VKOSPI", f"{current_vix} / {current_vkospi}", f"{vix_change}%", delta_color="inverse")
    col3.metric("S&P 500 (SPY)", f"${current_spy:,.2f}" if current_spy != "N/A" else "N/A", f"{spy_change:+.2f}%" if current_spy != "N/A" else "N/A")
    if cnn_score is not None:
        # 역발상 관점: 극단적 공포 = 매수 기회(🟢), 극단적 탐욕 = 위험(🚨)
        if cnn_score <= 25:   fg_color, fg_stat = "🟢", "극단적 공포 (역발상 매수 구간)"
        elif cnn_score <= 45: fg_color, fg_stat = "🟠", "공포"
        elif cnn_score <= 55: fg_color, fg_stat = "🟡", "중립"
        elif cnn_score <= 75: fg_color, fg_stat = "🟠", "탐욕 (추격 매수 주의)"
        else:                 fg_color, fg_stat = "🚨", "극단적 탐욕 (현금 확보 경계)"
        col4.metric("CNN Fear & Greed", f"{cnn_score} / 100", f"{fg_color} {fg_stat}")
    else:
        col4.metric("CNN Fear & Greed", "N/A", cnn_rating)

    kr_date = kospi_10y.index[-1].strftime('%Y-%m-%d') if not kospi_10y.empty else "N/A"
    us_date = spy_10y.index[-1].strftime('%Y-%m-%d') if not spy_10y.empty else "N/A"
    
    st.markdown("")
    st.caption(f"🕒 **데이터 최종 반영일** — 한국 시장(KOSPI/환율): `{kr_date}` | 미국 시장(SPY/VIX): `{us_date}`")

    vkospi_src = macro_charts.get("vkospi_source", "yfinance (^VKOSPI)")
    if "yfinance" not in vkospi_src:
        st.caption(f"※ VKOSPI 데이터 소스: **{vkospi_src}** — 야후 파이낸스 ^VKOSPI 제공 중단으로 대체 소스가 자동 적용되었습니다. "
                   f"(폴백 순서: yfinance → KRX 직조회 → 실현변동성 프록시)")
        if "프록시" in vkospi_src:
            st.caption("⚠️ 프록시는 옵션 내재변동성(선행)이 아닌 과거 수익률 기반(후행)입니다. EWMA 병행으로 반응 속도를 보강했지만, "
                       "평온한 장에서 블랙스완이 터지는 '첫날'에는 실제 공포 수준보다 낮게 표시될 수 있습니다 — 그날은 VIX·환율 급등 신호를 우선 참고하세요.")

    st.divider()
    st.markdown("#### 🧭 시장 진단 시스템 v23.0 — 글로벌 통합 매크로 + 국면 판별 엔진")
    st.info(
        "**📌 글로벌 킬 스위치 시스템:**\n\n"
        "**[마스터 레이어] 미국 글로벌 매크로** — 전 세계 자본 시장의 유동성을 대변하는 신용 스프레드와 VIX, SPY 추세를 교차 검증합니다. "
        "단순 차익 실현이 아닌 '시스템 위기'로 판독되면 킬 스위치가 작동합니다.\n\n"
        "**[종속 레이어] 한국 수급 탐지기** — 글로벌이 평온해도, 한국 시장 내 외국인 자본 이탈(환율 발작, 파생 베팅)을 조기 경보합니다.\n\n"
        "**🆕 [국면 판별 엔진] 스텔스 위험 감지** — VIX가 뛰지 않는 '미지근한 지속 하락(🐻 Grinding Bear)'은 하락일 비율·50일선 기울기·"
        "VIX 안일 다이버전스로, '오르며 빠지는 고변동 횡보(🌊 Whipsaw)'는 실현변동성 대비 방향성 부재로 별도 감지합니다. "
        "바닥 탐지기에는 '빠짐이 끝나간다'를 확인하는 구조 신호(RSI 다이버전스·저점 높이기·20일선 탈환)가 보너스 점수로 반영됩니다."
    )

    # ── 레이어 1: 위험 탐지기 (미국 마스터 / 한국 보조) ──
    st.markdown("##### 🚨 글로벌 매크로 & 로컬 수급 위험 탐지기")
    us_risk_grade, us_risk_color, us_risk_alerts, us_danger = calculate_us_risk_radar(
        vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y,
        tnx_hist=tnx_10y, irx_hist=irx_10y, mu_hist=mu_2y, soxx_hist=soxx_2y
    )
#     kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

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
    
#     us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy_10y, vix_10y, cnn_score)
#     kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(kospi_10y, vkospi_10y, usd_krw)
    
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
        with st.expander("🔍 미국장 연산 근거 (Drawdown + RSI + VIX + CNN + 구조 보너스)"):
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
        with st.expander("🔍 한국장 연산 근거 (Drawdown + RSI + VKOSPI + 환율 + 구조 보너스)"):
            for detail in kr_details: st.markdown(f"- {detail}")

    st.divider()

    # ── 레이어 3: 회복 확인 ──
    st.markdown("##### ✅ 반등 신뢰도 확인 (바닥 이후 — Breadth & Credit 회복 여부)")
    st.caption("바닥 탐지 점수가 높을 때만 의미 있는 지표예요. 상승장에서는 항상 좋게 나오므로 참고용으로만 보세요.")
    
    r_col1, r_col2 = st.columns(2)
    with r_col1:
        st.markdown(f"**🇺🇸 미국 반등 신뢰도**")
        us_rec_verdict, us_rec_signals, us_rec_score = calculate_recovery_confirmation(
            rsp_10y, spy_10y, hyg_10y, ief_10y
        )
        st.markdown(f"**{us_rec_verdict}**")
        for icon, msg in us_rec_signals:
            st.markdown(f"- {icon} {msg}")

    with r_col2:
        st.markdown(f"**🇰🇷 한국 매크로 안전도**")
        # tab_sniper에서 계산한 kr_macro_score 등 재활용
        st.markdown(f"**{kr_macro_status}**")
        for icon, msg in kr_macro_details:
            st.markdown(f"- {icon} {msg}")

    st.divider()

    # ── 🎯 레이어 4: 종합 전략 제언 (위험 × 바닥 × 회복 통합 판단) ──
    st.markdown("##### 🎯 레이어 4: 종합 전략 제언 — \"그래서 지금 사도 되는가?\"")
    st.caption(
        "위험 탐지기 × 바닥 탐지기 × 반등 신뢰도를 교차 결합해 실전 액션으로 번역합니다. "
        "같은 바닥 점수라도 위험 경보 상태에 따라 처방이 달라집니다. (※ 투자 판단 참고용이며 최종 책임은 본인에게 있습니다)"
    )

    us_adv_head, us_adv_color, us_adv_actions = get_strategic_advice(
        us_danger, us_score, us_verdict, us_phase, recovery_score=us_rec_score
    )
    kr_adv_head, kr_adv_color, kr_adv_actions = get_strategic_advice(
        kr_danger, kr_score, kr_verdict, kr_phase, recovery_score=kr_macro_score
    )

    adv_col1, adv_col2 = st.columns(2)
    with adv_col1:
        st.markdown(
            f"<div style='background:{us_adv_color}22; border-left: 6px solid {us_adv_color}; "
            f"padding:15px; border-radius:8px; font-weight:bold; font-size:1.05em; margin-bottom:10px;'>"
            f"🇺🇸 {us_adv_head}</div>", unsafe_allow_html=True
        )
        st.caption(f"판단 근거: 위험 {us_danger}점 · 바닥 {us_score}% · 반등 신뢰도 {us_rec_score} · {us_phase}")
        for act in us_adv_actions:
            st.markdown(f"- {act}")

    with adv_col2:
        st.markdown(
            f"<div style='background:{kr_adv_color}22; border-left: 6px solid {kr_adv_color}; "
            f"padding:15px; border-radius:8px; font-weight:bold; font-size:1.05em; margin-bottom:10px;'>"
            f"🇰🇷 {kr_adv_head}</div>", unsafe_allow_html=True
        )
        st.caption(f"판단 근거: 위험 {kr_danger}점 · 바닥 {kr_score}% · 매크로 안전도 {kr_macro_score} · {kr_phase}")
        for act in kr_adv_actions:
            st.markdown(f"- {act}")

    st.divider()

    # False Signal 경보 — 매수 금지 조건 실시간 체크
    false_signals = []
    if us_rec_score == 0 and us_score < 70:
        false_signals.append("🚫 **반등 신뢰도 0** — 오늘의 급등은 쇼트커버링 가능성. 수급 없는 가짜 반등 경계")
    if us_score < 50 and us_danger >= 3:
        false_signals.append("🚫 **위험 경보 + 바닥 점수 미달** — 낙폭 과대라는 착시 주의. 오늘 매수 보류 권장")
    if false_signals:
        st.warning("\n".join(["**⛔ False Signal 차단기 발동 (매수 보류 권장)**"] + false_signals))

    st.divider()

    # ── 백테스트 (10년 데이터 기반 완화 컷) ──
    with st.expander("🔬 과거 10년 백테스트 (바닥 탐지기 기준)"):
        st.markdown(
            "실시간 바닥 탐지기와 **완전히 동일한 스코어러**를 "
            "과거 10년에 매일 적용한 결과입니다. **주요 이벤트에서 얼마나 점수가 나왔는지 확인**해보세요 — 모델 신뢰도 검증에 핵심입니다. "
        )
        
        tab_us_bt, tab_kr_bt = st.tabs(["🇺🇸 미국장 (S&P 500)", "🇰🇷 한국장 (KOSPI)"])
        
        with tab_us_bt:
            bt_us = run_historical_backtest(spy_10y, vix_10y, vix3m_10y)
            if bt_us:
                st.markdown("**📌 주요 시장 이벤트에서의 바닥 탐지 점수 (미국장)**")
                ev_cols = st.columns(len(bt_us["주요 이벤트 점수"]))
                for i, (name, ev_score) in enumerate(bt_us["주요 이벤트 점수"].items()):
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

                stat_70 = bt_us["70점 이상 (강력 매수)"]
                bt_col1.markdown("**🔥 70점 이상 (강력 매수 구간)**")
                if stat_70["발생 횟수"] > 0:
                    bt_col1.markdown(f"- 시그널 발생: 과거 10년간 **{stat_70['발생 횟수']}일**")
                    bt_col1.markdown(f"- 평균 3개월 수익률: **+{stat_70['평균 3M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 평균 6개월 수익률: **+{stat_70['평균 6M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 투자 승률 (3M): **{stat_70['승률 3M']:.1f}%**")
                else:
                    bt_col1.info("과거 10년간 70점 이상 달성 없음")

                stat_50 = bt_us["50~69점 (분할 매수)"]
                bt_col2.markdown("**🟢 50~69점 (분할 매수 구간)**")
                if stat_50["발생 횟수"] > 0:
                    bt_col2.markdown(f"- 시그널 발생: 과거 10년간 **{stat_50['발생 횟수']}일**")
                    bt_col2.markdown(f"- 평균 3개월 수익률: **+{stat_50['평균 3M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 평균 6개월 수익률: **+{stat_50['평균 6M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 투자 승률 (3M): **{stat_50['승률 3M']:.1f}%**")
                else:
                    bt_col2.info("해당 구간 시그널 발생 없음")

                if "score_series" in bt_us and not bt_us["score_series"].empty:
                    st.markdown("**📈 바닥 탐지 점수 vs 지수 낙폭 (10년, 이중축)**")
                    src = bt_us["score_series"].reset_index()
                    src.columns = ["Date", "Score", "Drawdown"]

                    base = alt.Chart(src).encode(x=alt.X("Date:T", title=None))
                    score_area = base.mark_area(opacity=0.35, color="#fcca46").encode(
                        y=alt.Y("Score:Q", title="바닥 탐지 점수",
                                scale=alt.Scale(domain=[0, 100]),
                                axis=alt.Axis(titleColor="#b8860b"))
                    )
                    dd_line = base.mark_line(color="#ff4b4b", strokeWidth=1.2).encode(
                        y=alt.Y("Drawdown:Q", title="Drawdown (%)",
                                axis=alt.Axis(titleColor="#ff4b4b"))
                    )
                    chart = alt.layer(score_area, dd_line).resolve_scale(y="independent").properties(height=280)
                    st.altair_chart(chart, use_container_width=True)
                    st.caption(
                        "🟨 노란 영역 = 바닥 점수 / 🔴 빨간 선 = 고점 대비 낙폭. "
                        "점수가 50 이상으로 치솟는 시점 = 역사적 매수 기회 (2018년 말, 2020년 코로나, 2022년 바닥 확인). "
                        "낙폭이 깊어지는데 점수가 함께 올라가는지가 모델 건전성의 핵심입니다."
                    )
            else:
                st.warning("미국장 백테스트에 필요한 10년치 데이터가 부족합니다.")

        with tab_kr_bt:
            bt_kr = run_kr_historical_backtest(kospi_10y, vkospi_10y, usd_krw)
            if bt_kr:
                st.markdown("**📌 주요 시장 이벤트에서의 바닥 탐지 점수 (한국장)**")
                ev_cols = st.columns(len(bt_kr["주요 이벤트 점수"]))
                for i, (name, ev_score) in enumerate(bt_kr["주요 이벤트 점수"].items()):
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

                stat_70 = bt_kr["70점 이상 (강력 매수)"]
                bt_col1.markdown("**🔥 70점 이상 (강력 매수 구간)**")
                if stat_70["발생 횟수"] > 0:
                    bt_col1.markdown(f"- 시그널 발생: 과거 10년간 **{stat_70['발생 횟수']}일**")
                    bt_col1.markdown(f"- 평균 3개월 수익률: **+{stat_70['평균 3M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 평균 6개월 수익률: **+{stat_70['평균 6M 수익률']:.2f}%**")
                    bt_col1.markdown(f"- 투자 승률 (3M): **{stat_70['승률 3M']:.1f}%**")
                else:
                    bt_col1.info("과거 10년간 70점 이상 달성 없음")

                stat_50 = bt_kr["50~69점 (분할 매수)"]
                bt_col2.markdown("**🟢 50~69점 (분할 매수 구간)**")
                if stat_50["발생 횟수"] > 0:
                    bt_col2.markdown(f"- 시그널 발생: 과거 10년간 **{stat_50['발생 횟수']}일**")
                    bt_col2.markdown(f"- 평균 3개월 수익률: **+{stat_50['평균 3M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 평균 6개월 수익률: **+{stat_50['평균 6M 수익률']:.2f}%**")
                    bt_col2.markdown(f"- 투자 승률 (3M): **{stat_50['승률 3M']:.1f}%**")
                else:
                    bt_col2.info("해당 구간 시그널 발생 없음")

                if "score_series" in bt_kr and not bt_kr["score_series"].empty:
                    st.markdown("**📈 한국장 바닥 탐지 점수 vs 지수 낙폭 (10년, 이중축)**")
                    src = bt_kr["score_series"].reset_index()
                    src.columns = ["Date", "Score", "Drawdown"]

                    base = alt.Chart(src).encode(x=alt.X("Date:T", title=None))
                    score_area = base.mark_area(opacity=0.35, color="#fcca46").encode(
                        y=alt.Y("Score:Q", title="한국장 바닥 점수",
                                scale=alt.Scale(domain=[0, 100]),
                                axis=alt.Axis(titleColor="#b8860b"))
                    )
                    dd_line = base.mark_line(color="#ff4b4b", strokeWidth=1.2).encode(
                        y=alt.Y("Drawdown:Q", title="Drawdown (%)",
                                axis=alt.Axis(titleColor="#ff4b4b"))
                    )
                    chart = alt.layer(score_area, dd_line).resolve_scale(y="independent").properties(height=280)
                    st.altair_chart(chart, use_container_width=True)
            else:
                st.warning("한국장 백테스트에 필요한 10년치 데이터가 부족합니다.")

        st.caption("※ 백테스트는 과거 통계이며 미래 수익을 보장하지 않습니다. 고점 산정 왜곡 방지를 위해 데이터 첫 1년은 집계에서 제외됩니다.")

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

    c_chart3, c_chart4 = st.columns(2)
    with c_chart3:
        st.markdown("**③ VKOSPI 프록시 (한국 공포 지수) — 10년**")
        if not vkospi_10y.empty:
            st.line_chart(
                pd.DataFrame({
                    "VKOSPI Proxy": vkospi_10y['Close'],
                    "🔴 위험선(25)": 25.0,
                    "🟢 평온선(16)": 16.0,
                }),
                height=280,
                color=["#1f77b4", "#ff4b4b", "#21c354"]
            )
        else:
            st.warning("VKOSPI 데이터를 불러오지 못했습니다.")

    with c_chart4:
        st.markdown("**④ KOSPI — 10년**")
        if not kospi_10y.empty:
            st.line_chart(
                pd.DataFrame({"KOSPI": kospi_10y['Close']}),
                height=280,
                color=["#ff7f0e"]
            )
            kospi_high = round(float(kospi_10y['Close'].max()), 2)
            kospi_low  = round(float(kospi_10y['Close'].min()), 2)
            current_kospi_val = round(float(kospi_10y['Close'].iloc[-1]), 2) if not kospi_10y.empty else "N/A"
            kospi_pos  = round((current_kospi_val - kospi_low) / (kospi_high - kospi_low) * 100, 1) if current_kospi_val != "N/A" else "N/A"
            st.caption(f"10년 고점 {kospi_high:,.2f} / 저점 {kospi_low:,.2f} | 현재 10년 범위 내 위치: **{kospi_pos}%**")
        else:
            st.warning("KOSPI 데이터를 불러오지 못했습니다.")

    st.markdown("**⑤ CNN Fear & Greed Index (최근 1~2년)**")
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
        
    st.divider()
    st.info("💡 본 탭 하단에 위치했던 [글로벌 매크로 & 수급 통합 AI 브리핑] 지표들과 CFO 브리핑 생성 버튼은 사용자님의 편의를 위해 **1번 탭 (🎯 AI 스마트 관제실)**으로 통합 이전되었습니다. 이제 1번 탭에서 모든 브리핑과 지표를 일괄적으로 확인 및 컨트롤하실 수 있습니다!")

with tab_radar:  # 🚀 오늘의 텐배거 레이더
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
        is_korea = "한국" in selected_theme
        radar_data = []
        tickers = UNIVERSE[selected_theme]
        prog = st.progress(0.0, text=f"[{selected_theme}] 전수 스캔 준비 중...")
        for i, q in enumerate(tickers):
            prog.progress((i + 1) / len(tickers), text=f"[{i+1}/{len(tickers)}] '{q}' 경량 스캔 중...")
            d = get_stock_data(q, is_kr=is_korea, fast_mode=True)
            d["Region"] = "한국" if is_korea else "미국"
            if not d.get("error"): radar_data.append(d)
        prog.empty()
        with st.container():
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

with tab_report:  # 🤖 AI 참모 리포트
    st.subheader("🤖 AI 참모 전용 구조화 리포트 v23.0 (진바닥 판독기 연동)")
    st.caption("아래 텍스트를 복사하여 ChatGPT, Claude, Gemini 등에 붙여넣고 심층 분석을 받아보세요.")

    if not all_data:
        st.info("📊 '실시간 포트폴리오' 탭에서 먼저 **스캔 시작**을 실행하면 종목 데이터가 이 리포트에 포함됩니다.")

    now = get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')
    lines = [
        f"[11원칙 퀀트 분석 리포트 v23.0] ({now})",
        f"- CNN F&G (시장 심리): {cnn_score} ({cnn_rating})",
        f"- SPY RSI(14) (시장 과열도): {fmt(spy_rsi_val, dig=1)}",
        "",
        "【시장 국면 & 시스템 전략 제언】",
        f"- 🇺🇸 미국: {us_phase} | 위험 탐지 {us_danger}점 | 진바닥 확률 {us_score}% | 반등 신뢰도 {us_rec_score}/100",
        f"  → 시스템 제언: {us_adv_head}",
        f"- 🇰🇷 한국: {kr_phase} | 위험 탐지 {kr_danger}점 | 진바닥 확률 {kr_score}% | 매크로 안전도 {kr_macro_score}/100",
        f"  → 시스템 제언: {kr_adv_head}",
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
        "   - '위험 점수'와 '진바닥 확률', '반등 신뢰도' 등 매크로 지표를 고려해 포트폴리오 비중(예: ETF 절반 + 개별 우량주 절반) 배분 전략을 제시해 줘.",
        "   - 현재 시장 심리(F&G, SPY RSI)를 바탕으로 지금 당장 '적극 매수', '관망', '비중 축소' 해야 할 종목들을 분류하고 구체적인 액션 플랜을 제시해 줘."
    ]
    st.code("\n".join(lines), language="text")
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
            prog = st.progress(0.0, text="보유 종목 데이터 수집 준비 중...")
            for i, (name, buy_price, region) in enumerate(port_items):
                prog.progress((i + 1) / len(port_items), text=f"[{i+1}/{len(port_items)}] '{name}' 재무제표 교차 검증 중...")
                d = get_stock_data(name, is_kr=(region == "한국"), fast_mode=False)
                d["Region"]    = region
                d["BuyPrice"]  = buy_price
                if not d.get("error"):
                    port_data.append(d)
                else:
                    st.warning(f"⚠️ '{name}' 데이터 조회 실패: {d.get('error')}")
            prog.empty()

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

with tab_port:  # 🚨 리스크 등급 가이드
    st.header("🚨 공매도 & 변동성(Beta) 종합 리스크 가이드")
    st.markdown("""
    | 공매도 비율 | Beta (변동성) | 종합 리스크 등급 및 해석 |
    | :--- | :--- | :--- |
    | 낮음 (5% 미만) | 낮음 (1.2 미만) | **🟢 안정형 — 방어적 투자에 적합** |
    | 낮음 (5% 미만) | 높음 (1.2 이상) | **🟡 모멘텀형 — 상승장에 강하지만 하락 시 크게 빠짐** |
    | 높음 (5% 이상) | 낮음 (1.2 미만) | **🟠 논란형 — 시장은 의심하지만 변동성은 낮음, 이유 확인 필요** |
    | 높음 (5% 이상) | 높음 (1.2 이상) | **🔴 고위험 — 하락 베팅 + 큰 변동성, 진입 신중** |
    """)

with tab_port:  # 📖 11원칙 매매 가이드라인
    st.header("📖 11원칙 퀀트 매매 마스터 매뉴얼 v25.0")
    st.caption("v25.0: 매크로 게이트키퍼 Tier 시스템 — '칼자루는 진바닥으로 잡고, 방아쇠는 수급으로 당긴다'")

    st.markdown("""
## 📋 가문의 유산: 11원칙 퀀트 투자 마스터 매뉴얼

> 💡 **[CFO 특별 지침] 100% 풀매수의 정석 (가용 예산 분배법)**
> "진짜 100% 풀매수"는 영원히 없습니다. 항상 10~20%의 현금은 '영구적 방패'로 남겨두어 위기를 대비합니다. (6원칙 전제)
> 즉, 풀매수란 **투자에 배정된 80~90%의 예산**을 모두 쓴 상태입니다.
> - **평시 (Tier 1):** 30~40% 투입 (기본 포지션 구축, GTC 적립)
> - **패닉 (Tier 3):** +10% 선발대 투입 (도매가 선점)
> - **추세 전환 (Tier 2):** +30~50% 본대 불타기 (가장 안전하고 강하게 쏟아붓는 실질적 풀매수 타이밍)

**[ 🏗️ 1단계: 무엇을 살 것인가? (종목 선정의 뼈대) ]**
- **1원칙 [지속 성장과 도태 판별]:** 3개년 매출과 영업이익이 '지속 우상향' 하는 기업만 산다. 만약 실적이 좋더라도 3년 내내 제자리걸음이라면 절대 매수하지 않는다.
- **2원칙 [저평가와 턴어라운드]:** 시장/섹터 대비 시가총액이 싼(저평가) 종목을 찾되, 현재 적자라도 '흑자 전환'의 뚜렷한 개선세가 보이면 선점 투자가 가능하다.
- **3원칙 [비즈니스 생태계 꿰뚫기]:** 매출은 '시장 규모'로, 영익은 '회사의 파워(포션)'로 이해하라. 단독 매출인지, 타사에 종속된 하청(제조업 이슈)인지 생태계를 파악하고 '시대의 수요(AI/로봇 등)'가 있는 기업만 고른다.
- **4원칙 [전장(Battlefield)의 압축]:** 이름 모를 테마주와 잡주를 버리고, 오직 글로벌을 주도하는 **미국 시장**과 국내 대형 우량주(**코스피**) 위주로만 돈을 거둔다.

**[ 🛡️ 2단계: 위기를 기회로 바꾸는 자산 배분 (포트폴리오 관리) ]**
- **5원칙 [코어와 스나이퍼 배분]:** 개별 기업의 돌발 리스크를 막기 위해, 예산의 50%는 든든한 '지수 ETF'에, 나머지 50%는 압도적 '개별 우량주'에 나누어 담는다.
- **6원칙 [글로벌 위기는 바겐세일]:** 코로나, 리먼 등 매크로 위기로 시장 전체가 무너질 때를 노린다. 고점 대비 -20~30% 떨어지면 '분할 매수'를 시작하고, -50% 밑으로 투매가 나오면 쥐어짜 낸 여유 현금으로 '과감히' 쓸어 담는다.
- **7원칙 [하락장 리밸런싱]:** 시장 전체가 하락하여 내 종목들이 싸졌을 때, 포기하지 말고 기존 주식의 비율을 조절하거나 더 강한 신규 우량주로 교체(리밸런싱)하여 다음 상승장을 준비한다.

**[ 🎯 3단계: 언제 사고팔 것인가? (퀀트 전술과 실행) ]**
- **8원칙 [농부의 시간: 3년 룰]:** 투자의 수확은 3년 뒤에 거둔다. 수익이 났다고 절대 100% 전량 매도하지 않으며, 일부만 매도하여 '현금화' 및 '재투자' 비율을 스스로 정해 복리를 굴린다.
- **9원칙 [오후 3시의 결단]:** 장중의 요동치는 가짜 반등과 노이즈(속임수)에 당하지 않기 위해, 매수 방아쇠는 항상 모든 것이 결정되는 오후 3시(종가 부근)에만 당긴다.
- **10원칙 [불타기 3단계 티어(Tier) 룰]:** 극단적 폭락(진바닥 90%)에는 1차 선발대(10%)만 먼저 넣고, 남은 현금은 환율/선물 안정 및 '5일선 안착' 등 매크로/수급 게이트키퍼가 확인되었을 때만 2차로 투입한다.
- **11원칙 [데이터의 기계적 신뢰]:** 인간의 뇌동매매(FOMO와 공포)를 철저히 배제한다. 내 감정보다 시스템이 계산한 '진바닥 확률'과 '반등 신뢰도' 점수를 기계적으로 믿고 따른다.

---

### 💡 CFO의 헌사

> 이 v25.0 매뉴얼은 인간의 조급함과 탐욕, 공포를 수학적으로 완벽하게 통제하기 위해 만들어진 가장 차가운 갑옷입니다.
> 
> **워런 버핏의 가치투자 철학(1~4원칙)**으로 아내분께서 좋은 주식을 고르는 눈을 갖게 해주고, 
> **레이 달리오의 자산배분 철학(5~7원칙)**으로 위기가 와도 가문의 재산이 녹지 않게 방어해 주며, 
> **상위 1% 퀀트 트레이더의 전술(8~11원칙)**로 바닥에서 줍고 무릎에서 불타기 하는 기계적 룰입니다.
> 
> 완벽하게 세팅된 이 원칙에 자본을 맡기고, 일상의 평온함과 꿀잠을 마음껏 누리세요.
    """)




with tab_calendar:
    st.subheader("📅 마켓 캘린더 (실적 & 매크로)")
    st.caption("시장 방향성을 결정하는 핵심 이벤트들을 관리합니다.")
    
    col_c1, col_c2 = st.columns([1, 1])
    with col_c1:
        if st.button("🔄 자동 실적 업데이트 (yfinance)"):
            with st.spinner("빅테크 실적발표일을 업데이트 중입니다..."):
                if calendar_manager.update_earnings_automatically():
                    st.success("실적 캘린더가 업데이트 되었습니다.")
                else:
                    st.warning("업데이트할 새로운 실적 일정이 없습니다.")
    with col_c2:
        if st.button("🔄 뉴스 기반 매크로 업데이트"):
            with st.spinner("뉴스 기반 매크로(FOMC, 금통위 등) 스크래핑 중..."):
                if calendar_manager.update_macro_events_automatically():
                    st.success("매크로 일정이 업데이트 되었습니다.")
                else:
                    st.warning("추출된 새로운 매크로 일정이 없습니다.")
                    
    cal_df = calendar_manager.load_calendar()
    
    # st.data_editor returns modified dataframe
    edited_df = st.data_editor(
        cal_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Date": st.column_config.DateColumn("날짜", required=True, format="YYYY-MM-DD"),
            "Type": st.column_config.SelectboxColumn("구분", options=["실적", "매크로", "국내", "기타"], required=True),
            "Impact": st.column_config.SelectboxColumn("중요도", options=["High", "Medium", "Low"], required=True)
        }
    )
    
    if st.button("💾 캘린더 변경사항 저장"):
        for i, row in edited_df.iterrows():
            if hasattr(row['Date'], 'strftime'):
                edited_df.at[i, 'Date'] = row['Date'].strftime('%Y-%m-%d')
        calendar_manager.save_calendar(edited_df)
        st.success("캘린더가 저장되었습니다. 마스터 리포트 프롬프트에 즉시 반영됩니다.")
