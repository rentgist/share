import os
import pandas as pd
import datetime
import yfinance as yf
import concurrent.futures
import json
import re

CALENDAR_FILE = "market_calendar.csv"

# 공식 발표 일정으로 확인한 고중요도 거시 이벤트입니다. 뉴스 제목을 파싱해
# 날짜를 추정하지 않고, 일정이 확정된 뒤에만 이 목록을 갱신합니다.
CORE_MACRO_EVENTS_2026 = [
    ("2026-08-12", "물가·금리", "미국 7월 CPI 발표 (21:30 KST)", "High",
     "물가 상회 시 장기금리와 기술주 할인율 부담 확대. 둔화 시 신규진입 여건 개선."),
    ("2026-08-13", "물가·금리", "미국 7월 PPI 발표 (21:30 KST)", "High",
     "기업 비용의 물가 압력을 확인. CPI와 같은 방향이면 금리 반응이 커질 수 있음."),
    ("2026-08-14", "경기·고용", "미국 7월 소매판매 발표 (21:30 KST)", "High",
     "소비·경기 지속성 확인. 고물가와 소비 둔화의 동시 발생은 위험 신호."),
    ("2026-08-14", "경기·고용", "미시간대 8월 소비심리 잠정치 (23:00 KST)", "Medium",
     "기대인플레이션 급등 여부를 점검. 장기금리 민감 구간에서는 중요도가 높아짐."),
    ("2026-08-19", "연준", "7월 FOMC 의사록 공개 (03:00 KST, 8/20)", "High",
     "연준 내부의 물가·유동성 인식 확인. 매파적이면 기술주 비중 확대를 보류."),
    ("2026-08-26", "물가·금리", "미국 7월 PCE·개인소득 발표 (21:30 KST)", "High",
     "연준 선호 물가 지표. 핵심 PCE의 방향이 금리 경로 판단에 직접 연결됨."),
    ("2026-08-26", "경기·고용", "미국 2분기 GDP 수정치 발표 (21:30 KST)", "High",
     "성장과 물가를 함께 해석. 성장 둔화와 물가 재상승 조합은 가장 불리."),
    ("2026-08-27", "연준", "잭슨홀 경제정책 심포지엄 시작", "High",
     "8/27~29 연준 인사 발언에 따른 장기금리 변동성 경계. 갭 상승 추격 금지."),
    ("2026-09-04", "경기·고용", "미국 8월 고용보고서 발표 (21:30 KST)", "High",
     "고용·임금이 9월 연준 판단에 미치는 핵심 입력값."),
    ("2026-09-11", "물가·금리", "미국 8월 CPI 발표 (21:30 KST)", "High",
     "9월 FOMC 직전의 핵심 물가 확인. 예상치 대비 방향을 우선 해석."),
    ("2026-09-15", "연준", "9월 FOMC 회의 시작", "High",
     "9/15~16 회의 및 점도표. 정책금리·유동성 경로 재평가 구간."),
]

# 대표 글로벌/국내 빅테크 티커
MAJOR_TICKERS = {
    "ASML": "ASML",
    "NVDA": "NVDA",
    "MSFT": "MSFT",
    "AAPL": "AAPL",
    "META": "META",
    "TSMC": "TSM",
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS"
}

def load_calendar():
    if not os.path.exists(CALENDAR_FILE):
        df = pd.DataFrame(columns=["Date", "Type", "Event", "Impact", "Notes"])
        df.to_csv(CALENDAR_FILE, index=False, encoding="utf-8-sig")
        return df
    
    df = pd.read_csv(CALENDAR_FILE, encoding="utf-8-sig")
    # [BUG FIX] Convert 'Date' string to datetime.date to prevent StreamlitAPIException
    if not df.empty and 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df = df.sort_values(by="Date", na_position="last").reset_index(drop=True)
    return df

def save_calendar(df):
    # Ensure dates are strings for saving
    df_save = df.copy()
    if not df_save.empty and 'Date' in df_save.columns:
        df_save['Date'] = pd.to_datetime(df_save['Date']).dt.strftime('%Y-%m-%d')
    df_save.to_csv(CALENDAR_FILE, index=False, encoding="utf-8-sig")


def sync_core_macro_events():
    """확정된 핵심 거시 일정만 추가·갱신한다.

    수동으로 입력한 다른 이벤트는 보존하고, 동일 이벤트만 최신 설명으로 교체한다.
    """
    df = load_calendar()
    core_df = pd.DataFrame(
        CORE_MACRO_EVENTS_2026,
        columns=["Date", "Type", "Event", "Impact", "Notes"],
    )
    core_df["Date"] = pd.to_datetime(core_df["Date"]).dt.date

    if df.empty:
        merged = core_df
    else:
        # 이벤트명이 동일한 행만 대체해 수동 일정과 실적 일정을 보존한다.
        merged = df[~df["Event"].isin(core_df["Event"])].copy()
        merged = pd.concat([merged, core_df], ignore_index=True)

    merged = merged.sort_values(by=["Date", "Impact", "Event"]).reset_index(drop=True)
    save_calendar(merged)
    return len(core_df)

