import os
import streamlit as st
import plotly.express as px
import pandas as pd
from db_connect import get_connection
import plotly.graph_objects as go
from taxonomy import TECH_TAXONOMY

st.set_page_config(page_title="기술 스택 트렌드 분석", layout="wide")

# ── 공통 데이터 로드 ──────────────────────────
@st.cache_data
def load_trend_stats():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT job_category, keyword, year_month, total_postings,
               required_ratio, total_ratio
        FROM trend_stats
        ORDER BY job_category, keyword, year_month
    """, conn)
    conn.close()
    return df

@st.cache_data
def load_forecasts():
    conn = get_connection()
    df = pd.read_sql("""
        SELECT job_category, keyword, target_month,
               predicted_ratio, lower_bound, upper_bound
        FROM forecasts
        ORDER BY job_category, keyword, target_month
    """, conn)
    conn.close()
    return df

@st.cache_data
def load_summary():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM job_postings")
    total_postings = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT keyword) FROM tech_keywords")
    total_keywords = cur.fetchone()[0]
    cur.execute("SELECT keyword, COUNT(*) as cnt FROM tech_keywords GROUP BY keyword ORDER BY cnt DESC LIMIT 1")
    top_keyword = cur.fetchone()
    conn.close()
    return total_postings, total_keywords, top_keyword

@st.cache_data(ttl=600)
def load_dictionary_watch():
    """사전 점검 기록(커버리지 이력, 검토 대기 후보). 아직 테이블이 없거나 비어 있으면 (None, None)."""
    conn = get_connection()
    try:
        coverage = pd.read_sql("""
            SELECT measured_at, dictionary_size, postings_with_text, postings_covered, coverage_ratio
            FROM dictionary_coverage
            ORDER BY measured_at
        """, conn)
        candidates = pd.read_sql("""
            SELECT term, doc_count, doc_ratio, example, first_seen, last_seen
            FROM tech_candidates
            ORDER BY doc_count DESC, term
        """, conn)
    except Exception:
        return None, None
    finally:
        conn.close()
    return coverage, candidates

# 요구 비율의 의미 (analyzer.py의 ONLY_POSTINGS_WITH_TECH = True 기준)
RATIO_NOTE = "요구 비율 = 기술 스택이 언급된 공고 중, 해당 기술이 나온 공고의 비율"

def _get_admin_password():
    """배포 환경(Streamlit Cloud Secrets)과 로컬(.env) 둘 다 지원한다."""
    try:
        return st.secrets["ADMIN_PASSWORD"]
    except Exception:
        return os.environ.get("ADMIN_PASSWORD")


# ── 네비게이션 ────────────────────────────────
st.sidebar.title("기술 스택 트렌드")

# "사전 점검"은 개발용 내부 화면이라 비밀번호를 아는 사람에게만 메뉴에 보이게 한다.
# 비밀번호가 틀리거나 설정 자체가 없으면 그 탭은 메뉴 목록에 아예 나타나지 않는다.
_admin_password = _get_admin_password()
if _admin_password and not st.session_state.get("is_admin"):
    with st.sidebar.expander("🔒 관리자"):
        entered = st.text_input("비밀번호", type="password", key="admin_pw_input")
        if entered and entered == _admin_password:
            st.session_state["is_admin"] = True
            st.rerun()
_menu_options = ["메인 대시보드", "트렌드 분석", "필수·우대 분석", "수요 예측"]
if st.session_state.get("is_admin"):
    _menu_options.append("사전 점검")
page = st.sidebar.radio("메뉴", _menu_options)

JOB_CATEGORIES = [
    "백엔드 개발자", "프론트엔드 개발자", "데이터 엔지니어",
    "데이터 분석가", "ML 엔지니어", "DevOps", "보안 엔지니어"
]

# ── SCREEN-01 메인 대시보드 ───────────────────
if page == "메인 대시보드":
    st.title("📊 기술 스택 트렌드 분석 시스템")
    st.caption("사람인 채용공고 기반 기술 스택 트렌드 분석 (원티드는 수집량이 매우 적어 참고용)")
    st.caption(RATIO_NOTE)

    job_category = st.selectbox("직무 선택", JOB_CATEGORIES)

    df = load_trend_stats()
    filtered = df[df["job_category"] == job_category].copy()

    # 이번 주 데이터 (year_month는 그 주의 월요일 날짜, YYYY-MM-DD 형식이라
    # 문자열 비교(max/min)만으로도 날짜순 정렬이 그대로 유지됨)
    latest_month = filtered["year_month"].max()
    prev_month = filtered[filtered["year_month"] < latest_month]["year_month"].max() if len(filtered["year_month"].unique()) > 1 else None

    latest = filtered[filtered["year_month"] == latest_month].copy()
    latest = latest.groupby("keyword").agg(
        total_ratio=("total_ratio", "mean"),
        required_ratio=("required_ratio", "mean")
    ).reset_index()

    # 상단 요약 카드
    total_postings, total_keywords, top_keyword = load_summary()
    top_tech = latest.sort_values("total_ratio", ascending=False).iloc[0]["keyword"] if not latest.empty else "-"

    # 가장 빠르게 증가한 기술
    if prev_month:
        prev = filtered[filtered["year_month"] == prev_month].groupby("keyword")["total_ratio"].mean()
        curr = latest.set_index("keyword")["total_ratio"]
        change = (curr - prev).dropna()
        fastest = change.idxmax() if not change.empty else "-"
    else:
        fastest = "-"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총 수집 공고", f"{total_postings:,}건")
    col2.metric("추출된 기술 종류", f"{total_keywords}종")
    col3.metric("가장 많이 요구", top_tech)
    col4.metric("가장 빠르게 증가", fastest)

    st.divider()

    # 기술별 표
    if filtered.empty:
        st.warning("해당 직무의 데이터가 없습니다.")
    else:
        latest["요구 비율(%)"] = (latest["total_ratio"] * 100).round(2)
        latest["필수 비율(%)"] = (latest["required_ratio"] * 100).round(2)

        # 전주 대비 변화율
        if prev_month:
            prev_df = filtered[filtered["year_month"] == prev_month].groupby("keyword")["total_ratio"].mean()
            latest["변화율(%)"] = latest.apply(
                lambda row: round((row["total_ratio"] - prev_df.get(row["keyword"], row["total_ratio"])) * 100, 2)
                if row["keyword"] in prev_df.index else 0, axis=1
            )
            latest["트렌드"] = latest["변화율(%)"].apply(
                lambda x: "🔺 급상승" if x > 5 else ("↑ 상승" if x > 0 else ("↓ 하락" if x < 0 else "➡ 유지"))
            )
        else:
            latest["변화율(%)"] = 0
            latest["트렌드"] = "➡ 유지"

        latest = latest.sort_values("요구 비율(%)", ascending=False)

        st.subheader(f"{job_category} 기술 스택 현황 ({latest_month} 주)")
        st.dataframe(
            latest[["keyword", "요구 비율(%)", "필수 비율(%)", "변화율(%)", "트렌드"]].rename(
                columns={"keyword": "기술"}
            ),
            use_container_width=True,
            hide_index=True
        )
# ── SCREEN-02 트렌드 분석 ─────────────────────
elif page == "트렌드 분석":
    st.title("📈 트렌드 분석")
    st.caption("직무별 기술 스택 주별 요구 비율 변화")
    st.caption(RATIO_NOTE)

    job_category = st.selectbox("직무 선택", JOB_CATEGORIES)
    df = load_trend_stats()
    filtered = df[df["job_category"] == job_category]

    if filtered.empty:
        st.warning("해당 직무의 데이터가 없습니다.")
    else:
        keywords = filtered["keyword"].unique().tolist()
        default = keywords[:5] if len(keywords) >= 5 else keywords
        selected = st.multiselect("기술 선택", keywords, default=default)

        if selected:
            chart_df = filtered[filtered["keyword"].isin(selected)].copy()
            chart_df["요구 비율(%)"] = (chart_df["total_ratio"] * 100).round(2)
            # year_month가 이미 "그 주의 월요일" 완전한 날짜(YYYY-MM-DD)라
            # "-01"을 붙이지 않고 바로 파싱한다.
            chart_df["year_month"] = pd.to_datetime(chart_df["year_month"])

            fig = px.line(
                chart_df,
                x="year_month",
                y="요구 비율(%)",
                color="keyword",
                markers=True,
                title=f"{job_category} 기술 스택 트렌드",
                labels={"year_month": "주", "keyword": "기술"}
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("상위 기술 요약")
            top3 = filtered.groupby("keyword")["total_ratio"].mean().sort_values(ascending=False).head(3)
            cols = st.columns(3)
            for i, (kw, ratio) in enumerate(top3.items()):
                cols[i].metric(f"Top {i+1}", kw, f"{ratio*100:.2f}%")

# ── SCREEN-03 필수·우대 분석 ──────────────────
elif page == "필수·우대 분석":
    st.title("🔍 필수·우대 분석")
    st.caption("직무별 기술 스택 필수·우대 비율")

    job_category = st.selectbox("직무 선택", JOB_CATEGORIES)
    df = load_trend_stats()
    filtered = df[df["job_category"] == job_category].copy()

    if filtered.empty:
        st.warning("해당 직무의 데이터가 없습니다.")
    else:
        # 키워드별로 여러 주(week)의 데이터가 쌓여있으므로, 먼저 평균을 낸 뒤
        # 그래프를 그려야 한다. 원본을 그대로 넘기면 같은 키워드의 여러 주치
        # 막대가 계속 누적(stack)되어 필수 비율만 과도하게 커지고
        # 우대 비율은 상대적으로 묻혀 보이지 않는 문제가 있었다.
        agg = filtered.groupby("keyword").agg(
            required_ratio=("required_ratio", "mean"),
            total_ratio=("total_ratio", "mean")
        ).reset_index()

        agg["필수 비율"] = agg["required_ratio"]
        agg["우대 비율"] = agg["total_ratio"] - agg["required_ratio"]

        fig = px.bar(
            agg,
            x="keyword",
            y=["필수 비율", "우대 비율"],
            title=f"{job_category} 필수·우대 비율",
            labels={"value": "비율", "keyword": "기술", "variable": "구분"},
            color_discrete_map={"필수 비율": "#2ecc71", "우대 비율": "#3498db"},
            barmode="stack"
        )
        st.plotly_chart(fig, use_container_width=True)

        st.info("필수 비율 70% 이상: 무조건 필요 | 30~70%: 있으면 플러스 | 30% 미만: 우대 위주")
        st.caption("⚠️ 현재 채용공고 상세 본문 수집이 제한적이어서, "
                   "우대사항 등 세부 요건이 필수 비율에 비해 과소 집계될 수 있습니다.")

# ── SCREEN-04 수요 예측 ───────────────────────
elif page == "수요 예측":
    st.title("🔮 수요 예측")
    st.caption("향후 8주 기술 수요 예측 — 기술마다 여러 모델과 단순 기준선(직전 값·최근 평균) 중 검증 오차가 가장 작은 방식을 자동 선택")

    # 모델 성능 비교 섹션
    st.subheader("📊 모델 성능 비교")

    @st.cache_data
    def load_model_stats():
        conn = get_connection()
        df = pd.read_sql("""
            SELECT model_name, AVG(r2) as avg_r2, AVG(mse) as avg_mse, COUNT(*) as cnt
            FROM model_stats
            GROUP BY model_name
            ORDER BY avg_r2 DESC
        """, conn)
        conn.close()
        return df

    model_df = load_model_stats()

    if not model_df.empty:
        model_df["평균 R²"] = model_df["avg_r2"].round(3)
        model_df["평균 MSE"] = model_df["avg_mse"].round(5)
        model_df["평가 계열 수"] = model_df["cnt"]
        model_df["모델명"] = model_df["model_name"]

        col1, col2 = st.columns(2)

        with col1:
            fig_r2 = px.bar(
                model_df,
                x="모델명",
                y="평균 R²",
                title="모델별 평균 R² (높을수록 좋음)",
                color="모델명",
                color_discrete_sequence=["#95a5a6", "#f1c40f", "#2ecc71", "#3498db", "#e74c3c"]
            )
            fig_r2.update_layout(showlegend=False)
            st.plotly_chart(fig_r2, use_container_width=True)

        with col2:
            fig_mse = px.bar(
                model_df,
                x="모델명",
                y="평균 MSE",
                title="모델별 평균 MSE (낮을수록 좋음)",
                color="모델명",
                color_discrete_sequence=["#95a5a6", "#f1c40f", "#2ecc71", "#3498db", "#e74c3c"]
            )
            fig_mse.update_layout(showlegend=False)
            st.plotly_chart(fig_mse, use_container_width=True)

        st.dataframe(
            model_df[["모델명", "평균 R²", "평균 MSE", "평가 계열 수"]],
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # 예측 그래프 섹션
    st.subheader("📈 기술별 수요 예측")

    job_category = st.selectbox("직무 선택", JOB_CATEGORIES)
    df = load_trend_stats()
    forecast_df = load_forecasts()

    filtered = df[df["job_category"] == job_category]
    if filtered.empty:
        st.warning("해당 직무의 데이터가 없습니다.")
    else:
        keywords = filtered["keyword"].unique().tolist()
        keyword = st.selectbox("기술 선택", keywords)

        actual = filtered[filtered["keyword"] == keyword].copy()
        actual = actual.groupby("year_month")["total_ratio"].mean().reset_index()
        # year_month가 이미 완전한 날짜(YYYY-MM-DD)이므로 "-01" 없이 바로 파싱
        actual["날짜"] = pd.to_datetime(actual["year_month"])
        actual["요구 비율(%)"] = (actual["total_ratio"] * 100).round(2)
        actual = actual.sort_values("날짜")

        forecast = forecast_df[
            (forecast_df["job_category"] == job_category) &
            (forecast_df["keyword"] == keyword)
            ].copy()

        fig = go.Figure()

        # 실제 데이터 실선
        fig.add_trace(go.Scatter(
            x=actual["날짜"],
            y=actual["요구 비율(%)"],
            mode="lines+markers",
            name="실제 데이터",
            line=dict(color="#2ecc71", width=2),
            marker=dict(size=6)
        ))

        if not forecast.empty:
            # target_month도 이제 완전한 날짜(YYYY-MM-DD)라 "-01" 없이 바로 파싱
            forecast["날짜"] = pd.to_datetime(forecast["target_month"])
            forecast["요구 비율(%)"] = (forecast["predicted_ratio"] * 100).round(2)
            forecast["하한(%)"] = (forecast["lower_bound"] * 100).round(2)
            forecast["상한(%)"] = (forecast["upper_bound"] * 100).round(2)
            forecast = forecast.sort_values("날짜")

            # 실제-예측 연결선
            last_actual = actual.iloc[-1]
            first_forecast = forecast.iloc[0]
            fig.add_trace(go.Scatter(
                x=[last_actual["날짜"], first_forecast["날짜"]],
                y=[last_actual["요구 비율(%)"], first_forecast["요구 비율(%)"]],
                mode="lines",
                line=dict(color="#e74c3c", width=2, dash="dot"),
                showlegend=False
            ))

            # 예측 점선
            fig.add_trace(go.Scatter(
                x=forecast["날짜"],
                y=forecast["요구 비율(%)"],
                mode="lines+markers",
                name="예측값",
                line=dict(color="#e74c3c", width=2, dash="dot"),
                marker=dict(size=6)
            ))

            # 신뢰구간 음영
            fig.add_trace(go.Scatter(
                x=pd.concat([forecast["날짜"], forecast["날짜"][::-1]]),
                y=pd.concat([forecast["상한(%)"], forecast["하한(%)"][::-1]]),
                fill="toself",
                fillcolor="rgba(231, 76, 60, 0.15)",
                line=dict(color="rgba(255,255,255,0)"),
                name="신뢰구간",
                showlegend=True
            ))

            # 예측 시작 구분선
            fig.add_vline(
                x=last_actual["날짜"].timestamp() * 1000,
                line_dash="dash",
                line_color="gray",
                annotation_text="예측 시작",
                annotation_position="bottom"
            )

        fig.update_layout(
            title=f"{keyword} 수요 예측 (실제 → 예측)",
            xaxis_title="날짜",
            yaxis_title="요구 비율(%)",
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 하단 기술별 카드
        st.divider()
        st.subheader("기술별 예측 요약")
        top_keywords = filtered.groupby("keyword")["total_ratio"].mean().sort_values(ascending=False).head(
            3).index.tolist()
        cols = st.columns(3)
        for i, kw in enumerate(top_keywords):
            curr_ratio = filtered[filtered["keyword"] == kw]["total_ratio"].mean() * 100
            pred = forecast_df[
                (forecast_df["job_category"] == job_category) &
                (forecast_df["keyword"] == kw)
                ]
            if not pred.empty:
                pred_ratio = pred["predicted_ratio"].mean() * 100
                change = pred_ratio - curr_ratio
                trend = "🔺 급상승 전망" if change > 5 else ("↑ 상승 전망" if change > 0 else "↓ 하락 전망")
                cols[i].metric(
                    label=kw,
                    value=f"{pred_ratio:.1f}%",
                    delta=f"{change:+.1f}%p"
                )
                cols[i].caption(trend)
            else:
                cols[i].metric(label=kw, value=f"{curr_ratio:.1f}%")

        st.info("⚠️ 예측 결과는 참고용이며 외부 요인에 의한 급격한 변화는 반영되지 않을 수 있습니다.")

# ── SCREEN-05 사전 점검 ───────────────────────
elif page == "사전 점검":
    st.title("🔎 사전 점검")
    st.caption("키워드 사전에 없는 기술이 공고에 들어 있을 때 어떻게 다루는지 — 탐지 → 측정 → 보관 → 검토·반영")

    coverage_df, candidates_df = load_dictionary_watch()

    if coverage_df is None or coverage_df.empty:
        st.info("아직 사전 점검 기록이 없습니다. 파이프라인이 한 번 실행되면 표시됩니다.")
    else:
        latest = coverage_df.iloc[-1]
        with_text = int(latest["postings_with_text"])
        covered = int(latest["postings_covered"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("기술 사전", f"{int(latest['dictionary_size'])}개")
        col2.metric("기술 커버리지", f"{float(latest['coverage_ratio']) * 100:.1f}%",
                    help="본문이 있는 공고 중 기술이 하나라도 잡힌 공고의 비율")
        col3.metric("기술이 안 잡힌 공고", f"{with_text - covered:,}건",
                    help="사전에 없는 기술이 있거나, 개발 직무가 아닌 공고")
        col4.metric("검토 대기 후보", f"{len(candidates_df)}개")

        if len(coverage_df) >= 2:
            chart_df = coverage_df.copy()
            chart_df["커버리지(%)"] = (chart_df["coverage_ratio"].astype(float) * 100).round(1)
            fig = px.line(chart_df, x="measured_at", y="커버리지(%)", markers=True,
                          hover_data=["dictionary_size"], title="사전 점검 시점별 커버리지",
                          labels={"measured_at": "점검 시각", "dictionary_size": "사전 크기"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("커버리지 기록이 2회 이상 쌓이면 변화 그래프가 표시됩니다.")

    st.divider()
    st.subheader("검토 대기 후보 (사전에 없는 표기)")
    st.caption("공고 수가 많은 순입니다. 🆕는 최근 7일 안에 처음 나타난 후보입니다.")
    if candidates_df is None or candidates_df.empty:
        st.success("검토 대기 후보가 없습니다.")
    else:
        recent_start = pd.Timestamp.today().normalize() - pd.Timedelta(days=7)
        shown = candidates_df.copy()
        shown["공고 비율(%)"] = (shown["doc_ratio"].astype(float) * 100).round(2)
        shown["신규"] = shown["first_seen"].apply(
            lambda d: "🆕" if pd.Timestamp(d) >= recent_start else "")
        st.dataframe(
            shown[["신규", "term", "doc_count", "공고 비율(%)", "example"]].rename(
                columns={"term": "후보", "doc_count": "공고 수", "example": "예문"}).head(50),
            use_container_width=True, hide_index=True
        )

    st.divider()
    st.subheader("처리 방식")
    st.markdown(
        "1. **탐지** — 공고 본문에서 사전에 없는 영문 기술 표기를 찾아 공고 수 순으로 정리합니다.\n"
        "2. **측정** — 본문이 있는 공고 중 기술이 하나라도 잡힌 비율(커버리지)을 매번 기록합니다.\n"
        "3. **보관** — 검토 대기 후보를 저장하고, 처음 나타난 날짜를 남겨 새로 등장한 기술을 알아봅니다.\n"
        "4. **반영** — 개발 기술이면 사전에 추가하고 전체 공고를 소급 재분석합니다. "
        "개발 기술이 아니면 검토 이력에 제외로 기록하고 다음 점검부터 후보에서 뺍니다.\n\n"
        "후보가 전체 공고의 2% 미만이 되면 사전 확장을 멈춥니다."
    )

    st.subheader("기술 사전 구성 (대분류 → 세부 기술)")
    st.dataframe(
        pd.DataFrame([
            {"대분류": category, "기술 수": len(techs), "세부 기술": ", ".join(techs)}
            for category, techs in TECH_TAXONOMY.items()
        ]),
        use_container_width=True, hide_index=True
    )