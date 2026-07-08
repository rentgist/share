import os
import datetime
import time
import requests
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import google.generativeai as genai

os.environ['TZ'] = 'Asia/Seoul'
time.tzset()

from data_loader import get_macro_charts, get_real_cnn_fg, get_stock_data
from signals import (
    calculate_us_bottom_finder,
    calculate_kr_bottom_finder,
    calculate_us_risk_radar,
    calculate_kr_risk_radar,
    get_strategic_advice,
    get_ai_signal,
    get_tenbagger_signal,
)

# ═════════════════════════════════════════
# ⚙️ 봇 설정
# ═════════════════════════════════════════
SCORE_THRESHOLD_1 = 50
SCORE_THRESHOLD_2 = 70

TENBAGGER_BUY_SIGNALS = {
    "🔥 기관 최선호 대장주",
    "🔥 기관 최선호 대장주 (Rule of 40)",
    "🌱 우량 고성장주",
    "🌱 우량 고성장주 (Rule of 40)",
}

TARGET_STOCKS = [
    ("삼성전자",     True),
    ("SK하이닉스",   True),
    ("브로드컴",     False),
    ("엔비디아",     False),
    ("버티브",       False),
    ("마이크로소프트", False),
    ("원익QnC",      True),
    ("LS ELECTRIC",  True),
]

TENBAGGER_UNIVERSE = {
    "🇺🇸 미국 AI & 클라우드":      ["PLTR","CRWD","SNOW","DDOG","NET","SOUN","MDB","ZS","MNDY"],
    "🇺🇸 미국 혁신성장":           ["IONQ","SOFI","RIVN","CELH","RKLB","ASTS","CRSP","LUNR","SYM","HOOD"],
    "🇰🇷 한국 반도체 소부장":       ["한미반도체","디아이","테크윙","HPSP","이수페타시스","에이직랜드",
                                    "와이아이케이","원익IPS","에스티아이","주성엔지니어링","리노공업","하나마이크론"],
    "🇰🇷 한국 K-뷰티/푸드":        ["실리콘투","클리오","삼양식품","빙그레","에이피알","브이티","코스메카코리아"],
    "🇰🇷 한국 바이오/헬스케어":     ["알테오젠","HLB","삼천당제약","리가켐바이오","에이비엘바이오","파마리서치"],
    "🇰🇷 한국 전력/인프라":        ["HD현대일렉트릭","제룡전기","효성중공업","LS ELECTRIC"],
}

TARGET_AI_SIGNALS = ["🔥 바닥 줍줍 (적극매수)", "🟢 얕은 눌림목 (분할매수)"]

# ─────────────────────────────────────────
# 확정 일정 캘린더 (뉴스와 별도 채널)
# ─────────────────────────────────────────
# ★ 수정 포인트 2: 확정 일정을 RSS 뉴스와 분리해서 별도 채널로 관리.
#   - RSS는 타이밍 의존적이라 중요 이벤트를 놓칠 수 있음.
#   - 확정 일정은 코드에 직접 박아서 항상 안정적으로 경고.
#   - 점수에는 반영하지 않고 "사실 정보"만 전달 (Gemini 판단 최소화).
FIXED_EVENTS = [
    {
        "name": "국민연금 전략적 자산배분 리밸런싱",
        "date": "2026-07-31",
        "scale": "약 50~60조원 추정",
        "note": "역사적으로 리밸런싱 전후 2~3주간 코스피 변동성 확대 패턴 있음. "
                "정확한 일정과 규모는 국민연금공단 공시 확인 필요.",
    },
]

def get_upcoming_fixed_events(days_ahead: int = 45) -> list[dict]:
    """앞으로 N일 이내 확정 이벤트 반환"""
    today = datetime.datetime.now().date()
    upcoming = []
    for ev in FIXED_EVENTS:
        try:
            ev_date = datetime.datetime.strptime(ev["date"], "%Y-%m-%d").date()
            d_left  = (ev_date - today).days
            if 0 <= d_left <= days_ahead:
                upcoming.append({**ev, "days_left": d_left})
        except Exception:
            continue
    return upcoming


