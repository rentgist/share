import os
import json
import requests
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import pytz
import time
import math

KST = pytz.timezone("Asia/Seoul")
DATA_DIR    = "data"
REPORT_FILE = os.path.join(DATA_DIR, "smart_money_report.md")
TOP_N       = 10

def _get_dynamic_watchlist(top_n=30) -> list:
    """
    KOSDAQ 시가총액 500억 ~ 5000억 사이의 중소형주 중
    당일 거래량 상위 종목을 추출하여 타겟 유니버스로 설정합니다.
    작전 세력이 개입하기 좋은 타겟입니다.
    """
    print("  [유니버스 생성] KOSDAQ 중소형주 스캔 중...")
    try:
        df = fdr.StockListing('KOSDAQ')
        # 시총(Marcap) 500억 ~ 5000억 (50,000,000,000 ~ 500,000,000,000)
        df['Marcap'] = pd.to_numeric(df['Marcap'], errors='coerce')
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
        
        filtered = df[(df['Marcap'] >= 50000000000) & (df['Marcap'] <= 500000000000)]
        # 거래량 기준 정렬하여 시장의 관심을 받는 종목 추출
        filtered = filtered.sort_values('Volume', ascending=False).head(top_n)
        
        watchlist = []
        for _, row in filtered.iterrows():
            watchlist.append({"name": row['Name'], "code": str(row['Code']).zfill(6)})
        return watchlist
    except Exception as e:
        print(f"  [유니버스 생성 실패] {e}")
        return []

def _fetch_naver_investor_flow(code: str, days: int = 5) -> dict:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        }
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "euc-kr"

        tables = pd.read_html(resp.text)
        for tbl in tables:
            cols = [str(c) for c in tbl.columns]
            has_frgn = any("외국인" in c or "외인" in c for c in cols)
            has_inst = any("기관" in c for c in cols)
            if has_frgn or has_inst:
                tbl = tbl.dropna(how="all").head(days)
                frgn_col = next((c for c in cols if "외국인" in c or "외인" in c), None)
                inst_col = next((c for c in cols if "기관" in c), None)

                def to_억(series):
                    try:
                        cleaned = series.astype(str).str.replace(",", "").str.replace("+", "").str.strip()
                        nums = pd.to_numeric(cleaned, errors="coerce").dropna()
                        return round(float(nums.sum()) / 100, 1) # 백만원 단위 -> 억원
                    except:
                        return 0.0

                return {
                    "외인순매수_억": to_억(tbl[frgn_col]) if frgn_col else 0.0,
                    "기관순매수_억": to_억(tbl[inst_col]) if inst_col else 0.0,
                }
        return None
    except:
        return None

def _analyze_stealth_accumulation(code: str) -> dict | None:
    try:
        end   = datetime.now(KST).strftime("%Y-%m-%d")
        start = (datetime.now(KST) - timedelta(days=40)).strftime("%Y-%m-%d")
        df = fdr.DataReader(code, start=start, end=end)
        if df is None or len(df) < 25:
            return None

        df = df.sort_index()
        close = df["Close"]
        vol = df["Volume"]

        change_5d = round((close.iloc[-1] / close.iloc[-6] - 1) * 100, 2) if len(close) >= 6 else 0.0
        
        # 최근 5일간 매집봉(거래량 폭증 + 윗꼬리) 탐지
        has_volume_spike = False
        has_upper_wick = False
        
        for i in range(-5, 0):
            if len(df) + i < 20: continue
            
            # 20일 평균 거래량
            ma20_vol = vol.iloc[i-20:i].mean()
            if ma20_vol == 0: continue
            
            daily_vol = vol.iloc[i]
            if daily_vol >= ma20_vol * 2.5: # 2.5배 이상 폭증
                has_volume_spike = True
                
                # 윗꼬리 계산: (고가 - max(시가, 종가)) / (고가 - 저가)
                high = df["High"].iloc[i]
                low = df["Low"].iloc[i]
                open_p = df["Open"].iloc[i]
                close_p = df["Close"].iloc[i]
                
                body_top = max(open_p, close_p)
                wick_len = high - body_top
                total_len = high - low
                
                if total_len > 0 and (wick_len / total_len) >= 0.4: # 윗꼬리가 전체의 40% 이상
                    has_upper_wick = True

        return {
            "등락률_5일": change_5d,
            "매집봉발생": has_volume_spike,
            "윗꼬리발생": has_upper_wick,
        }
    except:
        return None

