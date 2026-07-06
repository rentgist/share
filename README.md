# 11원칙 퀀트 대시보드 v22.0

## 🛠️ 최근 업데이트 내역 (2026-07-06)
- **모듈 분리**: 단일 파일로 구성되어 있던 `final.py`를 유지보수성을 위해 `app.py`, `config.py`, `indicators.py`, `signals.py`, `data_loader.py` 5개의 모듈로 리팩토링했습니다.
- **API 안정성 향상**: `yfinance` 에러 방지를 위해 `tenacity` 모듈을 도입하여 자동 재시도(지수 백오프) 로직을 추가했습니다.
- **설정 분리**: FOMC 등 일정 데이터를 하드코딩하지 않고 `events.json`으로 분리했습니다.
- **기타 변경점**: 캐시 시간 단축(600초) 및 KST 타임존 일원화 적용.

### 🚀 사용 방법
```bash
pip install -r requirements.txt
streamlit run final.py
```