# ─────────────────────────────────────────
# ★ 수정 포인트 2: fetch_market_news 개선
#   - 기존: 헤드라인 7개를 단순 텍스트로 반환
#   - 변경: 헤드라인 + 원문 URL을 함께 반환 → Gemini가 맥락을 더 잘 판단 가능
#   - 확정 이벤트는 뉴스와 완전히 분리해서 별도 섹션으로 구성
# ─────────────────────────────────────────
def fetch_market_news(max_items: int = 7) -> tuple[list[dict], str]:
    """
    구글 뉴스 RSS 크롤링.
    반환: (news_items, error_msg)
    news_items: [{"title": str, "link": str, "pubDate": str}, ...]
    """
    print("📰 마켓 뉴스 크롤링 중...")
    keywords = (
        "증시 OR 금리 OR FOMC OR CPI OR 고용 OR 국민연금 OR "
        "지정학 OR 관세 OR 실적발표 OR 연준 OR 파월"
    )
    try:
        encoded = urllib.parse.quote(keywords)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root  = ET.fromstring(xml_data)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title   = (item.find("title").text   or "").strip()
            link    = (item.find("link").text     or "").strip()
            pubdate = (item.find("pubDate").text  or "").strip()
            if title:
                items.append({"title": title, "link": link, "pubDate": pubdate})
        return items, ""

    except Exception as e:
        print(f"❌ 뉴스 크롤링 실패: {e}")
        return [], str(e)


def fmt(v, suffix="") -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.2f}{suffix}"
    except Exception:
        return str(v)


# ─────────────────────────────────────────
# ★ 수정 포인트 3: analyze_with_gemini 구조 개선
#   - 기존: Gemini에게 판단 + 설명 모두 맡김 → 근거 없는 내러티브 위험
#   - 변경: 코드가 먼저 판단(점수, 국면, 전략 제언)을 완료하고
#           Gemini는 그 판단을 자연어로 설명하는 역할만 담당
#   - Gemini가 점수를 바꾸거나 독자적 판단을 내리지 못하도록
#     "아래 판단 결과를 변경하지 말고 그대로 보고서 형식으로 작성"을 명시
# ─────────────────────────────────────────
def analyze_with_gemini(
    code_judgment: str,   # 코드가 먼저 완성한 판단 결과 (점수, 국면, 시그널)
    news_context: str,    # 뉴스 헤드라인 + URL 목록
    fixed_events: str,    # 확정 일정 별도 섹션
) -> str:
    """
    Gemini 역할: 코드 판단을 자연어로 설명하고, 뉴스를 배경 맥락으로 연결하는 것.
    Gemini 역할이 아닌 것: 점수 산정, 매수/매도 판단, 시장 예측.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY 없음. 코드 판단만 전송.")
        return (
            "⚠️ <b>[AI 미탑재 모드]</b> GEMINI_API_KEY가 설정되지 않았습니다.\n\n"
            + code_judgment.replace("<", "&lt;").replace(">", "&gt;")
        )

    print("🧠 Gemini AI 설명 생성 중...")

    # ★ 핵심: 시스템 프롬프트에서 역할 분리를 명확히 선언
    system_prompt = """
[역할 정의]
너는 11원칙 퀀트 대시보드의 '보고서 작성 보조 AI'야.
아래에 퀀트 시스템이 이미 완성한 판단 결과가 주어진다.

[절대 금지 사항]
- 주어진 점수나 판단 결과를 네가 임의로 바꾸지 마.
- "제 생각에는", "분석해보면" 같은 AI 독자 판단 표현을 쓰지 마.
- 뉴스 헤드라인을 근거로 점수나 전략 제언을 수정하지 마.
  뉴스는 오직 '왜 지금 이런 매크로 환경이 만들어졌는지' 배경 설명에만 써.

