import streamlit as st
import json
import os
from datetime import datetime
import pytz

st.set_page_config(
    page_title="Alpha Engine | 퀀트 알파 브리핑",
    page_icon="⚡",
    layout="wide",
)

KST = pytz.timezone("Asia/Seoul")

# ── 경로 설정 (실행 위치에 무관하게 안전) ──────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
NEWS_FILE   = os.path.join(BASE_DIR, "data", "news_archive.json")
REPORT_FILE = os.path.join(BASE_DIR, "data", "smart_money_report.md")

# ── 스타일 ──────────────────────────────────────────────────────
st.markdown("""
<style>
.briefing-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border-left: 4px solid #e94560;
    border-radius: 8px;
    padding: 14px 18px;
    margin: 8px 0;
    color: #eee;
}
.briefing-card.good  { border-left-color: #00d4aa; }
.briefing-card.bad   { border-left-color: #e94560; }
.briefing-card.neutral { border-left-color: #aaa; }
.card-title   { font-size: 1.05rem; font-weight: 700; margin-bottom: 4px; }
.card-reason  { font-size: 0.88rem; color: #ccc; margin-bottom: 6px; }
.card-action  { font-size: 0.85rem; font-weight: 600; padding: 3px 8px;
                border-radius: 4px; display: inline-block; margin-top: 4px; }
.action-bad   { background: #e9456022; color: #e94560; border: 1px solid #e9456055; }
.action-good  { background: #00d4aa22; color: #00d4aa; border: 1px solid #00d4aa55; }
.action-neutral { background: #aaa2; color: #aaa; border: 1px solid #aaa5; }
.imp-badge    { font-size: 0.75rem; padding: 2px 6px; border-radius: 10px;
                background: #ffffff15; color: #ddd; margin-right: 6px; }
.sector-tag   { font-size: 0.75rem; padding: 1px 6px; border-radius: 8px;
                background: #ffffff10; color: #bbb; margin-right: 3px; }
.last-update  { font-size: 0.78rem; color: #888; }
</style>
""", unsafe_allow_html=True)

# ── 헤더 ─────────────────────────────────────────────────────────
st.title("⚡ Quant Alpha Briefing")
st.caption("AI가 선별·번역·분석한 글로벌 뉴스 브리핑 + 세력 수급 리포트")

tab_news, tab_smart = st.tabs(["📰 AI 매크로 브리핑", "🔥 세력 매집 다이버전스"])

