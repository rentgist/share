import os
import requests
import json
import datetime
from data_loader import get_macro_charts, get_real_cnn_fg, get_stock_data
from signals import calculate_us_bottom_finder, calculate_kr_bottom_finder, get_ai_signal

# ═════════════════════════════════════════
# ⚙️ 봇 설정 (조건 및 임계값)
# ═════════════════════════════════════════
SCORE_THRESHOLD = 80          # 이 점수 이상일 때 알림 (진바닥 임계치)
TARGET_STOCK_NAME = "브로드컴" # 주시할 종목 이름 (US_NAME_MAP에 정의된 이름)
TARGET_STOCK_TICKER = "AVGO"
TARGET_AI_SIGNALS = ["🔥 바닥 줍줍 (적극매수)", "🛒 분할매수 시작"] # 이 시그널이 뜰 때 알림

def send_telegram_alert(token, chat_id, message):
    """텔레그램 메시지 전송 (Markdown 파싱)"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ 텔레그램 알림 발송 성공")
    except Exception as e:
        print(f"❌ 텔레그램 알림 발송 실패: {e}")

def run_alert_logic():
    print("⏳ 11원칙 퀀트 에이전트 무인 감시 시작...")
    
    # 1. 깃허브 시크릿(환경변수)에서 키 불러오기
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️ 토큰이나 Chat ID가 설정되지 않았습니다. 알림을 보낼 수 없습니다.")
        # 로컬 테스트를 위해 리턴하지 않고 진행할 수도 있으나, 실제 발송은 불가
    
    messages = []
    
    # 2. 매크로 지표 분석 (바닥 탐지기)
    print("📊 매크로 데이터 로딩 중...")
    cnn_score, _, _ = get_real_cnn_fg()
    charts = get_macro_charts()
    
    if charts and "SPY" in charts and "^VIX" in charts:
        us_score, us_verdict, _, _ = calculate_us_bottom_finder(charts["SPY"], charts["^VIX"], cnn_score)
        print(f"🇺🇸 미국 바닥 점수: {us_score}점")
        if us_score >= SCORE_THRESHOLD:
            msg = f"🚨 **[미국 증시 진바닥 포착]** 🚨\n* **점수**: `{us_score}점`\n* **상태**: {us_verdict}\n* **조치**: 현금 투입(스나이퍼) 조건을 확인하세요."
            messages.append(msg)
            
    if charts and "KS11" in charts and "^VKOSPI" in charts and "USDKRW=X" in charts:
        kr_score, kr_verdict, _, _ = calculate_kr_bottom_finder(charts["KS11"], charts["^VKOSPI"], charts["USDKRW=X"])
        print(f"🇰🇷 한국 바닥 점수: {kr_score}점")
        if kr_score >= SCORE_THRESHOLD:
            msg = f"🚨 **[한국 증시 진바닥 포착]** 🚨\n* **점수**: `{kr_score}점`\n* **상태**: {kr_verdict}\n* **조치**: 현금 투입(스나이퍼) 조건을 확인하세요."
            messages.append(msg)

    # 3. 개별 타겟 종목 감시 (AI 시그널)
    print(f"🎯 타겟 종목 ({TARGET_STOCK_NAME}) 데이터 로딩 중...")
    d = get_stock_data(TARGET_STOCK_NAME, is_kr=False, fast_mode=False)
    if not d.get("error"):
        ai_sig = get_ai_signal(d)
        print(f"🤖 {TARGET_STOCK_NAME} 시그널: {ai_sig}")
        
        # 특정 시그널이 발생하면 알림
        if any(target in ai_sig for target in TARGET_AI_SIGNALS):
            close_price = d.get('Close', 0)
            rsi = d.get('RSI', 0)
            msg = (
                f"🎯 **[타겟 종목 시그널 포착]** 🎯\n"
                f"**종목**: {TARGET_STOCK_NAME} ({TARGET_STOCK_TICKER})\n"
                f"**현재가**: ${close_price:.2f}\n"
                f"**RSI**: {rsi:.1f}\n"
                f"**시그널**: `{ai_sig}`\n"
                f"**코멘트**: 설정된 매수 시그널이 감지되었습니다."
            )
            messages.append(msg)
    else:
        print(f"⚠️ 타겟 종목 로딩 실패: {d.get('error')}")

    # 4. 종합 알림 발송
    if messages:
        final_message = "🔔 **[11원칙 퀀트 에이전트 정기 보고]** 🔔\n\n" + "\n\n---\n\n".join(messages)
        print("\n[전송할 메시지 미리보기]\n" + final_message + "\n")
        if token and chat_id:
            send_telegram_alert(token, chat_id, final_message)
    else:
        print("💤 임계치를 넘는 특이사항이 없어 알림을 생략합니다.")

if __name__ == "__main__":
    run_alert_logic()
