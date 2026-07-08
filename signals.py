import pandas as pd
import numpy as np
from indicators import calc_rsi, calc_macd, get_rolling_rsi

# ═════════════════════════════════════════
# 공용 상수 (실시간 & 백테스트가 반드시 같은 값 사용)
# ═════════════════════════════════════════
GRIND_DOWN_RATIO   = 0.55   # 최근 20일 중 하락 마감일 비율 임계값
DIV_RSI_MARGIN     = 2.0    # RSI 다이버전스 인정 마진
KNIFE_1D_RET       = -2.5   # 떨어지는 칼날: 당일 급락 임계값 (%)
KNIFE_MA5_GAP      = -4.0   # 떨어지는 칼날: 5일선 이탈 임계값 (%)
KNIFE_PENALTY      = 20     # 칼날 감지 시 차감 점수

# ═════════════════════════════════════════
# 공용 헬퍼
# ═════════════════════════════════════════
def credit_spread_ratio(hyg_hist, ief_hist, min_len=50):
    """HYG/IEF 비율 시계열 (신용 스프레드 프록시). 단일 진실 원천."""
    if hyg_hist is None or ief_hist is None or hyg_hist.empty or ief_hist.empty:
        return None
    try:
        df = pd.concat([hyg_hist['Close'], ief_hist['Close']], axis=1).ffill().dropna()
        if len(df) < min_len:
            return None
        df.columns = ['HYG', 'IEF']
        return df['HYG'] / df['IEF']
    except Exception:
        return None


