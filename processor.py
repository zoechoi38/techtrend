import re
from db_connect import get_connection

# ── 기술 스택 키워드 사전 ─────────────────────────
TECH_KEYWORDS = {
    # 언어
    "Python": [r"python", r"파이썬"],
    "Java": [r"\bjava\b", r"자바"],
    "JavaScript": [r"javascript", r"\bjs\b", r"자바스크립트"],
    "TypeScript": [r"typescript", r"\bts\b", r"타입스크립트"],
    "Kotlin": [r"kotlin", r"코틀린"],
    "Swift": [r"swift"],
    "Go": [r"\bgolang\b", r"\bgo\b"],
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
    "Node.js": [r"node\.js", r"nodejs", r"노드"],
    "NestJS": [r"nestjs", r"nest\.js"],
    "Express": [r"express\.js", r"\bexpress\b"],
    "Laravel": [r"laravel"],

    # 프론트엔드
    "React": [r"\breact\b", r"리액트"],
    "Vue": [r"\bvue\b", r"뷰"],
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

REQUIRED_PATTERNS = [
    r"자격\s*요건", r"필수\s*사항", r"필수\s*역량",
    r"필수\s*조건", r"주요\s*업무", r"담당\s*업무"
]

PREFERRED_PATTERNS = [
    r"우대\s*사항", r"우대\s*조건", r"우대\s*역량", r"우대"
]


def split_required_preferred(text):
    """텍스트를 필수·우대 섹션으로 분리"""
    if not text:
        return text, ""

    preferred_start = len(text)
    for pattern in PREFERRED_PATTERNS:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            preferred_start = min(preferred_start, matches[0].start())

    required_text = text[:preferred_start]
    preferred_text = text[preferred_start:]
    return required_text, preferred_text


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

            # 저장
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
