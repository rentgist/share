"""
smart_money_engine.py
─────────────────────
세력(외인/기관) 매집 다이버전스 탐지기
- 주가 하락 중에 외인+기관이 공격적으로 순매수하는 종목을 발굴
- 데이터 소스: FinanceDataReader (주가/거래량) + Naver Finance JSON API (외인/기관 수급)
- 수급 데이터를 못 가져오면 거래량 이상 신호만으로 부분 점수 산출 (graceful degradation)
"""

import os
import json
import requests
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import pytz
import time

KST = pytz.timezone("Asia/Seoul")
DATA_DIR    = "data"
REPORT_FILE = os.path.join(DATA_DIR, "smart_money_report.md")
TOP_N       = 10

# ─── 추적 대상 종목 ───────────────────────────────────────────────
WATCHLIST = [
    {"name": "삼성전자",       "code": "005930"},
    {"name": "SK하이닉스",     "code": "000660"},
    {"name": "POSCO홀딩스",   "code": "005490"},
    {"name": "현대차",         "code": "005380"},
    {"name": "카카오",         "code": "035720"},
    {"name": "LG에너지솔루션", "code": "373220"},
    {"name": "기아",           "code": "000270"},
    {"name": "NAVER",          "code": "035420"},
    {"name": "삼성바이오로직스","code": "207940"},
    {"name": "셀트리온",       "code": "068270"},
    {"name": "현대모비스",     "code": "012330"},
    {"name": "KB금융",         "code": "105560"},
    {"name": "신한지주",       "code": "055550"},
    {"name": "LG화학",         "code": "051910"},
    {"name": "삼성SDI",        "code": "006400"},
]

# ─── Naver Finance 수급 API ──────────────────────────────────────
NAVER_FRGN_URL = "https://finance.naver.com/item/frgn.naver"

