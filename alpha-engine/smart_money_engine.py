import os
import json
import time
from datetime import datetime
import pytz

DATA_DIR = "data"
OUTPUT_FILE = os.path.join(DATA_DIR, "smart_money_report.md")

def fetch_stock_data():
    """
    API나 스크래핑을 통해 코스피/코스닥 종목들의
    1. 최근 5거래일 주가 등락률
    2. 최근 5거래일 기관/외국인 누적 순매수 대금
    을 수집합니다.
    (주의: pykrx 차단 이슈로 인해, 실제 운영 환경에서는 증권사 API(한국투자증권 등) 연동을 권장합니다.)
    현재는 로직을 시뮬레이션하기 위한 Mock 데이터를 반환합니다.
    """
    # TODO: 증권사 API 또는 우회 크롤링 로직 연동
    return [
        {"종목명": "삼성전자", "등락률": -3.5, "외인순매수_억": 1500, "기관순매수_억": 500, "거래량증가율": 1.2, "20일선이격도": 98},
        {"종목명": "SK하이닉스", "등락률": 1.2, "외인순매수_억": -300, "기관순매수_억": 1200, "거래량증가율": 0.9, "20일선이격도": 102},
        {"종목명": "현대차", "등락률": -5.0, "외인순매수_억": 2000, "기관순매수_억": 800, "거래량증가율": 2.5, "20일선이격도": 95},
        {"종목명": "기아", "등락률": -4.2, "외인순매수_억": 1200, "기관순매수_억": -100, "거래량증가율": 1.5, "20일선이격도": 96},
        {"종목명": "NAVER", "등락률": 2.0, "외인순매수_억": -500, "기관순매수_억": -200, "거래량증가율": 0.8, "20일선이격도": 105},
        {"종목명": "카카오", "등락률": -7.0, "외인순매수_억": 800, "기관순매수_억": 600, "거래량증가율": 3.0, "20일선이격도": 92},
        {"종목명": "LG에너지솔루션", "등락률": -1.5, "외인순매수_억": 100, "기관순매수_억": 50, "거래량증가율": 1.0, "20일선이격도": 99},
        {"종목명": "POSCO홀딩스", "등락률": -6.5, "외인순매수_억": 3000, "기관순매수_억": 1500, "거래량증가율": 4.0, "20일선이격도": 90},
    ]

def calculate_divergence_score(stock):
    """
    수급 다이버전스 점수(Divergence Score) 산출 알고리즘
    주가는 크게 하락했는데, 세력(외인+기관)은 대규모 순매수한 종목일수록 높은 점수
    """
    price_change = stock["등락률"]
    net_buy = stock["외인순매수_억"] + stock["기관순매수_억"]
    vol_ratio = stock["거래량증가율"]
    ma_20_dist = stock["20일선이격도"]
    
    # 1. 기초 조건 필터링: 주가는 하락했는가? & 쌍끌이 매수 또는 대규모 매집이 있는가?
    if price_change >= 0 or net_buy <= 0:
        return 0
        
    # 2. 다이버전스 강도 계산 (하락폭이 클수록, 매수 금액이 클수록 점수 증가)
    # 예시 가중치 산식: (하락폭 절대값) * (순매수액 / 100) * 거래량 가중치
    base_score = abs(price_change) * (net_buy / 100.0)
    
    # 3. 거래량 터진 음봉 매집(손바뀜) 가중치 (거래량이 평소보다 늘었을 때 가산점)
    if vol_ratio > 1.5:
        base_score *= 1.5
        
    # 4. 이격도 과대낙폭 가중치 (20일선 기준 -5% 이상 하락 시 추가 점수)
    if ma_20_dist < 95:
        base_score *= 1.2
        
    return round(base_score, 2)

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    stocks = fetch_stock_data()
    scored_stocks = []
    
    for stock in stocks:
        score = calculate_divergence_score(stock)
        if score > 0:
            stock["Divergence_Score"] = score
            scored_stocks.append(stock)
            
    # 점수 높은 순으로 정렬 (Top 10)
    scored_stocks = sorted(scored_stocks, key=lambda x: x["Divergence_Score"], reverse=True)[:10]
    
    kst = pytz.timezone('Asia/Seoul')
    now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    
    # 마크다운 리포트 생성 (Obsidian 호환)
    report_lines = [
        f"# 🔥 세력 매집 다이버전스 리포트",
        f"**분석 일시:** {now_str}",
        "",
        "## 💡 다이버전스 (주가 하락 + 수급 유입) Top 종목",
        ""
    ]
    
    if not scored_stocks:
        report_lines.append("현재 다이버전스 조건에 부합하는 매집 종목이 발견되지 않았습니다.")
    else:
        report_lines.append("| 순위 | 종목명 | 다이버전스 점수 | 등락률(5일) | 외인순매수 | 기관순매수 | 20일선이격도 | 거래량증폭 |")
        report_lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        
        for idx, s in enumerate(scored_stocks, 1):
            report_lines.append(
                f"| {idx} | **{s['종목명']}** | **{s['Divergence_Score']}** | {s['등락률']}% | {s['외인순매수_억']}억 | {s['기관순매수_억']}억 | {s['20일선이격도']} | {s['거래량증가율']}x |"
            )
            
    report_lines.extend([
        "",
        "---",
        "### 🔍 교차 검증 코멘트 (AI CFO 로직)",
        "- 거래량이 1.5배 이상 폭증하며 하락한 종목은 강력한 손바뀜(매집) 패턴일 확률이 높습니다.",
        "- 단, 악재성 공시(유상증자, 배임 등)로 인한 하락은 피해야 하므로 최종 매수 전 개별 종목 뉴스를 반드시 확인하십시오."
    ])
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"Smart Money Report generated successfully at {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
