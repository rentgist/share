import os
import requests
import json
import datetime
import traceback
from data_loader import get_macro_charts, get_real_cnn_fg, get_stock_data
from signals import calculate_us_bottom_finder, calculate_kr_bottom_finder, get_ai_signal, get_tenbagger_signal

# ═════════════════════════════════════════
# ⚙️ 봇 설정 (조건 및 임계값)
# ═════════════════════════════════════════
SCORE_THRESHOLD_1 = 50   # 1차 선발대 분할 매수 타점
SCORE_THRESHOLD_2 = 70   # 강력 매수 구간 (현금 투입 스나이퍼)

# 감시할 핵심 타겟 종목 리스트: (종목명/티커, 한국장 여부)
TARGET_STOCKS = [
    ("삼성전자", True),
    ("SK하이닉스", True),
    ("브로드컴", False),
    ("엔비디아", False),
    ("버티브", False),
    ("마이크로소프트", False),
    ("원익QnC", True),
    ("LS ELECTRIC", True)
]

# 텐배거 스캔 유니버스
TENBAGGER_UNIVERSE = {
    "🇺🇸 미국 AI & 클라우드": ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
    "🇺🇸 미국 혁신성장": ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
    "🇰🇷 한국 반도체 소부장": ["한미반도체", "디아이", "테크윙", "HPSP", "이수페타시스", "에이직랜드", "와이아이케이", "원익IPS", "에스티아이", "주성엔지니어링", "리노공업", "하나마이크론"],
    "🇰🇷 한국 K-뷰티/푸드": ["실리콘투","클리오","삼양식품","빙그레","에이피알","브이티","코스메카코리아"],
    "🇰🇷 한국 바이오/헬스케어": ["알테오젠","HLB","삼천당제약","리가켐바이오","에이비엘바이오","파마리서치"],
    "🇰🇷 한국 전력/인프라": ["HD현대일렉트릭","제룡전기","효성중공업","LS ELECTRIC"],
}

TARGET_AI_SIGNALS = ["🔥 바닥 줍줍 (적극매수)", "🛒 분할매수 시작"]