def fetch_single_earnings(name, ticker):
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal and 'Earnings Date' in cal and cal['Earnings Date']:
            earning_date = cal['Earnings Date'][0].strftime("%Y-%m-%d")
            return {"Date": earning_date, "Type": "실적", "Event": f"{name} 실적발표", "Impact": "High", "Notes": "자동 업데이트됨"}
    except Exception as e:
        print(f"Error fetching {name}: {e}")
    return None

def update_earnings_automatically():
    df = load_calendar()
    new_events = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_single_earnings, name, ticker): name for name, ticker in MAJOR_TICKERS.items()}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                # convert string date to python date
                res['Date'] = datetime.datetime.strptime(res['Date'], "%Y-%m-%d").date()
                new_events.append(res)
                
    if not new_events:
        return False
        
    new_df = pd.DataFrame(new_events)
    
    if not df.empty:
        for name in MAJOR_TICKERS.keys():
            df = df[~(df['Event'] == f"{name} 실적발표")]
        df = pd.concat([df, new_df], ignore_index=True)
    else:
        df = new_df
        
    df = df.sort_values(by="Date").reset_index(drop=True)
    save_calendar(df)
    return True

def update_macro_events_automatically():
    news_file = os.path.join("data", "news_archive.json")
    if not os.path.exists(news_file):
        return False
        
    try:
        with open(news_file, "r", encoding="utf-8") as f:
            news_data = json.load(f)
    except Exception:
        return False
        
    keywords = ["FOMC", "금통위", "금리 결정", "금리결정", "리밸런싱", "CPI", "PCE"]
    new_events = []
    current_year = datetime.datetime.now().year
    current_month = datetime.datetime.now().month
    
    for item in news_data:
        title = item.get("title_ko", item.get("title", ""))
        title_upper = title.upper()
        
        matched_kw = None
        for kw in keywords:
            if kw.upper() in title_upper:
                matched_kw = kw
                break
                
        if matched_kw:
            # Try to find "X월 Y일"
            match_full = re.search(r"(\d{1,2})월\s*(\d{1,2})일", title)
            if match_full:
                month = int(match_full.group(1))
                day = int(match_full.group(2))
                try:
                    event_date = datetime.date(current_year, month, day)
                    new_events.append({
                        "Date": event_date,
                        "Type": "매크로",
                        "Event": f"{matched_kw} ({title[:15]}...)",
                        "Impact": "High",
                        "Notes": "뉴스 스크래핑 자동 추가"
                    })
                    continue
                except ValueError:
                    pass
            
            # Try to find "오는 X일" or "X일"
            match_day = re.search(r"(\d{1,2})일", title)
            if match_day:
                day = int(match_day.group(1))
                try:
                    event_date = datetime.date(current_year, current_month, day)
                    # If date is in the past compared to today, it might be next month
                    if event_date < datetime.date.today() - datetime.timedelta(days=15):
                        next_month = current_month + 1 if current_month < 12 else 1
                        next_year = current_year if current_month < 12 else current_year + 1
                        event_date = datetime.date(next_year, next_month, day)
                        
                    new_events.append({
                        "Date": event_date,
                        "Type": "매크로",
                        "Event": f"{matched_kw} 일정",
                        "Impact": "High",
                        "Notes": "뉴스 스크래핑 자동 추가"
                    })
                except ValueError:
                    pass

    if not new_events:
        return False
        
    # Dedup
    df_new = pd.DataFrame(new_events)
    df_new = df_new.drop_duplicates(subset=["Date", "Event"])
    
    df = load_calendar()
    if not df.empty:
        # Avoid exact duplicates
        for _, row in df_new.iterrows():
            if not ((df['Date'] == row['Date']) & (df['Event'] == row['Event'])).any():
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = df_new
        
    df = df.sort_values(by="Date").reset_index(drop=True)
    save_calendar(df)
    return True

def get_upcoming_events_string():
    try:
        df = load_calendar()
        if df.empty:
            return "예정된 주요 일정이 없습니다."
            
        today = pd.Timestamp.now().normalize().date()
        
        # Filter for recent 2 days to future 14 days
        start_date = today - datetime.timedelta(days=2)
        end_date = today + datetime.timedelta(days=14)
        
        mask = (df['Date'] >= start_date) & (df['Date'] <= end_date)
        upcoming = df[mask].sort_values(by="Date")
        
        if upcoming.empty:
            return "향후 14일 내 예정된 주요 일정이 없습니다."
            
        events_str = "[🔥 최근 및 주간 주요 마켓 일정 (프롬프트 반영용)]\n"
        for _, row in upcoming.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d')
            typ = row['Type']
            evt = row['Event']
            notes = row['Notes']
            events_str += f"- {date_str} [{typ}] {evt} : {notes}\n"
            
        return events_str
    except Exception as e:
        return f"일정 로드 에러: {e}"
