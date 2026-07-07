import os
import requests
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import traceback
import google.generativeai as genai

from data_loader import get_macro_charts, get_real_cnn_fg, get_stock_data
from signals import calculate_us_bottom_finder, calculate_kr_bottom_finder, get_ai_signal, get_tenbagger_signal

# ═════════════════════════════════════════
# ⚙️ 봇 설정 (조건 및 임계값)
# ═════════════════════════════════════════
SCORE_THRESHOLD_1 = 50   # 1차 선발대 분할 매수 타점
SCORE_THRESHOLD_2 = 70   # 강력 매수 구간 (현금 투입 스나이퍼)

# 감시할 핵심 타겟 종목 리스트
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

def fetch_market_news():
    """구글 뉴스 RSS에서 굵직한 거시/증시/이슈 헤드라인 7개를 크롤링합니다."""
    print("📰 최신 마켓 뉴스 크롤링 중...")
    try:
        keywords = '증시 OR 금리 OR FOMC OR CPI OR 고용 OR 국민연금 OR 지정학 OR 전쟁 OR 실적발표 OR 연준 OR 파월'
        encoded = urllib.parse.quote(keywords)
        url = f'https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        news_list = []
        for item in root.findall('.//item')[:7]:
            title = item.find('title').text
            news_list.append(f"- {title}")
        return "\n".join(news_list)
    except Exception as e:
        print(f"❌ 뉴스 크롤링 실패: {e}")
        return "- 뉴스 데이터를 불러오지 못했습니다."

def analyze_with_gemini(prompt_data):
    """Gemini API를 호출하여 퀀트 데이터와 뉴스를 기반으로 최종 텔레그램 메시지를 생성합니다."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY가 없습니다. 원본 데이터만 전송합니다.")
        return "⚠️ <b>[AI 미탑재 모드]</b> GEMINI_API_KEY가 설정되지 않았습니다.\n\n" + prompt_data.replace("<", "&lt;").replace(">", "&gt;")
        
    print("🧠 Gemini AI 분석 중...")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-pro')
        
        system_prompt = """너는 '11원칙 퀀트 투자' 전략을 따르는 최고의 AI 참모 비서야. 대장님(사용자)의 대시보드 로직과 전략을 100% 동일하게 반영해야 해.
아래 제공되는 시장 매크로 데이터, 개별 종목 시그널, 최신 뉴스 헤드라인을 완벽하게 융합해서 텔레그램 보고서를 작성해줘.

