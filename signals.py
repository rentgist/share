import pandas as pd
import numpy as np
from indicators import calc_rsi, get_rolling_rsi

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

    if not usdkrw_hist.empty and len(usdkrw_hist) >= 20:
        curr_krw = float(usdkrw_hist['Close'].iloc[-1])
        krw_5d_ago = float(usdkrw_hist['Close'].iloc[-6])
        krw_surge = (curr_krw - krw_5d_ago) / krw_5d_ago * 100
        krw_rsi = calc_rsi(usdkrw_hist['Close'], 14)
        krw_ma20 = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
        
        if krw_surge >= 1.5 or (curr_krw > krw_ma20 and krw_rsi and krw_rsi >= 65):
            alerts.append(("🔴", f"환율 단기 폭등/추세이탈 (+{krw_surge:.1f}%, RSI {krw_rsi:.1f}) — 외국인 엑소더스 징후."))
            danger_count += 2
        elif krw_surge >= 0.8 or (krw_rsi and krw_rsi >= 55):
            alerts.append(("🟠", f"환율 상승세 (+{krw_surge:.1f}%) — 외국인 수급 악화 조기 경보."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"환율 안정적 ({curr_krw:,.1f}원) — 외인 수급 이탈 우려 낮음."))

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
    
    is_rule_40_passed = rule_40 is not None and rule_40 >= 40

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
    if op_m is not None and float(op_m) >= 0.20: points += 1 
    if is_rule_40_passed: points += 2 
    
    if points >= 3: return "🔥 기관 최선호 대장주 (Rule of 40)" if is_rule_40_passed else "🔥 기관 최선호 대장주"
    if points >= 1: return "🌱 우량 고성장주 (Rule of 40)" if is_rule_40_passed else "🌱 우량 고성장주"
    return "-"
