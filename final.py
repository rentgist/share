import streamlit as st
import pandas as pd
import numpy as np
import datetime
import altair as alt

from config import get_kst_now
from data_loader import (
    get_real_cnn_fg, 
    get_macro_charts, 
    get_sector_baseline, 
    get_stock_data,
    get_upcoming_events
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
        calculate_kr_recovery_confirmation,
        get_strategic_advice,
        run_historical_backtest,
        get_cashflow_interpretation,
        relative_strength_label,
        get_ai_signal,
        calculate_smart_target,
        get_tenbagger_signal
    )
except ImportError as e:
    st.error(f"🚨 ImportError 발생: {e}")
    st.stop()
except Exception as e:
    st.error(f"🚨 알 수 없는 오류 발생: {e}")
    st.stop()

st.set_page_config(page_title="11원칙 퀀트 대시보드 v23.0", page_icon="🧭", layout="wide")

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
st.title("🧭 11원칙 퀀트 트레이딩 대시보드 v23.0")
st.caption("v23.0: 국면 판별 엔진(Regime Engine) 탑재 — 스텔스 약세장(Grinding Bear)·고변동 횡보(Whipsaw) 감지 + 바닥 다지기(Basing) 구조 점수 + 백테스트·실시간 점수 스케일 통일")

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
    us_risk_grade, us_risk_color, us_risk_alerts, us_danger = calculate_us_risk_radar(vix_10y, vix3m_10y, hyg_10y, ief_10y, spy_10y)
    kr_risk_grade, kr_risk_color, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi_10y, usd_krw, kospi_10y)

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
        st.markdown(f"**🇰🇷 한국 반등 신뢰도**")
        kr_rec_verdict, kr_rec_signals, kr_rec_score = calculate_kr_recovery_confirmation(
            kospi_10y, usd_krw
        )
        st.markdown(f"**{kr_rec_verdict}**")
        for icon, msg in kr_rec_signals:
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
        kr_danger, kr_score, kr_verdict, kr_phase, recovery_score=kr_rec_score
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
        st.caption(f"판단 근거: 위험 {kr_danger}점 · 바닥 {kr_score}% · 반등 신뢰도 {kr_rec_score} · {kr_phase}")
        for act in kr_adv_actions:
            st.markdown(f"- {act}")

    st.divider()

    # ── 백테스트 (10년 데이터 기반 완화 컷) ──
    with st.expander("🔬 과거 10년 백테스트 (미국 바닥 탐지기 기준)"):
        st.markdown(
            "실시간 바닥 탐지기와 **완전히 동일한 스코어러**(Drawdown + RSI + VIX + 구조 보너스 + 칼날 패널티)를 "
            "과거 10년에 매일 적용한 결과입니다. **주요 이벤트에서 얼마나 점수가 나왔는지 확인**해보세요 — 모델 신뢰도 검증에 핵심입니다. "
            "(CNN F&G는 과거 데이터가 없어 제외되지만, 만점 대비 %로 정규화하므로 실시간 점수와 같은 자로 비교 가능합니다.)"
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
                st.markdown("**📈 바닥 탐지 점수 vs 지수 낙폭 (10년, 이중축)**")
                src = bt["score_series"].reset_index()
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

            st.caption("※ 백테스트는 과거 통계이며 미래 수익을 보장하지 않습니다. 고점 산정 왜곡 방지를 위해 데이터 첫 1년은 집계에서 제외됩니다.")
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

with tab1:
    st.subheader("🔍 관심 종목 스캔")
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
        for i, (region, q) in enumerate(queries):
            prog.progress((i + 1) / len(queries), text=f"[{i+1}/{len(queries)}] '{q}' 분석 중...")
            d = get_stock_data(q, is_kr=(region == "한국"), fast_mode=False)
            d["Region"] = region
            if not d.get("error"): all_data.append(d)
            else: failed_queries.append(q)
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

with tab3:
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
        f"- 🇰🇷 한국: {kr_phase} | 위험 탐지 {kr_danger}점 | 진바닥 확률 {kr_score}% | 반등 신뢰도 {kr_rec_score}/100",
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
        "   - 내가 이 질문 뒤에 이어서 '오늘의 주요 뉴스나 호재/악재'를 알려주면, 그 뉴스를 반영하여 각 종목의 [가장 안전한 1·2·3차 진입 타점과 비중]을 정확한 수치로 찍어 줘.",
        "   - 현재 시장 심리(F&G, SPY RSI)를 바탕으로 지금 당장 '적극 매수', '관망', '비중 축소' 해야 할 종목들을 분류하고 구체적인 액션 플랜을 제시해 줘."
    ]
    st.code("\n".join(lines), language="text")
