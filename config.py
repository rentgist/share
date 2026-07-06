import datetime

# ─────────────────────────────────────────
# 한글 이름 → 티커 매핑
# ─────────────────────────────────────────
US_NAME_MAP = {
    "애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "구글": "GOOGL", "알파벳": "GOOGL",
    "아마존": "AMZN", "메타": "META", "테슬라": "TSLA", "브로드컴": "AVGO", "이튼": "ETN",
    "버티브": "VRT", "스타벅스": "SBUX", "넷플릭스": "NFLX", "팔란티어": "PLTR",
    "일라이릴리": "LLY", "코카콜라": "KO", "AMD": "AMD", "퀄컴": "QCOM", "인텔": "INTC", "TSMC": "TSM",
    "아이온큐": "IONQ", "소파이": "SOFI", "크라우드스트라이크": "CRWD", "스노우플레이크": "SNOW",
    "암": "ARM", "ARM": "ARM", "슈퍼마이크로": "SMCI", "슈마컴": "SMCI",
    "웨스턴디지털": "WDC", "샌디스크": "SNDK"
}

def get_kst_now():
    """타임존 통일: 한국 시간(KST) 반환"""
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)
