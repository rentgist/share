import os
import json
from datetime import datetime

def generate_smart_control_room_report(market_context: str) -> str:
    """
    Reads data/news_archive.json and asks Gemini to synthesize a market report.
    market_context is a string containing the current algorithm's verdict and scores.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "🚨 `GEMINI_API_KEY` 환경변수가 설정되지 않아 AI 리포트를 생성할 수 없습니다. `.env` 파일을 확인하세요."
        
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        import requests
        news_data = []
        remote_url = "https://raw.githubusercontent.com/rentgist/quant-alpha-engine/main/data/news_archive.json"
        try:
            resp = requests.get(remote_url, timeout=5)
            if resp.status_code == 200:
                news_data = resp.json()
        except:
            pass
            
        if not news_data:
            news_file = os.path.join("..", "quant-alpha-engine", "data", "news_archive.json")
            if not os.path.exists(news_file):
                news_file = os.path.join("data", "news_archive.json")
            if os.path.exists(news_file):
                try:
                    with open(news_file, "r", encoding="utf-8") as f:
                        news_data = json.load(f)
                except:
                    pass

        news_text = "최근 수집된 뉴스가 없습니다. (백그라운드 뉴스 수집 파이프라인 대기 중)"
        
        if news_data:
            top_news = news_data[:60]
            if top_news:
                news_lines = []
                for n in top_news:
                    title = n.get("title_ko", n.get("title", "제목 없음"))
                    sentiment = n.get("sentiment", "중립")
                    importance = n.get("importance", 0)
                    action = n.get("action_point", "")
                    news_lines.append(f"- [{sentiment}/중요도:{importance}] {title} (대응: {action})")
                news_text = "\n".join(news_lines)
                
        prompt = f"""너는 대한민국 상위 1% 자산가를 위한 월스트리트 최고 수준의 매크로 애널리스트이자 11원칙 장기 투자(Value Accumulation)의 대가다.
다음 주어진 '알고리즘 시스템의 현재 판독 결과'와 '최근 글로벌 뉴스'를 바탕으로, 대시보드 상황판에 어울리는 브리핑을 Markdown 포맷으로 작성하라.

[알고리즘 시스템 판독 결과]
{market_context}

[최근 글로벌 속보 요약]
{news_text}

[작성 지침 및 철학 (매우 중요)]
1. **가독성 극대화**: 줄글로 길게 늘어놓지 마라. 중요한 수치와 액션은 **굵은 글씨(Bold)** 및 Bullet Point로 구조화하고, 문단 사이에 충분한 여백을 두어 한눈에 들어오게 하라.
2. **현실적인 자산배분 철학 (대가의 관점)**:
   - 현재 유저(직장인 투자자)는 **이미 주식에서 마이너스 손실을 보고 있는 상황**이며, 전체 투자금의 **약 50% 정도의 추가 투입 가능한 예비 현금**을 쥐고 있는 상태다.
   - 이런 하락장/공포장에서 이미 손실이 크게 나 있는 **우량 코어 자산(예: 반도체 대형주 등)을 공포에 질려 패닉 셀링(손절)하는 것은 대가의 관점이 아니다.** 손실 중인 우량주는 굳건히 **홀딩(Holding)**하며 정기 소득을 통한 장기 가치 적립 관점을 유지해야 함을 역설하라.
   - 단, **레버리지 상품(선물물량, 레버리지 ETF 등)**은 강제 반대매매나 녹아내림의 위험이 극도로 크므로 비중 축소 및 즉시 정리를 권고하라.
   - **남은 예비 현금(50%)**은 지금 같은 칼날 구간에서 급하게 투입하지 말고, 알고리즘상 **진바닥(Tier 2~3) 신호가 뜰 때까지 철저히 아껴두었다가 분할 적립식**으로 타격해야 함을 조언하라.
3. 알고리즘 판독 결과(안전장치)를 **최우선 절대 원칙**으로 삼아라. 
   - 예컨대 알고리즘이 "떨어지는 칼날(매수 보류)" 상태라고 판정했다면, 비록 뉴스에 호재가 있더라도 매수를 보류하고 리스크를 관리해야 함을 강력히 조언해야 한다.
4. 리포트는 엘리트 트레이더의 톤앤매너로, 매우 확신에 찬 어조(~~하십시오, ~~입니다, ~~해야 합니다)를 사용하라. 애매모호한 표현을 금지한다.

