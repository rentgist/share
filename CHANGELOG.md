# 퀀트 대시보드 & 텔레그램 봇 업데이트 내역 (CHANGELOG)

## [2026-07-08] 글로벌 매크로 & 수급 통합 AI 브리핑 연동 및 버그 픽스

### 1. 텔레그램 AI 알림 오류 해결 (`alert_bot.py`)
- **이슈**: 구글 뉴스 RSS에서 긁어온 뉴스 헤드라인에 '전쟁', '지정학' 등의 단어가 포함될 경우, Gemini의 유해 콘텐츠 필터(Safety Filter)가 작동하여 답변 생성을 차단하는 문제 발생 (`[AI 분석 오류]` 출력).
- **해결**: `alert_bot.py` 내 `genai.GenerativeModel.generate_content` 호출 시 `safety_settings` 옵션을 명시적으로 주입하여 필터링을 완전 해제. 이제 마켓 뉴스 키워드 검열 없이 안정적으로 AI 분석 브리핑이 제공됨.

### 2. 대시보드 [매크로 & 수급 AI 브리핑] 모듈 신규 구현 (`final.py` 외)
- **철학 연동**: `alert_bot.py`에 적용했던 "결정론적 로직 판별 + AI 스토리텔링 해설" 아키텍처를 대시보드의 '🌐 매크로 & F&G Index' 탭에도 완벽 이식.
- **데이터 수집 (`data_loader.py` & `requirements.txt`)**: 
  - `pykrx` 라이브러리를 도입하여 당일(또는 최근 거래일) 코스피 투자자별 순매수 대금(외국인, 기관, 개인) 수집 로직(`get_investor_flow`) 추가.
  - 기존 거시경제 지표에 미국 10년물 국채 금리(`^TNX`)와 WTI 원유(`CL=F`) 데이터를 `yfinance`에서 수집하도록 확장.
- **국면 판독 및 AI 통신 (`signals.py`)**:
  - `analyze_macro_flow`: 금리/유가/환율의 변동과 외국인 수급 방향을 계산해 `🟢 리스크 온`, `🔴 리스크 오프`, `🟡 혼조세` 등의 시장 국면을 기계적으로 확정 짓는 엔진 추가.
  - `generate_economic_commentary`: 코드가 판정한 데이터 세트와 국면을 Gemini 1.5 Pro (최고 성능 플래그십) 모델에 던져, CFO 관점의 거시경제 해설 텍스트 생성.
- **UI 렌더링 (`final.py`)**:
  - 매크로 탭 하단에 `st.divider()`를 추가하고 "💡 글로벌 매크로 & 수급 통합 AI 브리핑" 영역 신설.
  - 상단 3개(금리, 유가, 환율), 하단 3개(외국인, 기관, 개인 수급) 데이터를 `st.metric` 3x2 Grid 형태로 우아하게 시각화.
  - `st.info` 안내창을 통해 AI가 생성한 통찰력 있는 해설 브리핑 제공.

### 3. 미세 조정 내역 (Pro-Tip 적용)
- `alert_bot.py` 코드 최상단에 `os.environ['TZ'] = 'Asia/Seoul'` 타임존 강제 할당 (깃허브 액션 서버의 날짜 착각 방지).
- 텔레그램 메시지 전송 시 HTML 파싱 에러 발생 시를 대비한 `try-except` 일반 텍스트 재전송 로직(`parse_mode=None`) 방어막 적용.
