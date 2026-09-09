import pandas as pd
from db_connect import get_connection


def calculate_trend_stats():
    """tech_keywords 데이터를 월별로 집계해서 trend_stats에 저장"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.job_category, p.posted_date, t.keyword, t.is_required
        FROM job_postings p
        JOIN tech_keywords t ON p.posting_id = t.posting_id
    """)

    rows = cur.fetchall()
    print(f"분석할 데이터: {len(rows)}개")

    if not rows:
        print("데이터 없음")
        return

    df = pd.DataFrame(rows, columns=["job_category", "posted_date", "keyword", "is_required"])
    df["posted_date"] = pd.to_datetime(df["posted_date"])
    df["year_month"] = df["posted_date"].dt.strftime("%Y-%m")

    cur.execute("""
        SELECT job_category, TO_CHAR(posted_date, 'YYYY-MM') as year_month, COUNT(*) as total
        FROM job_postings
        GROUP BY job_category, year_month
    """)
    total_rows = cur.fetchall()
    total_df = pd.DataFrame(total_rows, columns=["job_category", "year_month", "total_postings"])

    grouped = df.groupby(["job_category", "year_month", "keyword"])

    saved = 0
    for (job_category, year_month, keyword), group in grouped:
        total_count = group.shape[0]
        required_count = group[group["is_required"] == True].shape[0]
        preferred_count = group[group["is_required"] == False].shape[0]

        total_postings_row = total_df[
            (total_df["job_category"] == job_category) &
            (total_df["year_month"] == year_month)
        ]
        total_postings = int(total_postings_row["total_postings"].values[0]) if len(total_postings_row) > 0 else 1

        required_ratio = round(required_count / total_postings, 4)
        total_ratio = round(total_count / total_postings, 4)

        try:
            cur.execute("""
                INSERT INTO trend_stats
                    (job_category, keyword, year_month, total_postings,
                     required_count, preferred_count, required_ratio, total_ratio, calculated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
            """, (job_category, keyword, year_month, total_postings,
                  required_count, preferred_count, required_ratio, total_ratio))
            saved += 1
        except Exception as e:
            print(f"저장 오류: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()
    print(f"트렌드 통계 완료! 총 {saved}개 저장")


def calculate_trend_change():
    """전월 대비 변화율 계산"""
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
    print("=== 트렌드 통계 집계 시작 ===")
    calculate_trend_stats()
    print("\n=== 트렌드 변화율 계산 시작 ===")
    calculate_trend_change()