def analyze_market_structure(close):
    """
    🧠 시장 구조/국면(Regime) 분석기 — v23.0 신규 핵심 모듈.

    기존 탐지기의 맹점 보완:
    - 🐻 Grinding Bear: VIX가 안 뛰는 '미지근한 지속 하락' (하락일 비율 + 50일선 기울기로 감지)
    - 🌊 Whipsaw: 변동성은 큰데 방향이 없는 '오르면서 빠지는' 횡보 (실현변동성 vs 순변화 괴리)
    - 🏗️ Basing: 바닥 다지기 (저점 높이기 + 20일선 탈환)
    - RSI 상승 다이버전스: 가격은 신저점인데 RSI 저점은 높아짐 → 매도 에너지 소진
    """
    out = {
        "regime": "⚪ 판별 불가", "drawdown": 0.0,
        "is_panic": False, "is_grind": False, "is_whipsaw": False, "is_basing": False,
        "bullish_div": False, "higher_low": False, "ma20_reclaim": False,
        "down_ratio": None, "days_since_high": None, "ma50_slope": 0.0,
        "dead_cross": False, "realized_vol": None,
    }
    if close is None or len(close) < 60:
        return out

    price     = float(close.iloc[-1])
    high_252  = float(close.rolling(252, min_periods=1).max().iloc[-1])
    drawdown  = (price / high_252 - 1) * 100
    out["drawdown"] = drawdown

    rets   = close.pct_change()
    ret_1d = float(rets.iloc[-1]) * 100

    # 최근 20일 중 하락 마감일 비율 — '조용한 자금 이탈' 감지의 핵심
    down_ratio = float((rets.iloc[-20:] < 0).mean())
    out["down_ratio"] = round(down_ratio * 100, 0)

    # 52주 고점 이후 경과 거래일
    window = close.iloc[-252:]
    out["days_since_high"] = int(len(window) - 1 - int(np.argmax(window.values)))

    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else price
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    if len(close) >= 71:
        ma50_series = close.rolling(50).mean()
        out["ma50_slope"] = round((float(ma50_series.iloc[-1]) / float(ma50_series.iloc[-21]) - 1) * 100, 2)

    if ma200 is not None:
        out["dead_cross"] = (ma50 < ma200) and (price < ma200)

    # 실현 변동성 (20일, 연율화 %) — VIX가 못 잡는 실제 가격 요동 측정
    realized_vol = float(rets.iloc[-20:].std() * np.sqrt(252) * 100)
    out["realized_vol"] = round(realized_vol, 1)

    net_20d = (price / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else 0.0

    # ── RSI 다이버전스 & 저점 구조 (최근 60일을 전반/후반 30일로 나눠 비교) ──
    rsi_series = get_rolling_rsi(close, 14)
    recent_p = close.iloc[-60:]
    recent_r = rsi_series.iloc[-60:]
    p1, p2 = float(recent_p.iloc[:30].min()), float(recent_p.iloc[30:].min())
    r1, r2 = float(recent_r.iloc[:30].min()), float(recent_r.iloc[30:].min())

    if p2 < p1 and r2 > r1 + DIV_RSI_MARGIN:
        out["bullish_div"] = True     # 가격 신저점 + RSI 저점 상승 = 매도세 소진 신호
    if p2 > p1 * 1.005:
        out["higher_low"] = True      # 저점 높이기 (바닥 구조의 필요조건)
    out["ma20_reclaim"] = price > ma20

    # ── 국면(Regime) 판별 ──
    is_panic   = (ret_1d <= KNIFE_1D_RET) or (drawdown <= -15 and realized_vol >= 25)
    is_grind   = (drawdown <= -7) and (down_ratio >= GRIND_DOWN_RATIO) and (out["ma50_slope"] < 0) and not is_panic
    is_whipsaw = (realized_vol >= 18) and (abs(net_20d) < 2.5) and not is_panic and not is_grind
    is_basing  = (drawdown <= -10) and out["higher_low"] and out["ma20_reclaim"] and not is_panic

    out.update({"is_panic": is_panic, "is_grind": is_grind,
                "is_whipsaw": is_whipsaw, "is_basing": is_basing})

    if drawdown > -5 and not is_whipsaw:
        out["regime"] = f"📈 고점권/상승 추세 (DD {drawdown:.1f}%)"
    elif is_panic:
        out["regime"] = f"🚨 급락 패닉 (DD {drawdown:.1f}%, 실현변동성 {realized_vol:.0f}%)"
    elif is_basing:
        out["regime"] = f"🏗️ 바닥 다지기 진행 (DD {drawdown:.1f}%, 저점 높이는 중)"
    elif is_grind:
        out["regime"] = f"🐻 완만한 하락 — Grinding Bear (DD {drawdown:.1f}%, 하락일 {down_ratio*100:.0f}%)"
    elif is_whipsaw:
        out["regime"] = f"🌊 고변동 횡보 — Whipsaw (DD {drawdown:.1f}%, 변동성 {realized_vol:.0f}%)"
    elif drawdown > -12:
        out["regime"] = f"📉 단기 조정 (DD {drawdown:.1f}%)"
    elif drawdown > -20:
        out["regime"] = f"🟠 깊은 조정 (DD {drawdown:.1f}%)"
    else:
        out["regime"] = f"🔴 약세장 진행 (DD {drawdown:.1f}%)"

    return out


# ═════════════════════════════════════════
# 🇺🇸 레이어 1: 미국 전용 위험 탐지기 (v23.0: 스텔스 약세장 레이어 추가)
# ═════════════════════════════════════════
def calculate_us_risk_radar(vix_hist, vix3m_hist, hyg_hist, ief_hist, spy_hist):
    alerts = []
    danger_count = 0

    curr_vix   = float(vix_hist['Close'].iloc[-1])   if not vix_hist.empty  else None
    curr_vix3m = float(vix3m_hist['Close'].iloc[-1]) if not vix3m_hist.empty else None

    # ── ① VIX 기간구조 (백워데이션 = 단기 패닉) ──
    if curr_vix and curr_vix3m:
        if curr_vix > curr_vix3m * 1.05:
            alerts.append(("🔴", f"VIX 백워데이션 발생 ({curr_vix:.1f} > {curr_vix3m:.1f}). 단기 패닉 초입."))
            danger_count += 2
        elif curr_vix > curr_vix3m:
            alerts.append(("🟠", "VIX 백워데이션 진입 중. 예비 주시."))
            danger_count += 1
        else:
            alerts.append(("🟢", "VIX 콘탱고 정상. 시장 구조 안정."))

    # ── ② VIX 상대 급등 + 절대 레벨 ──
    vix_spike = 0
    if curr_vix:
        vix_ma20 = float(vix_hist['Close'].rolling(20).mean().iloc[-1]) if len(vix_hist) >= 20 else curr_vix
        vix_spike = (curr_vix - vix_ma20) / vix_ma20 * 100 if vix_ma20 > 0 else 0

        if vix_spike >= 40:
            alerts.append(("🚨", f"VIX 폭등 경보 (+{vix_spike:.1f}% vs 20일평균) — 기습적인 공포장 진입."))
            danger_count += 2
        elif vix_spike >= 20:
            alerts.append(("🔴", f"VIX 단기 급등 (+{vix_spike:.1f}% vs 20일평균) — 변동성 팽창 중."))
            danger_count += 1

        if curr_vix >= 30:
            alerts.append(("🔴", f"VIX {curr_vix:.1f} — 절대적 공포 확산 구간."))
            danger_count += 2
        elif curr_vix >= 22:
            alerts.append(("🟠", f"VIX {curr_vix:.1f} — 절대적 불안 상승 구간."))
            danger_count += 1
        else:
            if vix_spike < 20:
                alerts.append(("🟢", f"VIX {curr_vix:.1f} — 평온 구간."))

    # ── ③ 신용 스프레드 (공용 헬퍼 — 중복 로직 제거) ──
    credit_danger = False
    ratio = credit_spread_ratio(hyg_hist, ief_hist)
    if ratio is not None:
        ma20 = float(ratio.rolling(20).mean().iloc[-1])
        ma50 = float(ratio.rolling(50).mean().iloc[-1])
        curr = float(ratio.iloc[-1])
        if curr < ma50 * 0.97:
            alerts.append(("🔴", "신용 스프레드 위험 이탈. 기관 투매 감지."))
            danger_count += 2
            credit_danger = True
        elif curr < ma20:
            alerts.append(("🟠", "신용 스프레드 단기 이탈. 주시 필요."))
            danger_count += 1
            credit_danger = True
        else:
            alerts.append(("🟢", "신용 스프레드 안정 (정배열)."))
    else:
        alerts.append(("⚪", "신용 스프레드 산출 불가."))

    # ── ④ SPY 급락 & 킬 스위치 교차 검증 ──
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

    # ── ⑤ 🆕 스텔스 약세장 레이어 (급등이 아닌 '구조'로 위험 감지) ──
    if not spy_hist.empty:
        struct = analyze_market_structure(spy_hist['Close'])
        dd = struct["drawdown"]

        if struct["is_grind"]:
            alerts.append(("🔴", f"스텔스 약세장(Grinding Bear) 감지 — VIX 급등 없이 최근 20일 중 "
                                 f"{struct['down_ratio']:.0f}%가 하락 마감, 50일선 기울기 {struct['ma50_slope']:+.1f}%. "
                                 f"조용한 자금 이탈이 진행 중."))
            danger_count += 2

        if dd <= -8 and curr_vix is not None and curr_vix < 20:
            alerts.append(("🟠", f"VIX 안일(Complacency) 다이버전스 — 지수는 고점 대비 {dd:.1f}% 빠졌는데 "
                                 f"VIX {curr_vix:.1f}로 공포 미반영. 헷지 수요 부재 = 추가 하락 시 무방비."))
            danger_count += 1

        if struct["dead_cross"]:
            alerts.append(("🔴", "장기 추세 훼손 — 50일선 < 200일선 (데드크로스) & 주가 200일선 이탈."))
            danger_count += 1

        if struct["is_whipsaw"]:
            alerts.append(("🟡", f"고변동 횡보(Whipsaw) 국면 — 실현변동성 {struct['realized_vol']:.0f}%인데 "
                                 f"20일 순변화는 미미. 추세 매매 실패 확률 높음 → 현금 비중 유지 유리."))
            danger_count += 1

    # 감지 항목이 늘어난 만큼 등급 컷도 상향 (과잉 경보 방지)
    if danger_count >= 7:
        grade = "🚨 글로벌 마스터 킬 스위치 작동 — 시스템적 유동성 위기."
        color = "#ff0000"
    elif danger_count >= 5:
        grade = "🔴 글로벌 위기 경보 — 폭락 초입 가능성."
        color = "#ff4b4b"
    elif danger_count >= 3:
        grade = "🟠 글로벌 주의 단계 — 신규 진입 자제."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 글로벌 관찰 단계 — 경미한 이상 신호."
        color = "#fcca46"
    else:
        grade = "🟢 글로벌 마스터 이상 없음 — 매크로 환경 정상."
        color = "#21c354"

    return grade, color, alerts, danger_count


# ═════════════════════════════════════════
# 🇰🇷 레이어 1: 한국 전용 위험 탐지기
# (v23.0: 중복 정의 제거 — 정교 버전(MACD+VKOSPI 이격) 단일화 + 스텔스 감지 추가)
# ═════════════════════════════════════════
def calculate_kr_risk_radar(vkospi_hist, usdkrw_hist, kospi_hist):
    alerts = []
    danger_count = 0

    # ── ① 환율: 급등 + RSI + MACD 추세 교차 검증 (조기경보) ──
    if not usdkrw_hist.empty and len(usdkrw_hist) >= 20:
        curr_krw   = float(usdkrw_hist['Close'].iloc[-1])
        krw_5d_ago = float(usdkrw_hist['Close'].iloc[-6])
        krw_surge  = (curr_krw - krw_5d_ago) / krw_5d_ago * 100
        krw_rsi    = calc_rsi(usdkrw_hist['Close'], 14)
        krw_ma20   = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
        _, krw_macd_dir = calc_macd(usdkrw_hist['Close'])

        if krw_surge >= 1.5 or (curr_krw > krw_ma20 and krw_rsi and krw_rsi >= 65):
            alerts.append(("🔴", f"환율 단기 폭등/추세이탈 (+{krw_surge:.1f}%, RSI {krw_rsi:.1f}) — 외국인 엑소더스 징후."))
            danger_count += 2
        elif krw_surge >= 0.8 or (krw_rsi and krw_rsi >= 55) or (krw_macd_dir == "🟢상승" and curr_krw > krw_ma20):
            alerts.append(("🟠", f"환율 상승세 (+{krw_surge:.1f}%) 및 MACD 상승 — 외국인 수급 악화 조기 경보."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"환율 안정적 ({curr_krw:,.1f}원) — 외인 수급 이탈 우려 낮음."))

    # ── ② VKOSPI: 20일 이격(spike) + 절대 레벨 + 5일 급등 ──
    if not vkospi_hist.empty and len(vkospi_hist) >= 20:
        curr_vk  = float(vkospi_hist['Close'].iloc[-1])
        vk_ma20  = float(vkospi_hist['Close'].rolling(20).mean().iloc[-1])
        vk_spike = (curr_vk - vk_ma20) / vk_ma20 * 100 if vk_ma20 > 0 else 0
        vk_5d_ago = float(vkospi_hist['Close'].iloc[-6])
        vk_surge  = (curr_vk - vk_5d_ago) / vk_5d_ago * 100 if vk_5d_ago > 0 else 0

        if vk_spike >= 30 or curr_vk >= 25 or vk_surge >= 25:
            alerts.append(("🔴", f"VKOSPI 급등 ({curr_vk:.1f}, +{vk_spike:.1f}% vs 20일평균) — 기관/외인 하락 헷지 팽창."))
            danger_count += 2
        elif vk_spike >= 15 or curr_vk >= 18 or vk_surge >= 15:
            alerts.append(("🟠", f"VKOSPI 불안 ({curr_vk:.1f}) — 파생 변동성 확대 조짐."))
            danger_count += 1
        else:
            alerts.append(("🟢", f"VKOSPI 평온 ({curr_vk:.1f}) — 하방 압력 낮음."))

    # ── ③ KOSPI 5일 낙폭 ──
    if not kospi_hist.empty and len(kospi_hist) >= 6:
        k_5d_ret = (float(kospi_hist['Close'].iloc[-1]) / float(kospi_hist['Close'].iloc[-6]) - 1) * 100
        if k_5d_ret <= -4:
            alerts.append(("🔴", f"KOSPI 5일 급락 ({k_5d_ret:.1f}%) — 프로그램 및 동반 투매 감지."))
            danger_count += 1
        elif k_5d_ret <= -2:
            alerts.append(("🟠", f"KOSPI 5일 하락 ({k_5d_ret:.1f}%) — 단기 매도 우위."))
        else:
            alerts.append(("🟢", f"KOSPI 단기 추세 ({k_5d_ret:+.1f}%) — 안정적."))

    # ── ④ 🆕 KOSPI 스텔스 약세 (미지근한 지속 하락 감지) ──
    if not kospi_hist.empty:
        struct = analyze_market_structure(kospi_hist['Close'])
        if struct["is_grind"]:
            alerts.append(("🔴", f"KOSPI 스텔스 약세 감지 — 최근 20일 중 {struct['down_ratio']:.0f}%가 하락 마감, "
                                 f"50일선 우하향 ({struct['ma50_slope']:+.1f}%). 완만한 외인 이탈형 하락."))
            danger_count += 2
        elif struct["is_whipsaw"]:
            alerts.append(("🟡", f"KOSPI 고변동 횡보 — 변동성 {struct['realized_vol']:.0f}% 대비 방향성 부재. 관망 유리."))
            danger_count += 1

    if danger_count >= 5:
        grade = "🔴 한국 위기 경보 — 외인 이탈 및 폭락 초입 우려."
        color = "#ff4b4b"
    elif danger_count >= 3:
        grade = "🟠 한국 주의 단계 — 수급/환율 불안정."
        color = "#ff9900"
    elif danger_count >= 1:
        grade = "🟡 한국 관찰 단계 — 경미한 수급 꼬임 감지."
        color = "#fcca46"
    else:
        grade = "🟢 한국 이상 없음 — 국내 수급 환경 안정적."
        color = "#21c354"

    return grade, color, alerts, danger_count


# ═════════════════════════════════════════
# 진바닥 탐지기 — 공용 스코어러
# (실시간 & 백테스트가 '동일 함수'를 사용 → 점수 스케일 완전 통일)
# ═════════════════════════════════════════
def _score_bottom(drawdown, rsi, vix, cnn=None, details=None):
    """
    미국 바닥 코어 점수. CNN 유무와 무관하게 항상 '만점 대비 %'로 정규화.
    → 실시간(CNN 포함, 100점 만점)과 백테스트(CNN 제외, 80점 만점)가 같은 자로 비교 가능.
    """
    def _log(msg):
        if details is not None:
            details.append(msg)

    s, maxs = 0, 80  # Drawdown 35 + RSI 20 + VIX 25

    if drawdown <= -25: s += 35; _log(f"🟢 대세 하락장 낙폭 ({drawdown:.1f}%) [+35/35]")
    elif drawdown <= -15: s += 22; _log(f"🟢 깊은 조정 ({drawdown:.1f}%) [+22/35]")
    elif drawdown <= -8: s += 10; _log(f"🟡 단기 조정 ({drawdown:.1f}%) [+10/35]")
    else: _log(f"⚪ 고점 근처 ({drawdown:.1f}%) [+0/35]")

    if rsi is not None:
        if rsi <= 30: s += 20; _log(f"🟢 RSI 극단 과매도 ({rsi:.1f}) [+20/20]")
        elif rsi <= 38: s += 12; _log(f"🟢 RSI 과매도 ({rsi:.1f}) [+12/20]")
        elif rsi <= 45: s += 5;  _log(f"🟡 RSI 과매도 진입 ({rsi:.1f}) [+5/20]")
        else: _log(f"⚪ RSI 정상 ({rsi:.1f}) [+0/20]")

    if vix is not None:
        if vix >= 40: s += 25; _log(f"🟢 VIX 극단 패닉 ({vix:.1f}) [+25/25]")
        elif vix >= 32: s += 20; _log(f"🟢 VIX 패닉 투매 ({vix:.1f}) [+20/25]")
        elif vix >= 26: s += 12; _log(f"🟡 VIX 공포 확산 ({vix:.1f}) [+12/25]")
        elif vix >= 22: s += 5;  _log(f"🟡 VIX 상승 주의 ({vix:.1f}) [+5/25]")
        else: _log(f"⚪ VIX 평온 ({vix:.1f}) [+0/25]")

    if cnn is not None:
        maxs += 20
        if cnn <= 15: s += 20; _log(f"🟢 F&G 역사적 패닉 ({cnn}) [+20/20]")
        elif cnn <= 25: s += 15; _log(f"🟢 F&G 극단 공포 ({cnn}) [+15/20]")
        elif cnn <= 35: s += 8;  _log(f"🟡 F&G 공포 구간 ({cnn}) [+8/20]")
        elif cnn <= 45: s += 3;  _log(f"⚪ F&G 약한 공포 ({cnn}) [+3/20]")
        else: _log(f"⚪ F&G 중립~탐욕 ({cnn}) [+0/20]")

    return min(int(round(s / maxs * 100)), 100)


def _apply_structure_bonus(score, struct, details):
    """🆕 구조 보너스 — '충분히 빠졌다'를 넘어 '빠짐이 끝나간다'를 점수화."""
    dd = struct["drawdown"]
    if struct["is_grind"] and dd <= -10:
        score += 8
        details.append("🟢 [구조] Grinding Bear 성숙 보정 — VIX가 못 잡는 완만한 하락의 누적 낙폭 반영 [+8점]")
    if struct["bullish_div"]:
        score += 10
        details.append("🟢 [구조] RSI 상승 다이버전스 — 가격 신저점에도 매도 에너지 소진 중 [+10점]")
    if struct["higher_low"] and dd <= -8:
        score += 5
        details.append("🟢 [구조] 저점 높이기(Higher Low) 확인 — 바닥 다지기 진행 [+5점]")
    if struct["ma20_reclaim"] and dd <= -10:
        score += 5
        details.append("🟢 [구조] 20일선 탈환 — 단기 수급 회복 [+5점]")
    return min(int(score), 100)


def _apply_falling_knife(score, close, details):
    """떨어지는 칼날 안전장치 (실시간·백테스트 공용 임계값)."""
    is_knife = False
    if len(close) >= 5:
        ret_1d  = (float(close.iloc[-1]) / float(close.iloc[-2]) - 1) * 100
        ma5     = float(close.rolling(5).mean().iloc[-1])
        gap_ma5 = (float(close.iloc[-1]) - ma5) / ma5 * 100
        if ret_1d <= KNIFE_1D_RET or gap_ma5 <= KNIFE_MA5_GAP:
            is_knife = True
            if score >= 35:
                details.append(f"🚨 [Safety Catch] 당일 급락({ret_1d:.1f}%) 또는 5일선 심각한 이탈({gap_ma5:.1f}%). "
                               f"브레이크(양봉) 확인 후 진입 권장. (-{KNIFE_PENALTY}점 차감)")
                score = max(score - KNIFE_PENALTY, 0)
    return score, is_knife


def _verdict_from_score(score, drawdown, is_knife):
    if drawdown > -5: verdict = "📈 고점권 — 바닥 탐지 불가"
    elif score >= 70: verdict = "🔥 강력 매수 신호 (역사적 바닥 근접)"
    elif score >= 50: verdict = "🟢 분할 매수 구간 (역발상 타점)"
    elif score >= 35: verdict = "🟡 조정 진행 중 (추가 하락 여지)"
    else: verdict = "⚪ 바닥 조건 미충족"
    if is_knife and score >= 35:
        verdict = "⚠️ 떨어지는 칼날 (관망 권장)"
    return verdict


def calculate_us_bottom_finder(spy_hist, vix_hist, cnn_score):
    if spy_hist is None or spy_hist.empty:
        return 0, "데이터 부족", [], "알 수 없음"

    spy_close = spy_hist['Close']
    struct = analyze_market_structure(spy_close)
    drawdown = struct["drawdown"]
    market_phase = struct["regime"]

    spy_rsi  = calc_rsi(spy_close, 14)
    curr_vix = float(vix_hist['Close'].iloc[-1]) if not vix_hist.empty else None

    details = []
    score = _score_bottom(drawdown, spy_rsi, curr_vix, cnn_score, details=details)
    score = _apply_structure_bonus(score, struct, details)
    score, is_knife = _apply_falling_knife(score, spy_close, details)
    verdict = _verdict_from_score(score, drawdown, is_knife)

    return score, verdict, details, market_phase


def calculate_kr_bottom_finder(kospi_hist, vkospi_hist, usdkrw_hist):
    if kospi_hist is None or kospi_hist.empty:
        return 0, "데이터 부족", [], "알 수 없음"

    kospi_close = kospi_hist['Close']
    struct = analyze_market_structure(kospi_close)
    drawdown = struct["drawdown"]
    market_phase = struct["regime"]

    score, max_score, details = 0, 0, []
    kill_switch = False

    # ① Drawdown (만점 35)
    max_score += 35
    dd = -drawdown
    if dd >= 20: 
        score += 35; details.append(f"🟢 KOSPI 대세 하락장 ({drawdown:.1f}%) [+35/35]")
    elif dd >= 12: 
        pts = 22 + (dd - 12) * (35 - 22) / (20 - 12)
        score += pts; details.append(f"🟢 KOSPI 깊은 조정 ({drawdown:.1f}%) [+{pts:.1f}/35]")
    elif dd >= 7: 
        pts = 10 + (dd - 7) * (22 - 10) / (12 - 7)
        score += pts; details.append(f"🟡 KOSPI 단기 조정 ({drawdown:.1f}%) [+{pts:.1f}/35]")
    elif dd > 0:
        pts = dd * 10 / 7
        score += pts; details.append(f"⚪ 얕은 조정 ({drawdown:.1f}%) [+{pts:.1f}/35]")
    else: 
        details.append(f"⚪ 고점 근처 ({drawdown:.1f}%) [+0/35]")

    # ② RSI (만점 20)
    kr_rsi = calc_rsi(kospi_close, 14)
    if kr_rsi is not None:
        max_score += 20
        if kr_rsi <= 30: 
            score += 20; details.append(f"🟢 KOSPI 극단 과매도 ({kr_rsi:.1f}) [+20/20]")
        elif kr_rsi <= 40: 
            pts = 12 + (40 - kr_rsi) * (20 - 12) / (40 - 30)
            score += pts; details.append(f"🟢 KOSPI 과매도 ({kr_rsi:.1f}) [+{pts:.1f}/20]")
        elif kr_rsi <= 45: 
            pts = 5 + (45 - kr_rsi) * (12 - 5) / (45 - 40)
            score += pts; details.append(f"🟡 KOSPI 과매도 진입 ({kr_rsi:.1f}) [+{pts:.1f}/20]")
        elif kr_rsi <= 60:
            pts = (60 - kr_rsi) * 5 / (60 - 45)
            score += pts; details.append(f"⚪ KOSPI RSI 정상 ({kr_rsi:.1f}) [+{pts:.1f}/20]")
        else: 
            details.append(f"⚪ KOSPI RSI 높음 ({kr_rsi:.1f}) [+0/20]")

    # ③ VKOSPI (만점 25) — 누락 시 만점에서 자동 제외 (하드코딩 환산 제거)
    curr_vkospi = float(vkospi_hist['Close'].iloc[-1]) if not vkospi_hist.empty else None
    if curr_vkospi and not np.isnan(curr_vkospi):
        max_score += 25
        if curr_vkospi >= 25: 
            score += 25; details.append(f"🟢 VKOSPI 패닉 투매 ({curr_vkospi:.1f}) [+25/25]")
        elif curr_vkospi >= 20: 
            pts = 15 + (curr_vkospi - 20) * (25 - 15) / (25 - 20)
            score += pts; details.append(f"🟢 VKOSPI 공포 확산 ({curr_vkospi:.1f}) [+{pts:.1f}/25]")
        elif curr_vkospi >= 16: 
            pts = 5 + (curr_vkospi - 16) * (15 - 5) / (20 - 16)
            score += pts; details.append(f"🟡 VKOSPI 상승 주의 ({curr_vkospi:.1f}) [+{pts:.1f}/25]")
        elif curr_vkospi >= 12:
            pts = (curr_vkospi - 12) * 5 / (16 - 12)
            score += pts; details.append(f"⚪ VKOSPI 평온 ({curr_vkospi:.1f}) [+{pts:.1f}/25]")
        else: 
            details.append(f"⚪ VKOSPI 매우 평온 ({curr_vkospi:.1f}) [+0/25]")
    else:
        details.append("⚪ VKOSPI 데이터 누락 — 만점에서 제외해 자동 보정 [+0점]")

    # ④ 환율 (만점 20) + 킬 스위치
    if not usdkrw_hist.empty:
        krw_rsi = calc_rsi(usdkrw_hist['Close'], 14)
        if krw_rsi is not None:
            max_score += 20
            if krw_rsi <= 55: 
                score += 20; details.append(f"🟢 환율 안정 및 원화 강세 (RSI {krw_rsi:.1f}) [+20/20]")
            elif krw_rsi <= 65: 
                pts = 10 + (65 - krw_rsi) * (20 - 10) / (65 - 55)
                score += pts; details.append(f"🟡 환율 약세 구간 (RSI {krw_rsi:.1f}) [+{pts:.1f}/20]")
            elif krw_rsi <= 75:
                pts = (75 - krw_rsi) * 10 / (75 - 65)
                score += pts; details.append(f"🚨 환율 단기 폭등 위험 (RSI {krw_rsi:.1f}) [+{pts:.1f}/20]")
            else:
                details.append(f"🚨 환율 극단적 폭등 (RSI {krw_rsi:.1f}) [+0/20]")
                if krw_rsi > 70 and drawdown > -10:
                    kill_switch = True
                    details.append("💣 [Kill Switch] 코스피 낙폭 적은데 환율 초급등. 폭락 초입 가능성으로 최종 점수 30점 제한.")

    # 만점 정규화 → 구조 보너스 → 킬 스위치 → 떨어지는 칼날
    score = min(int(round(score / max_score * 100)), 100) if max_score > 0 else 0
    score = _apply_structure_bonus(score, struct, details)
    if kill_switch:
        score = min(score, 30)
    score, is_knife = _apply_falling_knife(score, kospi_close, details)
    verdict = _verdict_from_score(score, drawdown, is_knife)

    return score, verdict, details, market_phase


# ═════════════════════════════════════════
# 레이어 3: 회복 확인
# ═════════════════════════════════════════
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
        except Exception:
            signals.append(("⚪", "Breadth 데이터 산출 불가."))

    ratio = credit_spread_ratio(hyg_hist, ief_hist)
    if ratio is not None:
        curr = float(ratio.iloc[-1])
        ma20 = float(ratio.rolling(20).mean().iloc[-1])
        ma50 = float(ratio.rolling(50).mean().iloc[-1])
        if curr > ma20 > ma50:
            signals.append(("🟢", "신용시장 회복 확인 — HYG/IEF 정배열. 기관이 위험자산으로 복귀 중."))
            recovery_score += 50
        elif curr > ma50:
            signals.append(("🟡", "신용시장 부분 회복 — MA50 위. 아직 완전 정배열은 아님."))
            recovery_score += 25
        else:
            signals.append(("🔴", "신용시장 미회복 — 아직 기관 자금 복귀 확인 안 됨."))
    else:
        signals.append(("⚪", "Credit 데이터 산출 불가."))

    if recovery_score >= 100: verdict = "🟢 반등 신뢰도 높음 — Breadth + Credit 동시 회복"
    elif recovery_score >= 50: verdict = "🟡 반등 신뢰도 보통 — 일부만 회복"
    else: verdict = "🔴 반등 신뢰도 낮음 — 아직 회복 확인 안 됨"

    return verdict, signals, recovery_score


def calculate_kr_recovery_confirmation(kospi_hist, usdkrw_hist):
    signals = []
    recovery_score = 0

    if not kospi_hist.empty and len(kospi_hist) >= 50:
        try:
            close = kospi_hist['Close']
            curr_k = float(close.iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            
            if curr_k > ma20 and curr_k > ma50:
                signals.append(("🟢", "한국장 추세 완전 회복 — KOSPI가 20일선 및 50일선을 동시 상회 중입니다."))
                recovery_score += 50
            elif curr_k > ma20:
                signals.append(("🟡", "한국장 단기 회복 — KOSPI가 20일선을 회복했으나 아직 50일선 아래에 있습니다."))
                recovery_score += 25
            else:
                signals.append(("🔴", "한국장 추세 미회복 — KOSPI가 주요 이동평균선(20일, 50일)을 하회하고 있습니다."))
        except Exception:
            signals.append(("⚪", "KOSPI 추세 데이터 산출 불가."))

    if not usdkrw_hist.empty and len(usdkrw_hist) >= 50:
        try:
            curr_fx = float(usdkrw_hist['Close'].iloc[-1])
            ma20_fx = float(usdkrw_hist['Close'].rolling(20).mean().iloc[-1])
            ma50_fx = float(usdkrw_hist['Close'].rolling(50).mean().iloc[-1])
            
            if curr_fx < ma20_fx and curr_fx < ma50_fx:
                signals.append(("🟢", "환율(외인 수급) 안정 — 환율이 20일/50일선 아래에서 하향 안정화되어 외인 자금 유입 환경이 조성되었습니다."))
                recovery_score += 50
            elif curr_fx < ma20_fx:
                signals.append(("🟡", "환율 단기 진정 — 환율이 20일선 아래로 내려와 급등세가 진정되었습니다."))
                recovery_score += 25
            else:
                signals.append(("🔴", "환율 불안정 — 환율이 이동평균선 위에 있어 외인 이탈 압력이 여전합니다."))
        except Exception:
            signals.append(("⚪", "환율 데이터 산출 불가."))

    if recovery_score >= 100: verdict = "🟢 반등 신뢰도 높음 — 추세 회복 + 환율 안정 동시 충족"
    elif recovery_score >= 50: verdict = "🟡 반등 신뢰도 보통 — 조건 중 일부만 회복"
    else: verdict = "🔴 반등 신뢰도 낮음 — 아직 회복 신호 부족"

    return verdict, signals, recovery_score


# ═════════════════════════════════════════
# 🎯 레이어 4: 종합 전략 제언 엔진
# 위험 탐지기(danger) × 바닥 탐지기(score) × 반등 신뢰도(recovery)를
# 교차 결합해 '지금 매수해도 되는가'를 실전 액션으로 번역한다.
# 포지션 비율은 11원칙(위기 줍줍·분할 매수) 철학 기준.
# ═════════════════════════════════════════
def get_strategic_advice(danger_count, bottom_score, bottom_verdict, regime="", recovery_score=None):
    """
    반환: (headline, color, actions[])
    danger_count: 위험 탐지기 원점수 (US 기준 7+ = 킬스위치, 5+ = 위기, 3+ = 주의)
    bottom_score: 바닥 탐지기 정규화 점수 (0~100)
    recovery_score: 반등 신뢰도 (0/25/50/75/100, 한국장은 None)
    """
    actions = []
    is_knife = "칼날" in bottom_verdict
    is_top   = "고점권" in bottom_verdict

    # ── ① 최우선 순위: 떨어지는 칼날 (점수 무관 매수 보류) ──
    if is_knife:
        headline = "⚠️ 매수 보류 — 떨어지는 칼날 구간"
        color = "#ff9900"
        actions = [
            "지금은 '낙폭'이 아니라 '속도'가 문제입니다. 급락 진행 중 진입은 평균단가만 훼손합니다.",
            "매수 재개 조건: ① 일봉 양봉 마감 또는 ② 5일선 회복 — 둘 중 하나 확인 후 다음 거래일 진입.",
            "대기 중 할 일: 매수 후보 리스트와 분할 예산(3회분)을 미리 확정해 두세요. 바닥에서는 생각할 시간이 없습니다.",
        ]

    # ── ② 고점권 (바닥 탐지 무의미 구간) ──
    elif is_top:
        if danger_count >= 5:
            headline = "🚨 고점권 + 위험 경보 다발 — 하락 '초입' 최악 조합"
            color = "#ff4b4b"
            actions = [
                "가장 위험한 조합입니다: 경보는 켜졌는데 낙폭은 아직 얕음 = 빠질 공간이 그대로 남아있는 하락 초입.",
                "신규 매수 전면 중단. 반등이 나오면 '탈출 기회'로 쓰고 비중을 줄이세요 (7원칙 리밸런싱).",
                "지킬 종목(펀더멘탈 우수)과 정리할 종목을 지금 분류해 두세요. 폭락 중에는 전부 같이 빠집니다.",
                "현금 목표: 30% 이상. 이 현금이 다음 '위기 줍줍(6원칙)'의 실탄입니다.",
            ]
        elif danger_count >= 3:
            headline = "🟠 고점권 + 이상 신호 — 신규 진입 자제, 현금 확보 시작"
            color = "#ff9900"
            actions = [
                "지수는 고점권인데 위험 탐지기에 경고가 쌓이는 중 — 추격 매수의 기대값이 가장 낮은 구간입니다.",
                "수익 중인 종목 일부 익절로 현금 20~30% 확보. 신규는 '20일선 눌림목 확인' 조건부로만.",
                "위험 점수가 더 올라가면(🔴 등급) 방어 모드 전환을 준비하세요.",
            ]
        else:
            headline = "🟢 정상 상승 장세 — 지수 레벨 타점 없음, 개별 종목 장세"
            color = "#21c354"
            actions = [
                "바닥 탐지기는 조정장 전용 도구입니다. 지금은 지수가 아니라 '종목'으로 승부하는 구간.",
                "개별 종목의 20일선 눌림목 + 실적 모멘텀(텐배거 레이더) 위주로 접근하세요.",
                "평시에도 위기 대비 현금 10~20%는 항상 유지 (6원칙의 전제 조건).",
            ]

    # ── ③ 바닥 점수 70+ : 역사적 바닥권 ──
    elif bottom_score >= 70:
        if danger_count >= 5:
            headline = "🔥 역사적 바닥권 + 시스템 위기 진행 중 — '1차 선발대' 전략 (30%)"
            color = "#fcca46"
            actions = [
                "역사적 과매도 구간이지만 신용경색/킬스위치가 살아있습니다 → 바닥 '근접'이지 '확정'이 아님.",
                "1차 선발대로 총 예산의 30%만 진입합니다. (하워드 막스 방식: 깊은 가치가 보이면 과감히 담되, 만약을 대비한 현금 확보).",
                "추가 증액 트리거: 신용 스프레드 🟢 복귀 또는 VIX 백워데이션 해소 — 이게 기관 자금 복귀 신호입니다.",
                "지수 ETF 절반 + 펀더멘탈 우량주 절반으로 하방을 방어하세요.",
            ]
        else:
            color = "#21c354"
            if recovery_score is not None and recovery_score < 50:
                headline = "🔥 강력 매수 구간 — 1차 선발대 투입 타이밍 (30~50%)"
                actions = [
                    "역사적 바닥 점수 + 위험 탐지기 진정 = 11원칙 '위기 줍줍'의 본령입니다.",
                    "단, 뚜렷한 반등 신호가 아직 없으므로, 1차 진입으로 총 예산의 30~50%를 투입하세요.",
                    "떨어지는 칼날 리스크를 관리하며 평균 단가를 낮출 수 있는 최적의 비중입니다.",
                    "아래 백테스트 탭에서 이 점수대의 과거 승률을 직접 확인하고 들어가세요 — 확신이 사이즈를 만듭니다.",
                ]
            else:
                headline = "🔥 강력 매수 구간 — 본격 비중 확대 타이밍 (50~70% 이상)"
                actions = [
                    "역사적 바닥 + 위험 진정 + 반등 신호 포착 = 최고의 투자 타이밍입니다.",
                    "총 예산의 50~70% 이상까지 과감히 집행하세요 (이미 1차 선발대가 있다면 2·3차 증액 구간).",
                    "워런 버핏의 '비가 올 때는 양동이를 내놓아라'라는 원칙이 적용되는 시기입니다.",
                    "종목 선택: 지수 ETF 절반 + 낙폭과대 우량주(펀더멘탈 점수 4+) 절반 배분이 회복탄력 극대화.",
                ]

    # ── ④ 50~69 : 분할 매수 접근 구간 ──
    elif bottom_score >= 50:
        if danger_count >= 5:
            headline = "🟡 매수권 점수 + 위험 경보 우세 — 관망 또는 최소 단위만 (10%)"
            color = "#fcca46"
            actions = [
                "점수는 분할 매수권이지만 위기 경보가 우세 → 추가 하락 확률이 여전히 높습니다.",
                "진입한다면 총 예산의 10% 이내 최소 단위만. '더 빠지면 더 산다'가 성립하는 금액만.",
                "현금 70% 이상 유지 — 지금 아끼는 현금이 점수 70+에서의 진짜 기회를 삽니다.",
            ]
        else:
            headline = "🟢 1차 분할 매수 타점 — 초기 선발대 진입 (20~30%)"
            color = "#21c354"
            actions = [
                "가치가 돋보이기 시작하는 1차 진입 구간입니다. 단, 바닥 '확인'이 아니라 '접근' 단계 — 몰빵 금지.",
                "총 예산의 20~30% 규모로 초기 선발대를 투입하세요.",
                "2차 증액 트리거: ① 점수 70+ 도달 또는 ② 저점 높이기 + 20일선 탈환 동시 확인.",
                "시간 분산: 다음 분할까지 최소 1~2주 간격. 같은 주에 전 예산 소진이 최다 실수 유형입니다.",
            ]

    # ── ⑤ 35~49 : 애매 구간 ──
    elif bottom_score >= 35:
        headline = "🟡 관망 — 조정 진행 중, 타점 대기"
        color = "#fcca46"
        actions = [
            "이 애매한 구간이 계좌를 가장 많이 상하게 합니다. '싸 보인다'는 근거가 아닙니다.",
            "매수 예약 조건을 미리 설정: 점수 50+ 도달 또는 RSI 30 이하 진입 시 1차 집행.",
            "위험 탐지기가 🔴 이상이면 조정이 하락장으로 발전할 수 있음 — 현금 추가 확보.",
        ]

    # ── ⑥ 35 미만 : 바닥 조건 미충족 ──
    else:
        if danger_count >= 5:
            headline = "🚨 위험 경보 + 낙폭 미달 — 하락 초입 방어 모드"
            color = "#ff4b4b"
            actions = [
                "경보는 켜졌는데 아직 충분히 안 빠졌습니다 = 빠질 공간이 남은 하락 초입 신호.",
                "신규 매수 전면 중단, 반등 시 비중 축소로 대응 (7원칙 리밸런싱).",
                "다음 매수는 바닥 탐지기 50+ 부터. 그 전까지 모든 하락은 '구경'입니다.",
            ]
        elif danger_count >= 3:
            headline = "🟠 경계 태세 — 이상 신호 감지, 현금 비중 확대"
            color = "#ff9900"
            actions = [
                "위험 신호가 쌓이는 초기 단계 — 아직 패닉은 아니지만 공격할 때도 아닙니다.",
                "신규 매수는 보류하고, 보유 종목 중 펀더멘탈 약한 것부터 정리 우선순위를 정하세요.",
                "현금 20~30% 확보 시작. 경보 해제(🟢/🟡 복귀) 시 정상 매매 재개.",
            ]
        else:
            headline = "🟢 평시 국면 — 지수 타점 없음, 정상 매매 유지"
            color = "#21c354"
            actions = [
                "위험도 바닥 신호도 없는 평시입니다. 지수 타이밍 베팅은 무의미한 구간.",
                "개별 종목의 눌림목/실적 기반 매매에 집중하고, 위기 대비 현금 10~20%만 유지하세요.",
            ]

    # ── 국면(Regime)별 특이사항 추가 ──
    if "Grinding" in regime:
        actions.append("🐻 국면 특이사항: 완만한 하락(Grinding Bear)은 V자 반등이 드뭅니다. 분할 간격을 평소의 2배로 넓히고(시간 분산 강화), 총알을 아끼세요.")
    if "Whipsaw" in regime:
        actions.append("🌊 국면 특이사항: 고변동 횡보에서는 추격 매매 승률이 급락합니다. 매수는 미리 정한 '가격 레벨'에 지정가로만 — 장중 추격 금지.")
    if "다지기" in regime:
        actions.append("🏗️ 국면 특이사항: 저점 높이기가 유지되는 한 눌림목마다 분할 매수 유효. 단, 직전 저점 이탈 시 시나리오 폐기 후 재관망.")

    # ── 반등 신뢰도(Breadth/Credit)로 증액 여부 미세 조정 ──
    if recovery_score is not None and bottom_score >= 50 and not is_knife:
        if recovery_score >= 100:
            actions.append("✅ 반등 신뢰도 교차검증: 주요 지표 동시 회복 — 2·3차 증액의 객관적 근거 충족.")
        elif recovery_score >= 50:
            actions.append("🟡 반등 신뢰도 교차검증: 절반만 회복 — 1차 포지션 유지, 증액은 완전 회복 확인 후.")
        else:
            actions.append("🔴 반등 신뢰도 교차검증: 미회복 — 지금 반등은 기술적 반등(데드캣)일 수 있음. 1차 이상 넣지 마세요.")

    # ── 대가의 퀀트 원칙 (장초 추격 매수 금지 & 종가 확인) ──
    actions.append("🕒 [대가의 타점 원칙] 당일 점수가 아무리 좋아도 다음날 장초 갭상승이나 추격 매수는 절대 금물입니다. 진입 타점은 '오후 2시 30분 이후 종가 무렵'에 확인하고 진입하세요.")
    if is_knife or danger_count >= 5:
        actions.append("🛡️ [생존 원칙] 현재처럼 불안정한 구간에서는 '장중 반등'은 속임수일 확률이 높습니다. 반드시 종가 기준 지지 여부를 확인하고 다음 날 판단하세요.")

    return headline, color, actions


# ═════════════════════════════════════════
# 백테스트 — 실시간과 '동일한 스코어러 + 동일한 구조 보너스 + 동일한 칼날 패널티' 사용
# ═════════════════════════════════════════
def run_historical_backtest(spy_hist, vix_hist, vix3m_hist):
    if any(df.empty for df in [spy_hist, vix_hist, vix3m_hist]):
        return None

    df = pd.concat([
        spy_hist['Close'], vix_hist['Close'], vix3m_hist['Close'],
    ], axis=1).ffill().dropna()

    if df.empty or len(df) < 400:
        return None

    df.columns = ['SPY', 'VIX', 'VIX3M']

    # 고점 기준선: min_periods=252 → 데이터 초기 1년은 '가짜 저낙폭' 왜곡이 생기므로 제외
    df['SPY_High_252'] = df['SPY'].rolling(252, min_periods=252).max()
    df['Drawdown']     = (df['SPY'] / df['SPY_High_252'] - 1) * 100
    df['RSI']          = get_rolling_rsi(df['SPY'], 14)
    df = df.dropna(subset=['Drawdown', 'RSI'])
    if df.empty:
        return None

    df['Fwd_3M_Ret'] = (df['SPY'].shift(-63)  / df['SPY'] - 1) * 100
    df['Fwd_6M_Ret'] = (df['SPY'].shift(-126) / df['SPY'] - 1) * 100

    # ① 코어 점수 — 실시간과 같은 _score_bottom (CNN은 과거 데이터 없어 제외, 만점 정규화로 스케일 동일)
    df['Score'] = [
        _score_bottom(dd, rsi, vix)
        for dd, rsi, vix in zip(df['Drawdown'], df['RSI'], df['VIX'])
    ]

    # ② 구조 보너스 — 실시간의 _apply_structure_bonus를 벡터화한 동일 조건
    close = df['SPY']
    rets  = close.pct_change()
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma50_slope = (ma50 / ma50.shift(21) - 1) * 100
    down_ratio = (rets < 0).rolling(20).mean()
    p1 = close.shift(30).rolling(30).min()
    p2 = close.rolling(30).min()
    r1 = df['RSI'].shift(30).rolling(30).min()
    r2 = df['RSI'].rolling(30).min()

    bonus = np.zeros(len(df))
    bonus += np.where((df['Drawdown'] <= -10) & (down_ratio >= GRIND_DOWN_RATIO) & (ma50_slope < 0), 8, 0)
    bonus += np.where((p2 < p1) & (r2 > r1 + DIV_RSI_MARGIN), 10, 0)
    bonus += np.where((p2 > p1 * 1.005) & (df['Drawdown'] <= -8), 5, 0)
    bonus += np.where((close > ma20) & (df['Drawdown'] <= -10), 5, 0)
    df['Score'] = np.minimum(df['Score'] + bonus, 100).astype(int)

    # ③ 떨어지는 칼날 패널티 — 실시간과 동일 임계값
    ret_1d  = rets * 100
    ma5     = close.rolling(5).mean()
    gap_ma5 = (close / ma5 - 1) * 100
    knife   = (ret_1d <= KNIFE_1D_RET) | (gap_ma5 <= KNIFE_MA5_GAP)
    df['Score'] = np.where(knife & (df['Score'] >= 35), df['Score'] - KNIFE_PENALTY, df['Score'])
    df['Score'] = df['Score'].clip(0, 100).astype(int)

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
        except Exception:
            event_scores[name] = None

    return {
        "70점 이상 (강력 매수)":    _stat(res_70),
        "50~69점 (분할 매수)":      _stat(res_50),
        "주요 이벤트 점수":          event_scores,
        "score_series":             df[['Score', 'Drawdown']],
    }


def run_kr_historical_backtest(kospi_hist, vkospi_hist, usdkrw_hist):
    if any(df is None for df in [kospi_hist, vkospi_hist, usdkrw_hist]) or any(df.empty for df in [kospi_hist, vkospi_hist, usdkrw_hist]):
        return None

    df = pd.concat([
        kospi_hist['Close'], vkospi_hist['Close'], usdkrw_hist['Close'],
    ], axis=1).ffill().dropna()

    if df.empty or len(df) < 400:
        return None

    df.columns = ['KOSPI', 'VKOSPI', 'USDKRW']

    # Drawdown (max 35)
    df['KOSPI_High_252'] = df['KOSPI'].rolling(252, min_periods=252).max()
    df['Drawdown']     = (df['KOSPI'] / df['KOSPI_High_252'] - 1) * 100
    df['RSI']          = get_rolling_rsi(df['KOSPI'], 14)
    df['USDKRW_RSI']   = get_rolling_rsi(df['USDKRW'], 14)
    
    df = df.dropna(subset=['Drawdown', 'RSI', 'USDKRW_RSI'])
    if df.empty:
        return None

    df['Fwd_3M_Ret'] = (df['KOSPI'].shift(-63)  / df['KOSPI'] - 1) * 100
    df['Fwd_6M_Ret'] = (df['KOSPI'].shift(-126) / df['KOSPI'] - 1) * 100

    dd = -df['Drawdown']
    kr_rsi = df['RSI']
    vkospi = df['VKOSPI']
    krw_rsi = df['USDKRW_RSI']

    # Vectorized score calculation (equivalent to calculate_kr_bottom_finder)
    s_dd = np.where(dd >= 20, 35,
             np.where(dd >= 12, 22 + (dd - 12) * (35 - 22) / (20 - 12),
               np.where(dd >= 7, 10 + (dd - 7) * (22 - 10) / (12 - 7),
                 np.where(dd > 0, dd * 10 / 7, 0))))
                 
    s_rsi = np.where(kr_rsi <= 30, 20,
              np.where(kr_rsi <= 40, 12 + (40 - kr_rsi) * (20 - 12) / (40 - 30),
                np.where(kr_rsi <= 45, 5 + (45 - kr_rsi) * (12 - 5) / (45 - 40),
                  np.where(kr_rsi <= 60, (60 - kr_rsi) * 5 / (60 - 45), 0))))
                  
    s_vkospi = np.where(vkospi >= 25, 25,
                 np.where(vkospi >= 20, 15 + (vkospi - 20) * (25 - 15) / (25 - 20),
                   np.where(vkospi >= 16, 5 + (vkospi - 16) * (15 - 5) / (20 - 16),
                     np.where(vkospi >= 12, (vkospi - 12) * 5 / (16 - 12), 0))))
                     
    s_krw = np.where(krw_rsi <= 55, 20,
              np.where(krw_rsi <= 65, 10 + (65 - krw_rsi) * (20 - 10) / (65 - 55),
                np.where(krw_rsi <= 75, (75 - krw_rsi) * 10 / (75 - 65), 0)))
                
    kill_switch = (krw_rsi > 70) & (df['Drawdown'] > -10)
    
    max_score = 100 # Assuming all data available
    score = (s_dd + s_rsi + s_vkospi + s_krw)
    score = np.round(score / max_score * 100).clip(0, 100)
    
    # Structure Bonus
    close = df['KOSPI']
    rets  = close.pct_change()
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma50_slope = (ma50 / ma50.shift(21) - 1) * 100
    down_ratio = (rets < 0).rolling(20).mean()
    p1 = close.shift(30).rolling(30).min()
    p2 = close.rolling(30).min()
    r1 = df['RSI'].shift(30).rolling(30).min()
    r2 = df['RSI'].rolling(30).min()

    bonus = np.zeros(len(df))
    bonus += np.where((df['Drawdown'] <= -10) & (down_ratio >= GRIND_DOWN_RATIO) & (ma50_slope < 0), 8, 0)
    bonus += np.where((p2 < p1) & (r2 > r1 + DIV_RSI_MARGIN), 10, 0)
    bonus += np.where((p2 > p1 * 1.005) & (df['Drawdown'] <= -8), 5, 0)
    bonus += np.where((close > ma20) & (df['Drawdown'] <= -10), 5, 0)
    
    score = np.minimum(score + bonus, 100)
    score = np.where(kill_switch, np.minimum(score, 30), score)
    
    # Knife penalty
    ret_1d  = rets * 100
    ma5     = close.rolling(5).mean()
    gap_ma5 = (close / ma5 - 1) * 100
    knife   = (ret_1d <= KNIFE_1D_RET) | (gap_ma5 <= KNIFE_MA5_GAP)
    score = np.where(knife & (score >= 35), score - KNIFE_PENALTY, score)
    df['Score'] = score.clip(0, 100).astype(int)

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
        "코로나 바닥": "2020-03-19",
        "2022 약세장 바닥": "2022-09-30",
        "2018 10월 폭락": "2018-10-29",
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
        except Exception:
            event_scores[name] = None

    return {
        "70점 이상 (강력 매수)":    _stat(res_70),
        "50~69점 (분할 매수)":      _stat(res_50),
        "주요 이벤트 점수":          event_scores,
        "score_series":             df[['Score', 'Drawdown']],
    }


# ═════════════════════════════════════════
# 종목 해석 / 라벨링 유틸
# ═════════════════════════════════════════
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
        elif fcf_y <= 0.02 and fcf_y > 0: texts.append("💡 현금 대비 주가에 프리미엄(기대감)이 반영된 성장주")
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


def analyze_macro_flow(macro_data, flow_data):
    """
    수집된 매크로 지표(금리, 유가, 환율)와 수급(외국인 등)을 교차 분석하여 국면(Phase) 확정.
    """
    tnx_df = macro_data.get('tnx_10y', None)
    wti_df = macro_data.get('wti_10y', None)
    usdkrw_df = macro_data.get('usdkrw_10y', None)
    
    # 최근 2거래일 데이터 추출
    tnx_current, tnx_change = 0, 0
    if tnx_df is not None and not tnx_df.empty:
        tnx_clean = tnx_df['Close'].dropna()
        if len(tnx_clean) >= 2:
            tnx_current = tnx_clean.iloc[-1]
            tnx_change = tnx_current - tnx_clean.iloc[-2]
        
    wti_current, wti_change = 0, 0
    if wti_df is not None and not wti_df.empty:
        wti_clean = wti_df['Close'].dropna()
        if len(wti_clean) >= 2:
            wti_current = wti_clean.iloc[-1]
            wti_change = wti_current - wti_clean.iloc[-2]
        
    usdkrw_current, usdkrw_change = 0, 0
    if usdkrw_df is not None and not usdkrw_df.empty:
        usdkrw_clean = usdkrw_df['Close'].dropna()
        if len(usdkrw_clean) >= 2:
            usdkrw_current = usdkrw_clean.iloc[-1]
            usdkrw_change = usdkrw_current - usdkrw_clean.iloc[-2]
        
    foreigner, institutional, retail = flow_data
    
    # 시나리오 기계적 판별
    # 환율 상승 + 금리 상승 -> 강달러 리스크 오프
    # 외국인 매수 -> 자금 유입
    if usdkrw_change < 0 and tnx_change < 0 and foreigner > 0:
        phase = "🟢 리스크 온 (강한 외국인 자금 유입)"
    elif usdkrw_change > 0 and tnx_change > 0 and foreigner < 0:
        phase = "🔴 리스크 오프 (안전자산 선호 및 외국인 이탈)"
    elif foreigner > 0:
        phase = "🟡 개별 종목 장세 (매크로 혼조 속 외국인 매수)"
    elif foreigner < 0:
        phase = "🟡 조정 장세 (외국인 차익 실현 및 매도 우위)"
    else:
        phase = "⚪ 방향성 탐색 (눈치 보기 장세)"
        
    summary_dict = {
        "TNX_10Y": f"{tnx_current:.3f}% (전일대비 {tnx_change:+.3f}%p)",
        "WTI_Crude": f"${wti_current:.2f} (전일대비 {wti_change:+.2f}$)",
        "USD_KRW": f"{usdkrw_current:.1f}원 (전일대비 {usdkrw_change:+.1f}원)",
        "Foreigner": f"{foreigner:,}억원",
        "Institutional": f"{institutional:,}억원",
        "Retail": f"{retail:,}억원"
    }
    
    return phase, summary_dict

def generate_economic_commentary(summary_dict, phase):
    """
    코드가 판정한 데이터와 국면을 Gemini API에 던져 자연어 해설 생성.
    """
    import os
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ 환경 변수에 GEMINI_API_KEY가 설정되지 않아 AI 브리핑을 제공할 수 없습니다."
    
    # 새 SDK(google-genai) 시도 → 실패 시 구 SDK(google-generativeai) 시도
    prompt = f"""
    너는 CFO 역할을 맡은 거시경제 전문가다. 
    아래 전달받은 데이터(수치)와 시장 국면(판단 결과)을 임의로 수정하지 마라.
    대신 [미국 금리/유가 동향 ➔ 달러 가치(환율) 변화 ➔ 외국인 자금의 한국 시장 유입/이탈 ➔ 개인/기관의 대응]으로 이어지는 '돈의 흐름과 경제 상황'을 인과관계에 맞게 3~4문장으로 알기 쉽게 해설해라.

    [시장 데이터]
    - 미국 10년물 국채 금리: {summary_dict['TNX_10Y']}
    - WTI 원유: {summary_dict['WTI_Crude']}
    - 원/달러 환율: {summary_dict['USD_KRW']}
    
    [코스피 수급 (순매수)]
    - 외국인: {summary_dict['Foreigner']}
    - 기관합계: {summary_dict['Institutional']}
    - 개인: {summary_dict['Retail']}
    
    [시스템이 판정한 현재 시장 국면]
    - {phase}
    
    오직 해설 텍스트만 3~4문장으로 작성해. 불필요한 인사말이나 마크다운 포맷팅은 제외해.
    """
    
    # 방법 1: 새 SDK (google-genai)
    e1_error = "Not attempted"
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e1:
        e1_error = str(e1)
        print(f"[google-genai 시도 실패]: {e1}")
    
    # 방법 2: 구 SDK (google-generativeai) 폴백
    try:
        import google.generativeai as genai_old
        genai_old.configure(api_key=api_key)
        
        # 사용 가능한 모델 리스트 강제 추출 (디버깅 용도)
        available_models = []
        try:
            for m in genai_old.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
        except Exception as list_e:
            available_models.append(f"List error: {list_e}")
            
        model = genai_old.GenerativeModel("gemini-1.5-flash")
        safety_settings = [
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        return response.text.strip()
    except Exception as e2:
        return f"⚠️ 디버깅 정보:\n[새 라이브러리(google-genai) 에러]: {e1_error}\n\n[구 라이브러리(generativeai) 에러]: {e2}\n\n[현재 계정에서 사용 가능한 모델 목록]: {', '.join(available_models)}"


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
            except Exception:
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

# Force Streamlit to reload this module
