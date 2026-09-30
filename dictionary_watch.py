"""
사전 점검: 크롤링한 공고에 기술 사전에 없는 기술이 들어 있을 때 다루는 절차.

파이프라인이 키워드 추출 뒤에 매번 실행한다. 절차는 네 단계다.
  1. 탐지   : 본문에서 사전에 없는 영문 기술 표기를 찾아 공고 수 순으로 정리한다(discover_terms).
  2. 측정   : 본문이 있는 공고 중 기술이 하나라도 잡힌 비율(커버리지)을 재서 이력으로 남긴다.
  3. 보관   : 검토 대기 후보를 tech_candidates 테이블에 저장한다. 처음 나타난 날짜(first_seen)가
              유지되므로 새로 등장한 기술을 알아볼 수 있고, 대시보드의 "사전 점검" 페이지에 보인다.
  4. 반영   : 사람이 후보를 검토해 개발 기술이면 taxonomy.py에 추가하고 processor.py --rebuild로
              전체 공고에 소급 적용한다. 개발 기술이 아니면 discover_terms.py의 REVIEWED_SKIP에 적는다.
              둘 중 어느 쪽이든 다음 실행부터 대기 목록에서 빠진다.

직접 실행하면 한 번 점검하고 끝난다:  python dictionary_watch.py
"""
from datetime import date

from psycopg2.extras import execute_values

from db_connect import get_connection
from discover_terms import find_candidates, load_texts
from taxonomy import TECH_KEYWORDS

MIN_DOCS = 5   # 이 수 이상의 공고에 나온 표기만 후보로 본다
TOP = 100      # 대기 목록에 남길 최대 후보 수


def measure_coverage(cur):
    """
    본문이 있는 공고 수와, 그중 기술이 하나라도 잡힌 공고 수.
    분석에 실제로 쓰이는 tech_keywords 기준이라 이력끼리 같은 조건으로 비교된다.
    """
    cur.execute("""
        SELECT
          COUNT(DISTINCT p.post_url) FILTER (WHERE LENGTH(p.content) >= 300),
          COUNT(DISTINCT p.post_url) FILTER (WHERE LENGTH(p.content) >= 300 AND EXISTS (
                SELECT 1 FROM tech_keywords t WHERE t.posting_id = p.posting_id))
        FROM job_postings p
        WHERE p.source = '사람인'
    """)
    return cur.fetchone()


def update_dictionary_watch(today=None):
    today = today or date.today()

    texts = load_texts()
    candidates = find_candidates(texts, min_docs=MIN_DOCS, top=TOP)
    total = len(texts)

    conn = get_connection()
    cur = conn.cursor()

    with_text, covered = measure_coverage(cur)
    if with_text:
        cur.execute("""
            INSERT INTO dictionary_coverage
                (dictionary_size, postings_with_text, postings_covered, coverage_ratio)
            VALUES (%s, %s, %s, %s)
        """, (len(TECH_KEYWORDS), with_text, covered, round(covered / with_text, 4)))
        print(f"사전 {len(TECH_KEYWORDS)}개 / 본문 있는 공고 {with_text}개 중 "
              f"{covered}개({covered / with_text:.1%})에서 기술이 잡힘")

    if candidates and total:
        # 이미 있는 후보는 공고 수만 갱신하고, 처음 나타난 날짜(first_seen)는 그대로 둔다
        execute_values(cur, """
            INSERT INTO tech_candidates (term, doc_count, doc_ratio, example, first_seen, last_seen)
            VALUES %s
            ON CONFLICT (term) DO UPDATE SET
                doc_count = EXCLUDED.doc_count,
                doc_ratio = EXCLUDED.doc_ratio,
                example   = EXCLUDED.example,
                last_seen = EXCLUDED.last_seen
        """, [(term, docs, round(docs / total, 4), sample[:200], today, today)
              for term, docs, sample in candidates])

    # 이번에 갱신되지 않은 후보는 사전에 추가됐거나 검토 이력에서 제외된 것이므로 대기 목록에서 뺀다
    cur.execute("DELETE FROM tech_candidates WHERE last_seen < %s", (today,))
    removed = cur.rowcount

    conn.commit()
    cur.close()
    conn.close()
    print(f"검토 대기 후보 {len(candidates)}개 저장 (대기 목록에서 빠진 후보 {removed}개)")
    return len(candidates)


if __name__ == "__main__":
    update_dictionary_watch()