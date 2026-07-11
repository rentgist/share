import os
import json
import time
import feedparser
from datetime import datetime, timezone, timedelta
import pytz

# 검증된 미국 주요 매체 및 한국 매체 RSS 피드
RSS_FEEDS = {
    "WSJ_Business": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "WSJ_Markets":  "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "WSJ_World":    "https://feeds.a.dj.com/rss/RSSWorldNews.xml",       # 국제/전쟁/지정학
    "CNBC_Finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "CNBC_World":   "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362",
    "GoogleNews_Korea": (
        "https://news.google.com/rss/search?q=%EA%B2%BD%EC%A0%9C+OR+%EA%B5%AD%EC%A0%9C"
        "+OR+%EC%A0%84%EC%9F%81+OR+%EC%9C%84%EA%B8%B0+OR+%EB%A6%AC%EC%8A%A4%ED%81%AC"
        "+OR+%EC%86%8D%EB%B3%B4&hl=ko&gl=KR&ceid=KR:ko"
    ),
    "Maeil_Business": "https://www.mk.co.kr/rss/30000001/",              # 매일경제 경제 전문
}

DATA_DIR  = "data"
DATA_FILE = os.path.join(DATA_DIR, "news_archive.json")
MAX_ARCHIVE_SIZE  = 120   # 보관할 최대 기사 수
STALE_HOURS       = 72    # 이 시간(시간)보다 오래된 기사는 스킵
ENTRIES_PER_FEED  = 8     # 각 피드당 최신 몇 개까지 검사할지

KST = pytz.timezone("Asia/Seoul")


def _is_stale(entry) -> bool:
    """published 날짜가 STALE_HOURS 이상 오래됐으면 True"""
    raw = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if raw is None:
        return False  # 날짜 정보 없으면 일단 처리
    try:
        pub_dt = datetime(*raw[:6], tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
        return age_hours > STALE_HOURS
    except Exception:
        return False


def get_gemini_classification(title: str, summary: str, source: str) -> dict:
    """Gemini API로 뉴스의 거시경제/증시 파급력 평가 + 한국어 번역"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = f"""너는 대한민국 자산가를 위한 월스트리트 수준의 시니어 매크로 애널리스트다.
다음은 {source}에서 발췌한 속보의 제목과 요약이다.

[분석 기준]
- 이 기사가 주식, 금리, 환율, 원자재, 부동산, 지정학 등 투자 자산에 미칠 실질적 영향을 분석하라.
- 영어 기사라면 title_ko에 자연스러운 한국어 번역을 작성하라. 이미 한국어면 그대로 작성.
- action_point는 "이 기사를 본 투자자가 당장 무엇을 해야 하는가?" 1문장으로 핵심 액션만 적어라.
  예: "반도체 섹터 비중 축소 검토", "달러 자산 보유 유지", "국내 금리 민감주 주시"
  막연한 표현("모니터링 지속", "주의 필요") 금지. 실제로 대장님의 포트폴리오에 영향이 없으면 "해당 없음"이라고 적어라.

반드시 유효한 JSON 형식으로만 응답하라.
{{
    "title_ko": "한국어 번역 제목",
    "sentiment": "호재" | "악재" | "중립",
    "importance": <1~5 정수. 금리결정/전쟁발발/무역전쟁 등 글로벌 쇼크=5, 주요국 경제지표=4, 개별기업 대형이슈=3, 섹터이슈=2, 단순가십=1>,
    "sectors": ["영향 섹터1", "영향 섹터2"],
    "keywords": ["핵심 키워드1", "키워드2"],
    "reason": "이 뉴스가 시장/매크로에 미칠 영향을 1~2줄 명료하게 (한국어)",
    "action_point": "투자자 액션 1문장 (한국어)"
}}

제목: {title}
요약: {summary}
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        text = response.text.strip()
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

    except json.JSONDecodeError as e:
        print(f"  [JSON 파싱 오류] {title}: {e}")
        return {"title_ko": title, "sentiment": "N/A", "importance": 0, "sectors": [], "reason": "", "keywords": [], "action_point": ""}
    except Exception as e:
        print(f"  [Gemini API 오류] {title}: {e}")
        return {"title_ko": title, "sentiment": "N/A", "importance": 0, "sectors": [], "reason": f"Error: {e}", "keywords": [], "action_point": ""}


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    # 기존 아카이브 로드
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                archive = json.load(f)
        except (json.JSONDecodeError, ValueError):
            archive = []
    else:
        archive = []

    existing_links = {item.get("link", "") for item in archive}
    new_items = []

    for source_name, url in RSS_FEEDS.items():
        print(f"\n📡 [{source_name}] 수집 중...")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"  피드 파싱 실패: {e}")
            continue

        for entry in feed.entries[:ENTRIES_PER_FEED]:
            link = getattr(entry, "link", None)
            if not link or link in existing_links:
                continue

            # 오래된 기사 스킵
            if _is_stale(entry):
                print(f"  [스킵-오래된 기사] {getattr(entry, 'title', '')[:60]}")
                continue

            title   = getattr(entry, "title", "제목 없음")
            summary = getattr(entry, "summary", "")

            print(f"  → 분석 중: {title[:70]}")

            classification = get_gemini_classification(title, summary, source_name)

            importance = classification.get("importance", 0)
            if importance < 2:
                print(f"     (중요도 {importance} → 필터링)")
                continue

            now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

            news_obj = {
                "source":       source_name,
                "title":        title,
                "title_ko":     classification.get("title_ko", title),   # ← 한국어 번역 저장
                "link":         link,
                "published":    getattr(entry, "published", now_str),
                "fetched_at":   now_str,
                "sentiment":    classification.get("sentiment", "중립"),
                "importance":   importance,
                "sectors":      classification.get("sectors", []),
                "keywords":     classification.get("keywords", []),
                "reason":       classification.get("reason", ""),
                "action_point": classification.get("action_point", ""),  # ← 투자자 액션 저장
            }
            new_items.append(news_obj)
            existing_links.add(link)

            time.sleep(1.5)  # API 레이트 리밋 방어

    if new_items:
        # 중요도 높은 기사가 맨 위로
        new_items.sort(key=lambda x: x.get("importance", 0), reverse=True)
        archive = new_items + archive
        archive = archive[:MAX_ARCHIVE_SIZE]

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 새 기사 {len(new_items)}건 저장 완료.")
    else:
        print("\n✅ 신규 기사 없음.")


if __name__ == "__main__":
    main()
