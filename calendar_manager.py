import os
import pandas as pd
import datetime
import yfinance as yf
import concurrent.futures
import json
import re

CALENDAR_FILE = "market_calendar.csv"

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
    return df

def save_calendar(df):
    # Ensure dates are strings for saving
    df_save = df.copy()
    if not df_save.empty and 'Date' in df_save.columns:
        df_save['Date'] = pd.to_datetime(df_save['Date']).dt.strftime('%Y-%m-%d')
    df_save.to_csv(CALENDAR_FILE, index=False, encoding="utf-8-sig")

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