def send_telegram_alert(token, chat_id, message):
    """텔레그램 메시지 전송 (HTML 파싱)"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"❌ 텔레그램 오류 상세: {response.text}")
        response.raise_for_status()
        print("✅ 텔레그램 알림 발송 성공")
    except Exception as e:
        print(f"❌ 텔레그램 알림 발송 실패: {e}")

def get_market_alert(score, verdict, market_name):
    """바닥 점수에 따른 알림 메시지 생성"""
    if score >= SCORE_THRESHOLD_2:
        return f"🚨 <b>[{market_name} 강력 매수 구간 진입!]</b> 🚨\n- <b>점수</b>: {score}점\n- <b>상태</b>: {verdict}\n- <b>조치</b>: 현금 투입(스나이퍼) 및 2~3차 비중 확대 타점입니다."
    elif score >= SCORE_THRESHOLD_1:
        return f"⚠️ <b>[{market_name} 1차 선발대 진입 타점]</b> ⚠️\n- <b>점수</b>: {score}점\n- <b>상태</b>: {verdict}\n- <b>조치</b>: 1차 선발대(30~50%) 분할 매수를 고려할 시점입니다."
    return None

def fmt(v):
    if v is None: return "N/A"
    return f"{v:.2f}"

def run_alert_logic():
    print("⏳ 11원칙 퀀트 에이전트 무인 감시 시작 (V2)...")
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ 토큰이나 Chat ID가 설정되지 않았습니다. (로컬 테스트 모드)")

    summary_messages = []
    detailed_messages = []
    
    # 1. 매크로 지표 분석 (바닥 탐지기)
    print("📊 매크로 데이터 로딩 중...")
    cnn_score, cnn_rating, _ = get_real_cnn_fg()
    charts = get_macro_charts()
    
    us_score = kr_score = "N/A"
    us_verdict = kr_verdict = "N/A"
    
    market_summary = ""
    market_details = ""
    
    if charts and "SPY" in charts and "^VIX" in charts:
        us_score, us_verdict, _, us_phase = calculate_us_bottom_finder(charts["SPY"], charts["^VIX"], cnn_score)
        print(f"🇺🇸 미국 바닥 점수: {us_score}점")
        alert_msg = get_market_alert(us_score, us_verdict, "미국 증시")
        if alert_msg:
            summary_messages.append(alert_msg)
        
        market_summary += f"🇺🇸 미국: {us_score}점 ({us_phase})\n"
        market_details += f"[미국 증시 매크로]\n- 국면: {us_phase}\n- 진바닥 점수: {us_score}\n- CNN F&G: {cnn_score} ({cnn_rating})\n\n"
            
    if charts and "KS11" in charts and "^VKOSPI" in charts and "USDKRW=X" in charts:
        kr_score, kr_verdict, _, kr_phase = calculate_kr_bottom_finder(charts["KS11"], charts["^VKOSPI"], charts["USDKRW=X"])
        print(f"🇰🇷 한국 바닥 점수: {kr_score}점")
        alert_msg = get_market_alert(kr_score, kr_verdict, "한국 증시")
        if alert_msg:
            summary_messages.append(alert_msg)
            
        market_summary += f"🇰🇷 한국: {kr_score}점 ({kr_phase})\n"
        market_details += f"[한국 증시 매크로]\n- 국면: {kr_phase}\n- 진바닥 점수: {kr_score}\n\n"

    # 2. 핵심 타겟 종목 스캔
    print(f"🎯 핵심 타겟 종목 ({len(TARGET_STOCKS)}개) 감시 중...")
    for name, is_kr in TARGET_STOCKS:
        print(f" - {name} 스캔 중...")
        try:
            d = get_stock_data(name, is_kr=is_kr, fast_mode=False)
            if not d.get("error"):
                ai_sig = get_ai_signal(d)
                
                if any(target in ai_sig for target in TARGET_AI_SIGNALS):
                    close_price = d.get('Close', 0)
                    rsi = d.get('RSI_14', d.get('RSI', 0))
                    gap_high = d.get('Gap_High', 0)
                    
                    summary_messages.append(
                        f"🎯 <b>[{name} 매수 시그널 포착]</b>\n"
                        f"- <b>시그널</b>: {ai_sig}\n"
                        f"- <b>현재가</b>: {close_price:,.0f} (고점대비 {gap_high:.1f}%)"
                    )
                    
                    detailed_messages.append(
                        f"[{name} 상세 제언용 데이터]\n"
                        f"- 시그널: {ai_sig}\n"
                        f"- RSI(14): {fmt(rsi)}\n"
                        f"- 고점대비 하락률: {fmt(gap_high)}%\n"
                        f"- PER / Fwd PER: {fmt(d.get('PER'))} / {fmt(d.get('Forward_PER'))}\n"
                        f"- PBR / ROE: {fmt(d.get('PBR'))} / {fmt(d.get('ROE'))}\n"
                        f"- Rule of 40: {fmt(d.get('Rule_of_40'))}%\n"
                        f"- 판단 근거: 설정된 핵심 타겟 종목에서 {ai_sig} 시그널이 감지되었습니다."
                    )
        except Exception as e:
            print(f"⚠️ {name} 스캔 중 오류: {e}")
            traceback.print_exc()

    # 3. 텐배거 Must-Enter 종목 감시
    print("🚀 텐배거 Must-Enter 종목 전수 스캔 중...")
    for theme, tickers in TENBAGGER_UNIVERSE.items():
        is_kr = "한국" in theme
        for tk in tickers:
            try:
                d = get_stock_data(tk, is_kr=is_kr, fast_mode=False)
                if not d.get("error"):
                    is_tenbagger = get_tenbagger_signal(d)
                    
                    # Must-Enter 조건: 텐배거 필터 통과 + (고점대비 -20% 이하 하락 또는 RSI 45 이하)
                    gap_high = d.get('Gap_High', 0)
                    rsi = d.get('RSI_14', 100)
                    
                    if is_tenbagger is True and (gap_high <= -20 or rsi <= 45):
                        close_price = d.get('Close', 0)
                        
                        summary_messages.append(
                            f"🦄 <b>[{d['Name']} 텐배거 진입 기회!]</b>\n"
                            f"- <b>테마</b>: {theme}\n"
                            f"- <b>사유</b>: 실적/마진 우량 + 낙폭 과대 (Gap {gap_high:.1f}%, RSI {rsi:.1f})"
                        )
                        
                        detailed_messages.append(
                            f"[{d['Name']} 텐배거 상세 데이터]\n"
                            f"- 소속 테마: {theme}\n"
                            f"- 고점대비 하락률: {fmt(gap_high)}%\n"
                            f"- RSI(14): {fmt(rsi)}\n"
                            f"- Rule of 40: {fmt(d.get('Rule_of_40'))}%\n"
                            f"- PER / PEG: {fmt(d.get('PER'))} / {fmt(d.get('PEG'))}\n"
                            f"- 판단 근거: 11원칙 텐배거 재무 펀더멘털 필터를 완벽히 통과했으며, 동시에 가격이 -20% 이상 하락했거나 RSI가 45 이하로 떨어져 진입 매력도가 극대화된 상태입니다."
                        )
            except Exception as e:
                print(f"⚠️ {tk} 텐배거 스캔 중 오류: {e}")

    # 4. 종합 알림 발송 구성 (Summary + Detailed AI Prompt)
    if summary_messages or detailed_messages:
        final_message = "🔔 <b>[11원칙 퀀트 에이전트 긴급 보고]</b> 🔔\n\n"
        final_message += "━━━━━━━━━━━━━━━━━━━━\n"
        final_message += "💡 <b>[요약본 (Quick Summary)]</b>\n"
        final_message += "━━━━━━━━━━━━━━━━━━━━\n"
        final_message += f"📊 <b>전체 시장 상태</b>\n{market_summary}\n"
        final_message += "\n\n".join(summary_messages)
        
        final_message += "\n\n━━━━━━━━━━━━━━━━━━━━\n"
        final_message += "🤖 <b>[AI 참모용 상세 데이터]</b>\n"
        final_message += "<i>아래 내용을 복사하여 ChatGPT나 Claude에게 보내세요.</i>\n"
        final_message += "━━━━━━━━━━━━━━━━━━━━\n"
        final_message += "<code>다음 퀀트 데이터를 바탕으로 현재 시장 상황과 매수 타점에 대한 종합적인 투자 제언을 작성해줘:\n\n"
        final_message += f"{market_details}"
        final_message += "\n\n".join(detailed_messages)
        final_message += "</code>"
    else:
        final_message = (
            f"💤 <b>[11원칙 퀀트 에이전트 정기 보고]</b>\n"
            f"현재 시장이나 타겟 종목에 1차 선발대(50점) 이상의 특이 시그널이 없습니다.\n\n"
            f"📊 <b>현재 진바닥 점수</b>\n"
            f"🇺🇸 미국: <code>{us_score}점</code>\n"
            f"🇰🇷 한국: <code>{kr_score}점</code>"
        )
        print("💤 임계치 미달. 요약 상태를 전송합니다.")

    print("\n[전송할 메시지 미리보기]\n" + final_message + "\n")
    if token and chat_id:
        send_telegram_alert(token, chat_id, final_message)

if __name__ == "__main__":
    run_alert_logic()