[브리핑 작성 양식]
반드시 아래 3가지 섹션으로 나누어 작성하라 (Markdown Header ### 사용).

### 🌐 현재 시장 국면 요약
(현재의 매크로 지표와 수급 다이버전스를 종합하여, 시장의 진짜 위치를 명확히 브리핑하십시오. 줄글은 2-3줄로 끝내고 핵심 요약 포인트를 Bullet으로 제공하십시오.)

### 🔭 72시간 단기 전망
(글로벌 뉴스 및 지정학 리스크가 반도체/IT 및 원자재 등 주요 자산 가격에 미칠 단기적 흐름을 예리하게 분석하십시오.)

### 🎯 최종 행동 지침 (CFO Action Plan)
(아래 3가지를 핵심 뼈대로 유저에게 매우 현실적이고 구체적인 액션 플랜을 제시하십시오.)
1. **보유 중인 우량주**: 패닉 셀 금지, 굳건한 홀딩 전략 유지.
2. **레버리지/신용 자산**: 반대매매 방지를 위한 즉각적인 리스크 관리(정리).
3. **남은 현금(50%) 집행**: 현재 칼날 구간에서는 매수 보류(현금 사수), 향후 진바닥 신호(Tier 2~3) 확인 후 적립식 분할 매수 대기.
"""

        models_to_try = [
            "gemini-2.5-pro",          # 1순위: 2.5 Pro (최상급 브레인)
            "gemini-3.5-flash",        # 2순위: 3.5 Flash (강력한 신형 Flash)
            "gemini-3.1-flash-lite",   # 3순위: 3.1 Flash Lite (확인된 안정 모델)
            "gemini-2.5-flash-lite",   # 4순위: 2.5 Flash Lite
            "gemini-pro-latest",
            "gemini-flash-latest"
        ]
        
        response = None
        last_err = None
        successful_model = None
        
        errors = []
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                successful_model = model_name
                break
            except Exception as e:
                errors.append(f"- 신규 SDK `{model_name}` 실패: {str(e)}")
                last_err = e
                continue
                
        if response:
            return f"*(사용된 AI 모델: {successful_model})*\n\n" + response.text.strip()
        else:
            # ──────────────────────────────────────────────────────────
            # [구형 SDK 폴백] 신규 SDK가 전부 실패 시, 구형 google-generativeai로 우회 시도
            # ──────────────────────────────────────────────────────────
            try:
                import google.generativeai as genai_old
                genai_old.configure(api_key=api_key)
                
                # 구형 SDK에서 검증된 안정 모델 6개 순차 시도
                for old_model in ["gemini-2.5-pro", "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-pro-latest", "gemini-flash-latest"]:
                    try:
                        model = genai_old.GenerativeModel(old_model)
                        # 안전 설정 무력화 (에러 방지)
                        safety_settings = [
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                        ]
                        old_response = model.generate_content(prompt, safety_settings=safety_settings)
                        if old_response and old_response.text:
                            return f"*(구형 SDK 모델: {old_model} 우회 성공)*\n\n" + old_response.text.strip()
                    except Exception as e_old:
                        errors.append(f"- 구형 SDK `{old_model}` 실패: {str(e_old)}")
            except Exception as e_import:
                errors.append(f"- 구형 SDK 로드 실패: {str(e_import)}")

            # ──────────────────────────────────────────────────────────
            # [최종 디버그: 지원 모델 리스트 조회]
            # ──────────────────────────────────────────────────────────
            available_models = []
            try:
                # 신규 SDK로 모델 목록 조회 시도
                for m in client.models.list():
                    available_models.append(f"  - `{m.name}` (신규 SDK)")
            except Exception as e_list1:
                errors.append(f"- 신규 SDK 모델 목록 조회 실패: {e_list1}")
                
            try:
                # 구형 SDK로 모델 목록 조회 시도
                import google.generativeai as genai_old
                genai_old.configure(api_key=api_key)
                for m in genai_old.list_models():
                    available_models.append(f"  - `{m.name}` (구형 SDK)")
            except Exception as e_list2:
                errors.append(f"- 구형 SDK 모델 목록 조회 실패: {e_list2}")

            models_str = "\n".join(available_models) if available_models else "조회된 모델 없음"
            error_details = "\n".join(errors)
            return (
                f"🚨 **AI 모델 호출에 전부 실패했습니다.**\n\n"
                f"**[상세 에러 로그]**\n{error_details}\n\n"
                f"**[현재 API Key가 사용 가능한 모델 목록]**\n{models_str}"
            )
        
    except Exception as e:
        return f"🚨 AI 리포트 생성 중 예외 발생: {e}"