[작성 규칙]
1. 텔레그램 HTML 파싱 포맷을 사용해 (<b>, <i>, <code>, <u>, <s>). 마크다운 문법(```)은 텔레그램 에러를 유발하므로 절대 쓰지 마.
2. 최상단에는 친근하고 전문적인 인사말과 함께 전체 시장 요약(미/국장 진바닥 점수 및 국면)을 짚어줘.
3. 매수 시그널(바닥 줍줍, 분할매수 등)이 발생한 종목이나 텐배거 진입 기회가 있다면, 대시보드의 재무 데이터(PER, ROE, Rule of 40 등)와 오늘의 [마켓 주요 뉴스]를 입체적으로 엮어서 '지금 진입해야 하는 핵심 논리'를 제공해.
4. 매수 시그널이 전혀 없다면, "현재는 시장을 관망하며 현금을 비축할 때입니다"라고 조언해.
5. 맨 아래에는 오늘 수집된 [주요 마켓 뉴스 헤드라인]을 깔끔하게 리스트로 첨부해.
6. 응답은 오직 텔레그램 메시지 본문 내용만 출력해라. 절대로 마크다운 코드블록(```html)으로 감싸지 마."""
        
        full_prompt = f"{system_prompt}\n\n[오늘의 퀀트 데이터 및 뉴스]\n{prompt_data}"
        response = model.generate_content(full_prompt)
        
        # 텔레그램 파싱 에러 방지를 위해 markdown 코드 블록 흔적 제거
        text = response.text.strip()
        if text.startswith("```html"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return text.strip()
    except Exception as e:
        print(f"❌ Gemini API 호출 실패: {e}")
        return "⚠️ <b>[AI 분석 오류 발생]</b>\n\n" + prompt_data.replace("<", "&lt;").replace(">", "&gt;")

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
        return f"[{market_name} 강력 매수 구간 진입! (스나이퍼)] 점수: {score}점"
    elif score >= SCORE_THRESHOLD_1:
        return f"[{market_name} 1차 선발대 진입 타점] 점수: {score}점"
    return None

def fmt(v):
    if v is None: return "N/A"
    return f"{v:.2f}"

def run_alert_logic():
    print("⏳ 11원칙 퀀트 에이전트 무인 감시 시작 (AI 탑재 모드)...")
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ 텔레그램 토큰이 설정되지 않았습니다. (로컬 테스트 모드)")

    raw_data_buffer = []
    
    # 1. 뉴스 크롤링
    news_text = fetch_market_news()
    raw_data_buffer.append("===== 마켓 주요 뉴스 =====\n" + news_text)
    
    # 2. 매크로 지표 분석
    print("📊 매크로 데이터 로딩 중...")
    cnn_score, cnn_rating, _ = get_real_cnn_fg()
    charts = get_macro_charts()
    
    macro_buf = ["===== 매크로(진바닥) 점수 ====="]
    if charts and "SPY" in charts and "^VIX" in charts:
        us_score, us_verdict, _, us_phase = calculate_us_bottom_finder(charts["SPY"], charts["^VIX"], cnn_score)
        print(f"🇺🇸 미국 바닥 점수: {us_score}점")
        macro_buf.append(f"🇺🇸 미국: {us_score}점 (국면: {us_phase}, CNN F&G: {cnn_score} {cnn_rating})")
            
    if charts and "KS11" in charts and "^VKOSPI" in charts and "USDKRW=X" in charts:
        kr_score, kr_verdict, _, kr_phase = calculate_kr_bottom_finder(charts["KS11"], charts["^VKOSPI"], charts["USDKRW=X"])
        print(f"🇰🇷 한국 바닥 점수: {kr_score}점")
        macro_buf.append(f"🇰🇷 한국: {kr_score}점 (국면: {kr_phase})")
    
    raw_data_buffer.append("\n".join(macro_buf))

    # 3. 핵심 타겟 종목 스캔
    print(f"🎯 핵심 타겟 종목 스캔 중...")
    stock_buf = ["===== 개별 종목 매수 시그널 ====="]
    signal_found = False
    
    for name, is_kr in TARGET_STOCKS:
        try:
            d = get_stock_data(name, is_kr=is_kr, fast_mode=False)
            if not d.get("error"):
                ai_sig = get_ai_signal(d)
                if any(target in ai_sig for target in TARGET_AI_SIGNALS):
                    signal_found = True
                    gap_high = d.get('Gap_High', 0)
                    rsi = d.get('RSI_14', d.get('RSI', 0))
                    stock_buf.append(
                        f"- 종목명: {name}\n  시그널: {ai_sig}\n  고점대비 하락률: {fmt(gap_high)}%\n  RSI: {fmt(rsi)}\n  PER: {fmt(d.get('PER'))}, ROE: {fmt(d.get('ROE'))}"
                    )
        except Exception as e:
            print(f"⚠️ {name} 스캔 중 오류: {e}")
            
    if not signal_found:
        stock_buf.append("- 현재 핵심 타겟 종목 중 매수 시그널(바닥 줍줍, 분할매수)이 발생한 종목이 없습니다.")
        
    raw_data_buffer.append("\n".join(stock_buf))

    # 4. 텐배거 Must-Enter 종목 감시
    print("🚀 텐배거 전수 스캔 중...")
    tb_buf = ["===== 텐배거 Must-Enter 기회 ====="]
    tb_found = False
    
    for theme, tickers in TENBAGGER_UNIVERSE.items():
        is_kr = "한국" in theme
        for tk in tickers:
            try:
                d = get_stock_data(tk, is_kr=is_kr, fast_mode=False)
                if not d.get("error"):
                    is_tenbagger = get_tenbagger_signal(d)
                    gap_high = d.get('Gap_High', 0)
                    rsi = d.get('RSI_14', 100)
                    if is_tenbagger is True and (gap_high <= -20 or rsi <= 45):
                        tb_found = True
                        tb_buf.append(
                            f"- 종목명: {d['Name']} ({theme})\n  고점대비: {fmt(gap_high)}%, RSI: {fmt(rsi)}, Rule of 40: {fmt(d.get('Rule_of_40'))}%"
                        )
            except Exception:
                pass
                
    if not tb_found:
        tb_buf.append("- 현재 진입하기 완벽한 텐배거 특이 종목이 없습니다.")
        
    raw_data_buffer.append("\n".join(tb_buf))

    # 5. 최종 데이터 결합 및 AI 분석
    final_prompt_data = "\n\n".join(raw_data_buffer)
    print("\n[AI 프롬프트용 수집 데이터]")
    print(final_prompt_data)
    
    final_message = analyze_with_gemini(final_prompt_data)

    print("\n[전송할 텔레그램 메시지]\n" + final_message + "\n")
    if token and chat_id:
        send_telegram_alert(token, chat_id, final_message)

if __name__ == "__main__":
    run_alert_logic()
