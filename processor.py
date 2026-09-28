import re
from db_connect import get_connection

# ── 기술 스택 키워드 사전 ─────────────────────────
# 본문 전체를 검사하기 시작하면서 오탐이 생기던 패턴을 고쳤다:
#   Java : "자바스크립트"에 걸리지 않게 함
#   Vue  : "인터뷰", "리뷰"의 "뷰"에 걸리지 않게 함
#   Node : "쿠버네티스 노드"의 "노드"에 걸리지 않도록 한글 패턴 제거
#   Go   : 영어 문장의 "go"에 걸리지 않게 대문자 "Go"만 인정
#   JS/TS: "Node.js", "Vue.js"의 ".js"에 걸려 JavaScript로 잘못 집계되던 문제
TECH_KEYWORDS = {
    # 언어
    "Python": [r"python", r"파이썬"],
    "Java": [r"\bjava\b", r"자바(?!\s*스크립트)"],
    "JavaScript": [r"javascript", r"(?<![\w.])js\b", r"자바스크립트"],
    "TypeScript": [r"typescript", r"(?<![\w.])ts\b", r"타입스크립트"],
    "Kotlin": [r"kotlin", r"코틀린"],
    "Swift": [r"swift"],
    "Go": [r"\bgolang\b", r"(?-i:\bGo\b)"],
    "C++": [r"c\+\+", r"\bcpp\b"],
    "C#": [r"c#"],
    "Scala": [r"scala"],
    "Rust": [r"\brust\b"],
    "PHP": [r"\bphp\b"],
    "Ruby": [r"\bruby\b", r"루비"],
    "R": [r"\bR언어\b", r"\bR프로그래밍\b"],

    # 백엔드 프레임워크
    "Spring": [r"spring\s*boot", r"\bspring\b", r"스프링"],
    "Django": [r"django", r"장고"],
    "FastAPI": [r"fastapi"],
    "Flask": [r"\bflask\b"],
    "Node.js": [r"node\.js", r"nodejs"],
    "NestJS": [r"nestjs", r"nest\.js"],
    "Express": [r"express\.js", r"\bexpress\b"],
    "Laravel": [r"laravel"],

    # 프론트엔드
    "React": [r"\breact\b", r"리액트"],
    "Vue": [r"\bvue\b", r"(?<![가-힣])뷰(?:를|는|와|과|로|가|도|의)?(?![가-힣])"],
    "Angular": [r"angular", r"앵귤러"],
    "Next.js": [r"next\.js", r"nextjs"],
    "Nuxt.js": [r"nuxt\.js", r"nuxtjs"],
    "Svelte": [r"svelte"],

    # DB
    "MySQL": [r"mysql"],
    "PostgreSQL": [r"postgresql", r"postgres"],
    "MongoDB": [r"mongodb", r"몽고"],
    "Redis": [r"\bredis\b"],
    "Elasticsearch": [r"elasticsearch", r"elastic"],
    "Oracle": [r"\boracle\b", r"오라클"],
    "MariaDB": [r"mariadb"],
    "SQLite": [r"sqlite"],
    "Cassandra": [r"cassandra"],

    # 클라우드
    "AWS": [r"\baws\b", r"amazon web", r"아마존"],
    "GCP": [r"\bgcp\b", r"google cloud", r"구글 클라우드"],
    "Azure": [r"\bazure\b", r"애저"],
    "NCP": [r"\bncp\b", r"네이버 클라우드"],

    # DevOps
    "Docker": [r"docker", r"도커"],
    "Kubernetes": [r"kubernetes", r"\bk8s\b", r"쿠버네티스"],
    "Linux": [r"linux", r"리눅스"],
    "Terraform": [r"terraform"],
    "Jenkins": [r"jenkins"],
    "GitHub Actions": [r"github\s*actions"],
    "Ansible": [r"ansible"],
    "Nginx": [r"nginx"],

    # 데이터
    "Pandas": [r"pandas"],
    "Spark": [r"\bspark\b"],
    "Kafka": [r"kafka", r"카프카"],
    "Airflow": [r"airflow"],
    "Hadoop": [r"hadoop"],
    "Hive": [r"\bhive\b"],
    "Flink": [r"\bflink\b"],
    "dbt": [r"\bdbt\b"],

    # ML/AI
    "TensorFlow": [r"tensorflow"],
    "PyTorch": [r"pytorch"],
    "Scikit-learn": [r"scikit.learn", r"sklearn"],
    "AI": [r"\bAI\b", r"인공지능", r"AI\s*개발", r"AI\s*서비스", r"AI\s*엔지니어"],
    "LLM": [r"\bllm\b", r"거대언어모델", r"chatgpt", r"gpt"],
    "MLOps": [r"mlops"],

    # 기타
    "REST API": [r"rest\s*api", r"restful"],
    "MSA": [r"\bmsa\b", r"마이크로서비스"],
    "CI/CD": [r"ci/cd", r"\bcicd\b"],
    "Git": [r"\bgit\b", r"깃"],
    "Jira": [r"\bjira\b"],
    "GraphQL": [r"graphql"],
    "gRPC": [r"\bgrpc\b"],
    "WebSocket": [r"websocket", r"웹소켓"],
}

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


def process_postings():
    """title + content 합쳐서 키워드 추출 후 저장"""
    conn = get_connection()
    cur = conn.cursor()

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

    total_keywords = 0
    for i, (posting_id, job_category, title, content) in enumerate(postings):
        try:
            # title + content 합쳐서 분석
            full_text = f"{title or ''} {content or ''}"

            # 필수·우대 섹션 분리
            required_text, preferred_text = split_required_preferred(full_text)

            # 키워드 추출
            required_keywords = extract_keywords(required_text)
            preferred_keywords = extract_keywords(preferred_text)
            all_keywords = required_keywords | preferred_keywords

            if not all_keywords:
                continue

            # 저장 (필수 섹션에도 나온 키워드는 필수로 본다)
            for keyword in all_keywords:
                is_required = keyword in required_keywords
                cur.execute("""
                    INSERT INTO tech_keywords
                        (posting_id, keyword, is_required, extracted_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT DO NOTHING
                """, (posting_id, keyword, is_required))
                total_keywords += 1

            if (i + 1) % 100 == 0:
                conn.commit()
                print(f"  {i+1}/{len(postings)} 처리 중...")

        except Exception as e:
            print(f"  공고 {posting_id} 처리 오류: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n완료! 총 {total_keywords}개 키워드 저장")


if __name__ == "__main__":
    print("=== 키워드 추출 시작 ===")
    process_postings()