# ════════════════════════════════════════════════════════════════
# TAB 1: AI 매크로 뉴스 브리핑 (중요도 순)
# ════════════════════════════════════════════════════════════════
with tab_news:
    if not os.path.exists(NEWS_FILE):
        st.warning("📭 아직 수집된 뉴스가 없습니다. `news_pipeline.py` 또는 GitHub Actions를 실행해주세요.")
    else:
        try:
            with open(NEWS_FILE, "r", encoding="utf-8") as f:
                news_data = json.load(f)
        except Exception as e:
            st.error(f"데이터 파일 로딩 오류: {e}")
            news_data = []

        if news_data:
            # 마지막 업데이트 시간
            last_time = news_data[0].get("fetched_at", "알 수 없음") if news_data else "-"
            st.markdown(f'<div class="last-update">⏱ 마지막 업데이트: {last_time} (KST) | 총 {len(news_data)}건</div>',
                        unsafe_allow_html=True)

            # ── 중요도 순 정렬 (이미 파이프라인에서 정렬되지만 한 번 더 보장)
            news_sorted = sorted(news_data, key=lambda x: x.get("importance", 0), reverse=True)

            # ── 상단: 중요도 4~5 핵심 브리핑 ──────────────────────
            critical = [n for n in news_sorted if n.get("importance", 0) >= 4]
            if critical:
                st.subheader("🚨 핵심 이슈 (중요도 4~5)")
                for n in critical:
                    sentiment  = n.get("sentiment", "중립")
                    imp        = n.get("importance", 0)
                    title_ko   = n.get("title_ko") or n.get("title", "제목 없음")
                    reason     = n.get("reason", "")
                    action     = n.get("action_point", "")
                    sectors    = n.get("sectors", [])
                    link       = n.get("link", "#")
                    source     = n.get("source", "")

                    css_cls    = "good" if sentiment == "호재" else ("bad" if sentiment == "악재" else "neutral")
                    icon       = "🟢" if sentiment == "호재" else ("🔴" if sentiment == "악재" else "⚪")
                    action_css = "action-good" if sentiment == "호재" else ("action-bad" if sentiment == "악재" else "action-neutral")
                    sectors_html = " ".join(f'<span class="sector-tag">{s}</span>' for s in sectors[:4])

                    st.markdown(f"""
<div class="briefing-card {css_cls}">
  <div class="card-title">{icon} <span class="imp-badge">중요도 {imp}/5</span>{title_ko}
    <span style="font-size:0.75rem;color:#888;"> — {source}</span>
  </div>
  <div class="card-reason">{reason}</div>
  {sectors_html}
  <br/><span class="card-action {action_css}">💼 액션: {action if action else '해당 없음'}</span>
  <br/><a href="{link}" target="_blank" style="font-size:0.78rem;color:#5599ff;">🔗 원문 보기</a>
</div>
""", unsafe_allow_html=True)

            # ── 중간: 중요도 2~3 참고 이슈 ───────────────────────
            mid = [n for n in news_sorted if 2 <= n.get("importance", 0) <= 3]
            if mid:
                st.subheader("📋 참고 이슈 (중요도 2~3)")
                for n in mid:
                    sentiment  = n.get("sentiment", "중립")
                    imp        = n.get("importance", 0)
                    title_ko   = n.get("title_ko") or n.get("title", "제목 없음")
                    reason     = n.get("reason", "")
                    action     = n.get("action_point", "")
                    sectors    = n.get("sectors", [])
                    link       = n.get("link", "#")
                    source     = n.get("source", "")

                    icon = "🟢" if sentiment == "호재" else ("🔴" if sentiment == "악재" else "⚪")
                    sectors_str = "  ·  ".join(sectors[:3])

                    with st.expander(f"{icon} [{imp}/5] {title_ko}  ({source})"):
                        if reason:
                            st.markdown(f"**📊 영향 분석:** {reason}")
                        if action:
                            st.markdown(f"**💼 투자자 액션:** `{action}`")
                        if sectors_str:
                            st.caption(f"🏢 관련 섹터: {sectors_str}")
                        st.markdown(f"[🔗 기사 원문 보기]({link})")

        else:
            st.info("수집된 뉴스가 없습니다.")

# ════════════════════════════════════════════════════════════════
# TAB 2: 세력 매집 다이버전스 리포트
# ════════════════════════════════════════════════════════════════
with tab_smart:
    st.header("🔥 세력 매집 다이버전스 리포트")
    st.caption("주가 하락 중 외인+기관이 공격적으로 매집 중인 종목 탐색 (실 데이터 기반)")

    if not os.path.exists(REPORT_FILE):
        st.warning("생성된 리포트가 없습니다. `smart_money_engine.py`를 실행해주세요.")
    else:
        try:
            with open(REPORT_FILE, "r", encoding="utf-8") as f:
                report_content = f.read()
            st.markdown(report_content)
        except Exception as e:
            st.error(f"리포트 로딩 오류: {e}")

# ── 사이드바 ──────────────────────────────────────────────────
st.sidebar.markdown("### ⚙️ 자동화 안내")
st.sidebar.info(
    "GitHub Actions가 **매 시간 정각**에 자동 실행되어 "
    "뉴스 수집 및 수급 분석을 업데이트합니다.\n\n"
    "이 대시보드는 결과 파일만 읽어오는 Read-Only Viewer입니다."
)
now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
st.sidebar.caption(f"현재 시각: {now_kst} (KST)")