[네가 해야 하는 것]
1. 코드 판단 결과를 텔레그램 HTML 형식으로 깔끔하게 정리해.
   (<b>, <i>, <code> 태그만 사용. 마크다운 ``` 절대 금지)
2. 각 판단 항목(매크로 점수, 국면, 전략 제언) 옆에
   오늘 뉴스 중 관련 배경을 1~2문장으로 자연스럽게 연결해.
   예: "미국 바닥 탐지기 8점 (고점권)" 옆에
       → "이 기간 미 연준 파월 의장 발언으로 금리 인하 기대가 후퇴한 점이 배경."
3. 확정 일정(국민연금 리밸런싱 등)은 별도 섹션으로 맨 아래에 배치.
4. 전략 제언은 코드가 내린 것을 그대로 전달. 네가 추가 조언을 붙이지 마.
5. 마지막에 뉴스 출처 링크를 리스트로 정리.

[형식]
응답은 텔레그램 메시지 본문만 출력. 코드블록으로 감싸지 마.
""".strip()

    full_prompt = (
        f"{system_prompt}\n\n"
        f"=== [코드 판단 결과 — 수정 금지] ===\n{code_judgment}\n\n"
        f"=== [오늘의 뉴스 헤드라인 + 출처] ===\n{news_context}\n\n"
        f"=== [확정 이벤트 일정] ===\n{fixed_events}"
    )

    try:
        genai.configure(api_key=api_key)
        model   = genai.GenerativeModel("gemini-1.5-pro")
        
        # 유해 콘텐츠 필터 강제 해제 (마켓 뉴스 키워드 차단 방지)
        from google.generativeai.types import HarmCategory, HarmBlockThreshold
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        response = model.generate_content(full_prompt, safety_settings=safety_settings)
        text = response.text.strip()
        # markdown 코드블록 잔재 제거
        for tag in ("```html", "```"):
            if text.startswith(tag):
                text = text[len(tag):]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    except Exception as e:
        print(f"❌ Gemini 호출 실패: {e}")
        return (
            "⚠️ <b>[AI 분석 오류]</b>\n\n"
            + code_judgment.replace("<", "&lt;").replace(">", "&gt;")
        )


def send_telegram_alert(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print("✅ 텔레그램 전송 성공 (HTML 모드)")
    except requests.exceptions.HTTPError as e:
        if r.status_code == 400:
            print("⚠️ 텔레그램 HTML 파싱 에러 발생. 일반 텍스트 모드로 재전송 시도...")
            payload["parse_mode"] = None
            try:
                r_fallback = requests.post(url, json=payload, timeout=10)
                r_fallback.raise_for_status()
                print("✅ 텔레그램 전송 성공 (일반 텍스트 모드)")
            except Exception as ex:
                print(f"❌ 텔레그램 재전송 실패: {ex}")
        else:
            print(f"❌ 텔레그램 HTTP 에러: {r.text}")
    except Exception as e:
        print(f"❌ 텔레그램 전송 실패: {e}")


# ─────────────────────────────────────────
# 메인 로직
# ─────────────────────────────────────────
def run_alert_logic() -> None:
    print("⏳ 11원칙 퀀트 에이전트 시작...")

    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ 텔레그램 토큰 없음. 로컬 테스트 모드.")

    # ── 섹션 A: 뉴스 수집 (확정 이벤트와 분리) ──
    news_items, news_err = fetch_market_news()
    if news_items:
        news_context = "\n".join(
            f"- {it['title']}\n  출처: {it['link']}  ({it['pubDate'][:16]})"
            for it in news_items
        )
    else:
        news_context = f"- 뉴스 수집 실패: {news_err or '알 수 없음'}"

    # ── 섹션 B: 확정 이벤트 캘린더 ──
    upcoming = get_upcoming_fixed_events(days_ahead=45)
    if upcoming:
        fixed_events_text = "\n".join(
            f"- [D-{ev['days_left']}] {ev['name']} ({ev['scale']})\n  {ev['note']}"
            for ev in upcoming
        )
    else:
        fixed_events_text = "- 향후 45일 이내 주요 확정 이벤트 없음."

    # ── 섹션 C: 코드 판단 (Gemini가 수정 금지) ──
    print("📊 매크로 데이터 로딩 중...")
    cnn_score, cnn_rating, _ = get_real_cnn_fg()
    charts = get_macro_charts() or {}

    code_judgment_parts = [
        f"[생성 시각] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}",
        f"[CNN F&G]   {cnn_score} / 100 ({cnn_rating})",
        "",
    ]

    # 미국 바닥 탐지
    us_score, us_verdict, us_details, us_phase = (0, "데이터 없음", [], "알 수 없음")
    us_risk_grade, _, us_risk_alerts, us_danger = ("N/A", "#aaa", [], 0)

    spy  = charts.get("SPY",  None)
    vix  = charts.get("^VIX", None)
    vix3m = charts.get("^VIX3M", None)
    hyg  = charts.get("HYG", None)
    ief  = charts.get("IEF", None)
    rsp  = charts.get("RSP", None)

    if spy is not None and vix is not None:
        us_score, us_verdict, us_details, us_phase = calculate_us_bottom_finder(spy, vix, cnn_score)
        print(f"🇺🇸 미국 바닥 점수: {us_score}점 ({us_phase})")

    if all(v is not None for v in [vix, vix3m, hyg, ief, spy]):
        us_risk_grade, _, us_risk_alerts, us_danger = calculate_us_risk_radar(vix, vix3m, hyg, ief, spy)

    us_strategy_headline, _, us_strategy_actions = get_strategic_advice(
        us_danger, us_score, us_verdict, us_phase
    )

    code_judgment_parts += [
        "─── 🇺🇸 미국 시장 판단 ───",
        f"위험 탐지기: {us_risk_grade}",
        f"바닥 탐지기: {us_score}점 / {us_verdict}",
        f"현재 국면: {us_phase}",
        f"전략 제언: {us_strategy_headline}",
        "  행동 지침:",
        *[f"  · {a}" for a in us_strategy_actions],
        "  바닥 탐지 근거:",
        *[f"  · {d}" for d in us_details],
        "",
    ]

    # 한국 바닥 탐지
    kr_score, kr_verdict, kr_details, kr_phase = (0, "데이터 없음", [], "알 수 없음")
    kr_risk_grade, _, kr_risk_alerts, kr_danger = ("N/A", "#aaa", [], 0)

    ks11    = charts.get("KS11",      None)
    vkospi  = charts.get("^VKOSPI",   None)
    usdkrw  = charts.get("USDKRW=X",  None)

    if ks11 is not None and vkospi is not None and usdkrw is not None:
        kr_score, kr_verdict, kr_details, kr_phase = calculate_kr_bottom_finder(ks11, vkospi, usdkrw)
        print(f"🇰🇷 한국 바닥 점수: {kr_score}점 ({kr_phase})")

    if ks11 is not None and vkospi is not None and usdkrw is not None:
        kr_risk_grade, _, kr_risk_alerts, kr_danger = calculate_kr_risk_radar(vkospi, usdkrw, ks11)

    kr_strategy_headline, _, kr_strategy_actions = get_strategic_advice(
        kr_danger, kr_score, kr_verdict, kr_phase
    )

    code_judgment_parts += [
        "─── 🇰🇷 한국 시장 판단 ───",
        f"위험 탐지기: {kr_risk_grade}",
        f"바닥 탐지기: {kr_score}점 / {kr_verdict}",
        f"현재 국면: {kr_phase}",
        f"전략 제언: {kr_strategy_headline}",
        "  행동 지침:",
        *[f"  · {a}" for a in kr_strategy_actions],
        "  바닥 탐지 근거:",
        *[f"  · {d}" for d in kr_details],
        "",
    ]

    # 핵심 타겟 종목 스캔
    print("🎯 핵심 타겟 종목 스캔 중...")
    signal_lines = []
    for name, is_kr in TARGET_STOCKS:
        try:
            d = get_stock_data(name, is_kr=is_kr, fast_mode=False)
            if d.get("error"):
                continue
            ai_sig = get_ai_signal(d)
            if any(t in ai_sig for t in TARGET_AI_SIGNALS):
                signal_lines.append(
                    f"· {name}: {ai_sig} | "
                    f"고점대비 {fmt(d.get('Gap_High'),'%')} | "
                    f"RSI {fmt(d.get('RSI_14'))} | "
                    f"PER {fmt(d.get('PER'))} | ROE {fmt(d.get('ROE'))}"
                )
        except Exception as e:
            print(f"⚠️ {name} 스캔 오류: {e}")

    code_judgment_parts.append("─── 핵심 타겟 종목 매수 시그널 ───")
    if signal_lines:
        code_judgment_parts += signal_lines
    else:
        code_judgment_parts.append("  · 현재 타겟 종목 중 매수 시그널 없음.")
    code_judgment_parts.append("")

    # ★ 수정 포인트 1: 텐배거 시그널 — is_tenbagger is True 버그 수정
    #   get_tenbagger_signal()은 True/False가 아닌 문자열을 반환함.
    #   기존 `is_tenbagger is True` → 항상 False라 조건을 영원히 통과 못했음.
    #   변경: 반환된 문자열이 유효한 시그널 세트에 포함되는지로 비교.
    print("🚀 텐배거 스캔 중...")
    tb_lines = []
    for theme, tickers in TENBAGGER_UNIVERSE.items():
        is_kr = "한국" in theme
        for tk in tickers:
            try:
                d = get_stock_data(tk, is_kr=is_kr, fast_mode=False)
                if d.get("error"):
                    continue
                tb_sig   = get_tenbagger_signal(d)       # 문자열 반환
                gap_high = d.get("Gap_High") or 0
                rsi      = d.get("RSI_14") or 100

                # ★ 수정: 문자열 포함 여부로 비교 (is True → in SET)
                if tb_sig in TENBAGGER_BUY_SIGNALS and (gap_high <= -20 or rsi <= 45):
                    tb_lines.append(
                        f"· {d.get('Name', tk)} ({theme})\n"
                        f"  등급: {tb_sig} | "
                        f"고점대비 {fmt(gap_high,'%')} | "
                        f"RSI {fmt(rsi)} | "
                        f"Rule of 40: {fmt(d.get('Rule_of_40'),'%')}"
                    )
            except Exception:
                pass

    code_judgment_parts.append("─── 텐배거 Must-Enter 기회 ───")
    if tb_lines:
        code_judgment_parts += tb_lines
    else:
        code_judgment_parts.append("  · 현재 진입 조건을 충족한 텐배거 후보 없음.")

    code_judgment = "\n".join(code_judgment_parts)

    # ── 최종 출력 ──
    print("\n[코드 판단 결과]")
    print(code_judgment)
    print("\n[확정 이벤트]")
    print(fixed_events_text)

    final_message = analyze_with_gemini(code_judgment, news_context, fixed_events_text)

    print("\n[전송할 텔레그램 메시지]")
    print(final_message)

    if token and chat_id:
        send_telegram_alert(token, chat_id, final_message)


if __name__ == "__main__":
    run_alert_logic()
