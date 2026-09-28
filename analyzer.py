import pandas as pd
from datetime import date, timedelta
from psycopg2.extras import execute_values
from db_connect import get_connection

# 분석에 쓰는 첫 주(월요일).
# 수집이 5월 며칠(시범)과 8/25 이후로 나뉘어 있어 6월이 통째로 비어 있고,
# 그 이전 주들은 표본이 몇 건뿐이다. 8월 초부터는 끊김 없이 충분한 공고가 있다.
# 수집 기간이 늘어나면 이 날짜를 유지한 채 구간이 자연스럽게 길어진다.
SERIES_START = date(2026, 8, 3)


def analysis_weeks(today=None, start=SERIES_START):
    """
    분석 대상 주(월요일 날짜 'YYYY-MM-DD') 목록: start부터 '지난주'까지.
    아직 진행 중인 이번 주는 공고가 다 모이지 않았으므로 제외한다.
    """
    assert start.weekday() == 0, "시작일은 월요일이어야 합니다"
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    weeks = []
    week = start
    while week < this_monday:
        weeks.append(week.strftime("%Y-%m-%d"))
        week += timedelta(days=7)
    return weeks


def build_stats(df, total_df, weeks):
    """
    df       : 공고-키워드 행 (job_category, year_month, keyword, is_required)
    total_df : 직무·주별 전체 공고 수 (job_category, year_month, total_postings)
    weeks    : 분석 대상 주 목록

    결과 행: (직무, 키워드, 주, 전체공고수, 필수수, 우대수, 필수비율, 요구비율)

    키워드가 등장하지 않은 주도 0으로 채운다. 빈 주를 건너뛰면 주 간격이 어긋나
    시계열 예측(순번을 시간으로 사용)이 틀어지고, 등장한 주만 평균 내면 비율이 부풀려진다.
    그 직무의 공고가 아예 없는 주는 비율을 계산할 수 없으므로 건너뛴다.
    """
    week_set = set(weeks)
    df = df[df["year_month"].isin(week_set)]
    total_df = total_df[total_df["year_month"].isin(week_set)]

    totals = {
        (r.job_category, r.year_month): int(r.total_postings)
        for r in total_df.itertuples()
    }

    counts = {}
    for (category, week, keyword), group in df.groupby(["job_category", "year_month", "keyword"]):
        required = int((group["is_required"] == True).sum())
        counts[(category, week, keyword)] = (len(group), required)

    rows = []
    for category, keywords in df.groupby("job_category")["keyword"].unique().items():
        for keyword in sorted(keywords):
            for week in weeks:
                total_postings = totals.get((category, week))
                if not total_postings:
                    continue
                total_count, required_count = counts.get((category, week, keyword), (0, 0))
                rows.append((
                    category, keyword, week, total_postings,
                    required_count, total_count - required_count,
                    round(required_count / total_postings, 4),
                    round(total_count / total_postings, 4),
                ))
    return rows


def calculate_trend_stats(today=None):
    """
    tech_keywords를 '주' 단위로 집계해서 trend_stats에 저장한다.
    year_month에는 그 주의 월요일 날짜(YYYY-MM-DD)가 들어간다.
    Postgres의 DATE_TRUNC('week', ...)는 월요일 시작(ISO 8601) 기준이다.
    """
    conn = get_connection()
    cur = conn.cursor()

    # trend_stats는 매번 원본(job_postings/tech_keywords)에서 전체 재계산한다.
    cur.execute("TRUNCATE TABLE trend_stats")

    cur.execute("""
        SELECT p.job_category,
               TO_CHAR(DATE_TRUNC('week', p.posted_date), 'YYYY-MM-DD') AS year_month,
               t.keyword, t.is_required
        FROM job_postings p
        JOIN tech_keywords t ON p.posting_id = t.posting_id
    """)
    rows = cur.fetchall()
    print(f"분석할 데이터: {len(rows)}개")
    if not rows:
        print("데이터 없음")
        conn.commit()
        return
    df = pd.DataFrame(rows, columns=["job_category", "year_month", "keyword", "is_required"])

    cur.execute("""
        SELECT job_category,
               TO_CHAR(DATE_TRUNC('week', posted_date), 'YYYY-MM-DD') AS year_month,
               COUNT(*) AS total
        FROM job_postings
        GROUP BY 1, 2
    """)
    total_df = pd.DataFrame(cur.fetchall(), columns=["job_category", "year_month", "total_postings"])

    weeks = analysis_weeks(today)
    print(f"분석 기간: {weeks[0]} ~ {weeks[-1]} ({len(weeks)}주)" if weeks else "분석할 주가 없음")

    stats = build_stats(df, total_df, weeks)
    if stats:
        execute_values(
            cur,
            """
            INSERT INTO trend_stats
                (job_category, keyword, year_month, total_postings,
                 required_count, preferred_count, required_ratio, total_ratio, calculated_at)
            VALUES %s
            """,
            stats,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
        )

    conn.commit()
    cur.close()
    conn.close()
    print(f"트렌드 통계 완료! 총 {len(stats)}개 저장 (주 단위)")


def calculate_trend_change():
    """전주 대비 변화율 계산"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT job_category, keyword, year_month, total_ratio
        FROM trend_stats
        ORDER BY job_category, keyword, year_month
    """)

    rows = cur.fetchall()
    if not rows:
        print("trend_stats 데이터 없음")
        return

    df = pd.DataFrame(rows, columns=["job_category", "keyword", "year_month", "total_ratio"])

    updated = 0
    for (job_category, keyword), group in df.groupby(["job_category", "keyword"]):
        group = group.sort_values("year_month")
        for i in range(1, len(group)):
            prev = group.iloc[i-1]["total_ratio"]
            curr = group.iloc[i]["total_ratio"]
            year_month = group.iloc[i]["year_month"]

            change_rate = round((curr - prev) / prev * 100, 2) if prev > 0 else 0.0

            try:
                cur.execute("""
                    UPDATE trend_stats
                    SET change_rate = %s
                    WHERE job_category = %s AND keyword = %s AND year_month = %s
                """, (change_rate, job_category, keyword, year_month))
                updated += 1
            except Exception as e:
                conn.rollback()
                continue

    conn.commit()
    cur.close()
    conn.close()
    print(f"변화율 계산 완료! {updated}개 업데이트")


if __name__ == "__main__":
    print("=== 트렌드 통계 집계 시작 (주 단위) ===")
    calculate_trend_stats()
    print("\n=== 트렌드 변화율 계산 시작 ===")
    calculate_trend_change()