import re
import sys
from psycopg2.extras import execute_values
from db_connect import get_connection
from taxonomy import TECH_KEYWORDS  # 기술 사전은 taxonomy.py에서 관리한다

# ── 섹션 제목 ─────────────────────────────────────
# 실제 사람인 공고 본문을 확인해 보니 "주요업무 / 자격요건 / 우대사항" 같은
# 제목이 일관되게 붙어 있다. 단어 하나("우대", "필수")로 나누면
# "이력서 (필수)", "보훈대상자 우대"처럼 다른 뜻에 걸리므로 제목 형태만 인정한다.
SECTION_HEADERS = [
    ("preferred", re.compile(r"우대\s*(?:사항|조건|역량|요건)")),
    ("required", re.compile(
        r"자격\s*요건|지원\s*자격|필수\s*(?:사항|역량|조건|요건)|주요\s*업무|담당\s*업무"
    )),
    # 기술 스택과 무관한 섹션: 이 구간의 키워드는 필수/우대 어느 쪽에도 넣지 않는다
    ("ignore", re.compile(
        r"근무\s*조건|근무\s*환경|전형\s*절차|채용\s*절차|접수\s*기간|접수\s*방법"
        r"|지원\s*방법|제출\s*서류|복리\s*후생"
    )),
]


def split_required_preferred(text):
    """
    본문을 섹션 제목 기준으로 (필수 텍스트, 우대 텍스트)로 나눈다.
      - 첫 제목 앞(공고 제목, 회사 소개): 필수로 본다
      - 자격요건 / 주요업무 / 담당업무 섹션: 필수
      - 우대사항 섹션: 우대
      - 근무조건 / 전형절차 등: 제외
    제목이 하나도 없으면 전체를 필수로 본다(우대를 구분할 근거가 없으므로).
    """
    if not text:
        return "", ""

    marks = []
    for kind, pattern in SECTION_HEADERS:
        for match in pattern.finditer(text):
            marks.append((match.start(), match.end(), kind))
    if not marks:
        return text, ""

    marks.sort()
    required_parts = [text[:marks[0][0]]]
    preferred_parts = []
    for i, (_, end, kind) in enumerate(marks):
        next_start = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        section = text[end:next_start]
        if kind == "required":
            required_parts.append(section)
        elif kind == "preferred":
            preferred_parts.append(section)
    return " ".join(required_parts), " ".join(preferred_parts)


def extract_keywords(text):
    """텍스트에서 기술 스택 키워드 추출"""
    found = set()
    if not text:
        return found
    for standard_name, patterns in TECH_KEYWORDS.items():
        for pattern in patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    found.add(standard_name)
                    break
            except re.error:
                continue
    return found


def process_postings(rebuild=False):
    """
    title + content 합쳐서 키워드 추출 후 저장.

    기본: 아직 키워드가 없는 공고만 처리한다(매일 자동 실행용).
    rebuild=True: tech_keywords를 비우고 전체 공고를 새 기술 사전으로 다시 분석한다.
                  사전(taxonomy.py)을 바꾼 뒤 한 번 실행한다.

    키워드 추출은 메모리에서 끝내고, DB에는 한꺼번에 저장한다. 클라우드 DB는 요청 한 번마다
    네트워크를 왕복하므로 키워드를 하나씩 저장하면 수만 번 왕복해 느리고, 그 사이 인터넷이
    끊기면 실패한다. 저장은 하나의 트랜잭션이라 중간에 실패하면 전체가 되돌아가고
    기존 키워드는 그대로 남는다.
    """
    conn = get_connection()
    cur = conn.cursor()

    if rebuild:
        cur.execute("TRUNCATE TABLE tech_keywords")

    # 아직 처리 안 된 공고 가져오기 (title도 함께)
    cur.execute("""
        SELECT p.posting_id, p.job_category, p.title, p.content
        FROM job_postings p
        WHERE NOT EXISTS (
            SELECT 1 FROM tech_keywords t
            WHERE t.posting_id = p.posting_id
        )
    """)

    postings = cur.fetchall()
    print(f"처리할 공고: {len(postings)}개")

    rows = []  # (posting_id, keyword, is_required)
    for posting_id, job_category, title, content in postings:
        try:
            # title + content 합쳐서 분석
            full_text = f"{title or ''} {content or ''}"

            # 필수·우대 섹션 분리
            required_text, preferred_text = split_required_preferred(full_text)

            # 키워드 추출
            required_keywords = extract_keywords(required_text)
            preferred_keywords = extract_keywords(preferred_text)
            all_keywords = required_keywords | preferred_keywords
        except Exception as e:
            if rebuild:
                # 전체 재분석은 전부 성공하거나 전부 취소한다(TRUNCATE까지 되돌아감)
                print(f"  공고 {posting_id} 처리 오류로 전체 재분석을 취소합니다: {e}")
                conn.rollback()
                raise
            print(f"  공고 {posting_id} 처리 오류: {e}")
            continue

        # 필수 섹션에도 나온 키워드는 필수로 본다
        for keyword in all_keywords:
            rows.append((posting_id, keyword, keyword in required_keywords))

    print(f"키워드 추출 완료: {len(postings)}개 공고에서 {len(rows)}개, DB에 저장합니다...")
    if rows:
        execute_values(
            cur,
            """
            INSERT INTO tech_keywords (posting_id, keyword, is_required, extracted_at)
            VALUES %s
            ON CONFLICT DO NOTHING
            """,
            rows,
            template="(%s, %s, %s, NOW())",
            page_size=1000,
        )

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n완료! 총 {len(rows)}개 키워드 저장")


if __name__ == "__main__":
    rebuild = "--rebuild" in sys.argv
    print("=== 키워드 추출 시작" + (" (전체 재분석)" if rebuild else "") + " ===")
    process_postings(rebuild=rebuild)