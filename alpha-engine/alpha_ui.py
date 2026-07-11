import streamlit as st
import json
import os

st.set_page_config(page_title="Alpha Engine UI", page_icon="⚡", layout="wide")

st.title("⚡ Quant Alpha Engine Viewer")
st.caption("독립 구동되는 AI 뉴스 파이프라인과 스마트 머니(세력) 수급 엔진의 결과물을 가볍게 확인하는 전용 대시보드입니다.")

tab_news, tab_smart = st.tabs(["📰 실시간 AI 뉴스 데스크", "🔥 세력 매집 다이버전스"])

with tab_news:
    st.header("📰 AI 매크로 뉴스 브리핑")
    st.markdown("글로벌 주요 경제 매체(WSJ, CNBC 등)에서 파급력이 높은 뉴스만 선별하여 AI가 분석한 결과입니다.")
    
    news_file = "data/news_archive.json"
    if os.path.exists(news_file):
        try:
            with open(news_file, "r", encoding="utf-8") as f:
                news_data = json.load(f)
            
            if not news_data:
                st.info("수집된 뉴스가 없습니다.")
            else:
                for news in news_data:
                    imp = news.get("importance", 0)
                    sentiment = news.get("sentiment", "중립")
                    
                    if sentiment == "호재":
                        icon = "🟢"
                    elif sentiment == "악재":
                        icon = "🔴"
                    else:
                        icon = "⚪"
                        
                    # 한국어 번역 제목(title_ko)이 있으면 우선 사용하고, 없으면 원본 title 사용
                    display_title = news.get('title_ko', news.get('title'))
                    
                    with st.expander(f"{icon} [중요도 {imp}/5] {display_title} ({news.get('source')})"):
                        st.markdown(f"**🎯 AI 한줄 평:** {news.get('reason')}")
                        st.markdown(f"**💡 핵심 키워드:** {', '.join(news.get('keywords', []))}")
                        st.markdown(f"**🏢 영향 섹터:** {', '.join(news.get('sectors', []))}")
                        st.caption(f"수집 시간: {news.get('fetched_at')}")
                        st.markdown(f"🔗 **[기사 원문 보기 (영어/원본)]({news.get('link')})**")
        except Exception as e:
            st.error(f"뉴스 데이터를 불러오는데 실패했습니다: {e}")
    else:
        st.warning("아직 수집된 뉴스가 없습니다. `news_pipeline.py` 엔진을 실행해주세요.")

with tab_smart:
    st.header("🔥 스마트 머니 수급 리포트")
    st.markdown("주가는 폭락 중이나 세력(외인/기관)이 공격적으로 매집 중인 다이버전스 종목 리스트입니다.")
    
    report_file = "data/smart_money_report.md"
    if os.path.exists(report_file):
        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report_content = f.read()
            st.markdown(report_content)
        except Exception as e:
            st.error(f"리포트를 불러오는데 실패했습니다: {e}")
    else:
        st.warning("생성된 리포트가 없습니다. `smart_money_engine.py` 엔진을 실행해주세요.")

st.sidebar.markdown("### ⚙️ Engine Control")
st.sidebar.info("실제 운영 시에는 GitHub Actions나 로컬 스케줄러(Cron)를 통해 엔진 스크립트들이 백그라운드에서 자동 실행됩니다. 이 대시보드는 단순히 결과만 읽어오는 Viewer 역할입니다.")