def calculate_speculative_score(price_data: dict, flow_data: dict | None) -> float:
    change_5d = price_data.get("등락률_5일", 0)
    has_spike = price_data.get("매집봉발생", False)
    has_wick  = price_data.get("윗꼬리발생", False)

    # 1. 횡보 및 하락 범위 완화 (-12% ~ +15%)
    # 매집봉 당일 급등을 고려하여 상한선을 +15%로 상향 조정합니다.
    if not (-12.0 <= change_5d <= 15.0):
        return 0.0

    # 2. 기술적 매집 패턴 점수 (가장 직관적인 세력의 거래량/캔들 흔적)
    tech_score = 0.0
    if has_spike:
        tech_score += 15.0
    if has_wick:
        tech_score += 10.0

    # 3. 메이저 수급 확인 (외인+기관)
    flow_score = 0.0
    if flow_data:
        net_buy = flow_data.get("외인순매수_억", 0) + flow_data.get("기관순매수_억", 0)
        if net_buy > 0:
            # 수급 유입 시 가산점
            flow_score = net_buy * 1.5
        else:
            # 수급이 음수(매도)이더라도 기술적 매집 패턴(매집봉+윗꼬리)이 동시에 떴다면
            # 차명계좌(개인 창구)를 통한 세력 개입 가능성을 열어두고 통과시킵니다. (약간의 감점 적용)
            if has_spike and has_wick:
                flow_score = -2.0
            else:
                # 매집 패턴도 없는데 메이저 수급도 매도세라면 탈락
                return 0.0

    total_score = tech_score + flow_score
    return round(max(total_score, 0.0), 2)

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🔍 스나이퍼(작전/세력) 탐지기 실행: {now_str}\n")

    watchlist = _get_dynamic_watchlist(top_n=30)
    if not watchlist:
        print("  [에러] 타겟 종목을 추출하지 못했습니다.")
        return

    results = []
    for stock in watchlist:
        name = stock["name"]
        code = stock["code"]
        print(f"  [{name} ({code})] 탐지 중...")

        price_data = _analyze_stealth_accumulation(code)
        if not price_data:
            continue

        flow_data = _fetch_naver_investor_flow(code, days=5)
        score = calculate_speculative_score(price_data, flow_data)

        if score > 0:
            results.append({
                "종목명": name,
                "코드": code,
                "다이버전스점수": score,
                "등락률_5일": price_data["등락률_5일"],
                "외인순매수_억": flow_data["외인순매수_억"] if flow_data else 0,
                "기관순매수_억": flow_data["기관순매수_억"] if flow_data else 0,
                "매집봉": "🚨포착" if price_data["매집봉발생"] else "-",
                "윗꼬리": "🚨포착" if price_data["윗꼬리발생"] else "-",
            })
            print(f"    ✅ 세력 매집 시그널 포착! (점수: {score})")
        
        time.sleep(0.3)

    results.sort(key=lambda x: x["다이버전스점수"], reverse=True)
    top_results = results[:TOP_N]

    lines = [
        f"# 🔥 코스닥 스나이퍼: 작전 세력 매집 탐지 리포트",
        f"",
        f"> **타겟:** 시가총액 500억~5,000억 사이의 코스닥 중소형주",
        f"> **로직:** 주가 횡보 구간에서 발생하는 수상한 수급(외인/기관 위장 사모펀드)과 윗꼬리 매집봉(Volume Spike)을 추적합니다.",
        f"> 데이터 기준: 최근 5영업일 / 분석 일시: {now_str} (KST)",
        f"",
    ]

    if not top_results:
        lines += [
            "## 📭 세력 매집 감지 종목 없음",
            "",
            "현재 코스닥 중소형주 타겟 그룹에서 뚜렷한 매집봉과 기관/외인 동반 매집 패턴이 감지된 종목이 없습니다.",
            "*pykrx(거래소 API) 차단으로 인해 네이버 금융 데이터를 기반으로 산출되었습니다.*",
        ]
    else:
        lines += [
            f"## 💡 세력 매집 Top {len(top_results)} 종목",
            "",
            "| 순위 | 종목명 | 스나이퍼점수 | 5일등락 | 외인순매수(억) | 기관순매수(억) | 거래량폭증 | 윗꼬리(물량뺏기) |",
            "|------|--------|-------------|---------|--------------|--------------|----------|----------------|",
        ]
        for i, r in enumerate(top_results, 1):
            lines.append(
                f"| {i} | {r['종목명']} | **{r['다이버전스점수']}** "
                f"| {r['등락률_5일']:+.1f}% "
                f"| {r['외인순매수_억']:+.1f} "
                f"| {r['기관순매수_억']:+.1f} "
                f"| {r['매집봉']} "
                f"| {r['윗꼬리']} |"
            )

        lines += [
            "",
            "---",
            "",
            "## 🔎 스나이퍼 로직 & 해석 가이드",
            "",
            "- **타겟:** KOSDAQ 시가총액 500억~5000억 사이 거래량 급증 종목 30개 동적 스캔.",
            "- **점수:** `순매수(억) × 매집봉 발생(2배) × 윗꼬리 발생(1.5배)`",
            "- **매집봉(거래량폭증):** 최근 5일 내에 20일 평균 대비 거래량이 2.5배 이상 폭증한 날이 존재함.",
            "- **윗꼬리(물량뺏기):** 매집봉 발생 당일, 캔들의 윗꼬리가 전체의 40% 이상을 차지함. (세력이 고가에서 개인 물량을 뺏은 전형적 패턴)",
            "- **수급 주체:** 중소형주의 경우 '기관/외국인' 창구를 통해 사모펀드나 기타 세력 자금이 위장 진입하는 경우가 많습니다.",
            "- **⚠ 주의:** 재무가 극히 부실한 '환기종목'이거나 전환사채(CB) 폭탄이 있는 종목은 제외하고 보셔야 합니다.",
        ]

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n📄 리포트 저장 완료: {REPORT_FILE}")

if __name__ == "__main__":
    main()