def _fetch_naver_investor_flow(code: str, days: int = 10) -> dict:
    """
    Naver Finance에서 외인/기관 순매수 데이터를 가져온다.
    반환: {"외인순매수_억": float, "기관순매수_억": float}
    실패 시 None 반환
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Referer": f"https://finance.naver.com/item/main.naver?code={code}",
        }
        # Naver 외인/기관 거래 내역 페이지 (HTML 파싱)
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "euc-kr"

        tables = pd.read_html(resp.text)
        # 보통 두 번째 테이블이 일별 외인/기관 순매수
        for tbl in tables:
            cols = [str(c) for c in tbl.columns]
            # 컬럼명에 '외국인' 또는 '기관' 포함 여부 확인
            has_frgn = any("외국인" in c or "외인" in c for c in cols)
            has_inst = any("기관" in c for c in cols)
            if has_frgn or has_inst:
                tbl = tbl.dropna(how="all").head(days)
                frgn_col = next((c for c in cols if "외국인" in c or "외인" in c), None)
                inst_col = next((c for c in cols if "기관" in c), None)

                def to_억(series):
                    try:
                        cleaned = (
                            series.astype(str)
                            .str.replace(",", "")
                            .str.replace("+", "")
                            .str.strip()
                        )
                        nums = pd.to_numeric(cleaned, errors="coerce").dropna()
                        # Naver는 백만원 단위 → 억원 변환
                        return round(float(nums.sum()) / 100, 1)
                    except Exception:
                        return 0.0

                return {
                    "외인순매수_억": to_억(tbl[frgn_col]) if frgn_col else 0.0,
                    "기관순매수_억": to_억(tbl[inst_col]) if inst_col else 0.0,
                }
        return None
    except Exception as e:
        print(f"  [수급 API 실패] {code}: {e}")
        return None


# ─── 주가/거래량 데이터 ──────────────────────────────────────────
def _fetch_price_data(code: str) -> dict | None:
    """
    FinanceDataReader로 30일 주가/거래량 데이터를 가져온다.
    반환: {등락률_5일, 거래량증가율, 20일선이격도}
    """
    try:
        end   = datetime.now(KST).strftime("%Y-%m-%d")
        start = (datetime.now(KST) - timedelta(days=60)).strftime("%Y-%m-%d")
        df = fdr.DataReader(code, start=start, end=end)
        if df is None or len(df) < 25:
            return None

        df = df.sort_index()
        close = df["Close"]

        # 5일 등락률
        change_5d = round((close.iloc[-1] / close.iloc[-6] - 1) * 100, 2) if len(close) >= 6 else 0.0

        # 20일 이동평균 이격도 (현재가/MA20 * 100)
        ma20 = close.rolling(20).mean().iloc[-1]
        ma20_dist = round((close.iloc[-1] / ma20) * 100, 1) if ma20 > 0 else 100.0

        # 거래량 증가율 (최근 5일 평균 / 직전 25일 평균)
        vol = df["Volume"] if "Volume" in df.columns else df.get("거래량", pd.Series())
        if len(vol) >= 30:
            recent_vol  = vol.iloc[-5:].mean()
            baseline_vol = vol.iloc[-30:-5].mean()
            vol_ratio = round(recent_vol / baseline_vol, 2) if baseline_vol > 0 else 1.0
        else:
            vol_ratio = 1.0

        return {
            "등락률_5일":  change_5d,
            "20일선이격도": ma20_dist,
            "거래량증가율": vol_ratio,
        }
    except Exception as e:
        print(f"  [주가 데이터 실패] {code}: {e}")
        return None


# ─── 다이버전스 점수 산출 ────────────────────────────────────────
def calculate_divergence_score(price_data: dict, flow_data: dict | None) -> float:
    """
    핵심 다이버전스 공식:
    - 주가 하락 중이면서 (change_5d < 0)
    - 외인+기관 순매수가 양수이면 (net_buy > 0)
    → 하락폭 × 순매수 규모 × 보너스 팩터

    수급 데이터 없는 경우: 거래량 이상 신호만으로 부분 점수
    """
    change_5d  = price_data.get("등락률_5일", 0)
    vol_ratio  = price_data.get("거래량증가율", 1.0)
    ma20_dist  = price_data.get("20일선이격도", 100)

    # 주가가 하락 중이어야 함
    if change_5d >= 0:
        return 0.0

    if flow_data:
        net_buy = flow_data.get("외인순매수_억", 0) + flow_data.get("기관순매수_억", 0)
        if net_buy <= 0:
            return 0.0

        # 기본 점수: 하락폭(절댓값) × 순매수 (단위: 억)
        # 정규화: 로그 스케일로 대형주 독점 방지
        import math
        log_net_buy = math.log1p(net_buy)           # 로그 스케일 (큰 값의 지배 완화)
        base_score  = abs(change_5d) * log_net_buy

        # 보너스: 거래량 급증 (강한 수급 확인)
        if vol_ratio >= 2.0:
            base_score *= 1.6
        elif vol_ratio >= 1.5:
            base_score *= 1.3

        # 보너스: 20일선 아래 (눌림목 매집)
        if ma20_dist < 97:
            base_score *= 1.2

        return round(base_score, 2)

    else:
        # 수급 데이터 없을 때: 거래량 이상 + 하락폭만으로 부분 점수
        if vol_ratio < 1.5:
            return 0.0
        partial = abs(change_5d) * (vol_ratio - 1.0) * 5
        return round(partial, 2)


# ─── 메인 ────────────────────────────────────────────────────────
def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🔍 스마트 머니 엔진 실행: {now_str}\n")

    results = []
    for stock in WATCHLIST:
        name = stock["name"]
        code = stock["code"]
        print(f"  [{name} ({code})] 데이터 수집 중...")

        price_data = _fetch_price_data(code)
        if not price_data:
            print(f"    ⚠ 주가 데이터 없음 — 스킵")
            continue

        flow_data = _fetch_naver_investor_flow(code, days=5)
        data_source = "주가+수급" if flow_data else "주가(수급 미수신)"

        score = calculate_divergence_score(price_data, flow_data)

        if score > 0:
            results.append({
                "종목명":     name,
                "코드":       code,
                "다이버전스점수": score,
                "등락률_5일": price_data.get("등락률_5일", 0),
                "외인순매수_억": flow_data.get("외인순매수_억", 0) if flow_data else "N/A",
                "기관순매수_억": flow_data.get("기관순매수_억", 0) if flow_data else "N/A",
                "20일선이격도": price_data.get("20일선이격도", 100),
                "거래량증가율": price_data.get("거래량증가율", 1.0),
                "데이터소스":  data_source,
            })
            print(f"    ✅ 다이버전스 {score}점 ({data_source})")
        else:
            print(f"    — 다이버전스 없음")

        time.sleep(0.5)  # Naver 요청 속도 제한

    # 점수 내림차순 정렬
    results.sort(key=lambda x: x["다이버전스점수"], reverse=True)
    top_results = results[:TOP_N]

    # ─── Markdown 리포트 생성 ────────────────────────────────────
    lines = [
        f"# 🔥 세력 매집 다이버전스 리포트",
        f"",
        f"> 주가는 하락 중이나 외인+기관이 공격적으로 매집 중인 **진짜 다이버전스** 종목 리스트입니다.",
        f"> 데이터 기준: 최근 5영업일 / 분석 일시: {now_str} (KST)",
        f"",
    ]

    if not top_results:
        lines += [
            "## 📭 다이버전스 감지 종목 없음",
            "",
            "현재 추적 중인 종목 중 '주가 하락 + 세력 매집' 패턴이 감지된 종목이 없습니다.",
            "시장이 전반적으로 상승 중이거나 수급 데이터 수신에 일시적 문제가 있을 수 있습니다.",
        ]
    else:
        lines += [
            f"## 💡 다이버전스 Top {len(top_results)} 종목",
            "",
            "| 순위 | 종목명 | 점수 | 5일등락 | 외인순매수(억) | 기관순매수(억) | 20일선이격 | 거래량증가 | 데이터 |",
            "|------|--------|------|---------|--------------|--------------|----------|----------|------|",
        ]
        for i, r in enumerate(top_results, 1):
            frgn = f"{r['외인순매수_억']:+.0f}" if isinstance(r["외인순매수_억"], (int, float)) else r["외인순매수_억"]
            inst = f"{r['기관순매수_억']:+.0f}" if isinstance(r["기관순매수_억"], (int, float)) else r["기관순매수_억"]
            lines.append(
                f"| {i} | {r['종목명']} | **{r['다이버전스점수']}** "
                f"| {r['등락률_5일']:+.1f}% "
                f"| {frgn} "
                f"| {inst} "
                f"| {r['20일선이격도']:.1f} "
                f"| {r['거래량증가율']:.1f}x "
                f"| {r['데이터소스']} |"
            )

        lines += [
            "",
            "---",
            "",
            "## 🔎 AI CFO 로직 & 해석 가이드",
            "",
            "- **다이버전스 점수** = `abs(5일등락률) × log(외인+기관 순매수) × 보너스팩터` (로그 스케일 정규화 적용)",
            "- 거래량이 평균 2배 이상 폭증 시 → 점수 ×1.6 (강력한 세력 개입 신호)",
            "- 20일선 아래(이격도 < 97) 매집 시 → 점수 ×1.2 (눌림목 저가 매집)",
            "- **⚠ 필수 교차검증**: 악재성 공시(유상증자/배임/소송 등) 여부는 반드시 확인 후 판단",
            "- **수급 미수신** 표시 종목: Naver 서버 일시 오류. 거래량 신호만으로 부분 계산된 결과임.",
        ]

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n📄 리포트 저장 완료: {REPORT_FILE}")
    print(f"   총 다이버전스 종목: {len(results)}개 → Top {len(top_results)}개 선정")


if __name__ == "__main__":
    main()
