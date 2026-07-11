import os
import json
import time
import feedparser
from datetime import datetime
import pytz

# 검증된 미국 주요 경제/금융 매체 RSS 피드
# 검증된 미국 주요 매체 및 한국 매체 RSS 피드
RSS_FEEDS = {
    "WSJ_Business": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "WSJ_Markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "WSJ_World": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",  # 국제/전쟁/지정학
    "CNBC_Finance": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "CNBC_World": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362", # 국제/지정학
    "GoogleNews_Korea": "https://news.google.com/rss/search?q=%EA%B2%BD%EC%A0%9C+OR+%EA%B5%AD%EC%A0%9C+OR+%EC%A0%84%EC%9F%81+OR+%EC%9C%84%EA%B8%B0+OR+%EB%A6%AC%EC%8A%A4%ED%81%AC+OR+%EC%86%8D%EB%B3%B4&hl=ko&gl=KR&ceid=KR:ko", # 경제, 국제, 전쟁, 위기, 리스크, 속보
    "Maeil_Business": "https://www.mk.co.kr/rss/30000001/" # 매일경제 (경제 전문)
}

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "news_archive.json")
MAX_ARCHIVE_SIZE = 100  # 보관할 최대 기사 수

def get_gemini_classification(title, summary, source):
    """Gemini API를 활용해 뉴스의 거시경제/증시 파급력을 평가"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다. GitHub Secrets 또는 로컬 환경변수를 확인해주세요.")

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        prompt = f"""너는 월스트리트 헤지펀드의 시니어 매크로 애널리스트다.
다음은 {source}에서 발췌한 경제/금융/국제/전쟁 관련 속보의 제목과 요약이다.
이 기사가 주식 시장과 거시 경제(금리, 환율, 유동성, 지정학적 리스크 등)에 미칠 구조적 영향을 입체적으로 분석하라.
만약 기사가 영어라면 한국어로 완벽하게 번역해서 응답해야 한다.

반드시 유효한 JSON 형식으로만 응답하라.
{{
    "title_ko": "기사 제목의 자연스러운 한국어 번역 (이미 한국어라면 그대로 작성)",
    "sentiment": "호재" | "악재" | "중립",
    "importance": <1~5 사이의 정수. 전쟁 발발, 금리결정 등 매크로 충격은 4~5, 단순 기업 가십은 1~2>,
    "sectors": ["수혜/피해 예상 섹터명1", "섹터명2"],
    "keywords": ["핵심키워드1", "핵심키워드2"],
    "reason": "이 뉴스가 증시 및 매크로에 미칠 실질적 영향을 1~2줄로 명료하게 요약 (한국어)"
}}

제목: {title}
요약: {summary}
"""
        from google.genai import types
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        result = json.loads(text.strip())
        return result
    except Exception as e:
        print(f"Gemini API Error for '{title}': {e}")
        return {"sentiment": "N/A", "importance": 0, "sectors": [], "reason": f"Error: {e}", "keywords": []}

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                archive = json.load(f)
            except:
                archive = []
    else:
        archive = []

    existing_links = {item['link'] for item in archive}
    new_items = []
    
    for source_name, url in RSS_FEEDS.items():
        print(f"Fetching from {source_name}...")
        feed = feedparser.parse(url)
        # 각 피드당 최신 5개만 검사
        for entry in feed.entries[:5]:
            if entry.link in existing_links:
                continue
                
            title = entry.title
            summary = getattr(entry, 'summary', '')
            
            print(f"  -> Processing: {title}")
            
            # AI 분류 요청
            classification = get_gemini_classification(title, summary, source_name)
            
            # 중요도 2 미만(1 또는 0)의 파급력 없는 기사는 필터링
            importance = classification.get("importance", 0)
            if importance < 2:
                print(f"     (Skipped due to low importance: {importance})")
                continue
                
            kst = pytz.timezone('Asia/Seoul')
            now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
            
            news_obj = {
                "source": source_name,
                "title": title,
                "link": entry.link,
                "published": getattr(entry, 'published', now_str),
                "fetched_at": now_str,
                "sentiment": classification.get("sentiment", "N/A"),
                "importance": importance,
                "sectors": classification.get("sectors", []),
                "keywords": classification.get("keywords", []),
                "reason": classification.get("reason", "")
            }
            new_items.append(news_obj)
            
            # API 제한 방지를 위한 짧은 대기
            time.sleep(1.5)

    if new_items:
        # 새로 수집된 기사가 위로 오도록 추가
        archive = new_items + archive
        archive = archive[:MAX_ARCHIVE_SIZE]
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        print(f"Added {len(new_items)} new critical articles to the archive.")
    else:
        print("No new critical articles to add.")

if __name__ == "__main__":
    main()
