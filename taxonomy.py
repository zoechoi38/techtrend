import re

TECH_TAXONOMY = {
    "프로그래밍 언어": {
        "Python": [r"python", r"파이썬"],
        "Java": [r"\bjava\b", r"자바(?!\s*스크립트)"],
        "JavaScript": [r"javascript", r"javasc\s*ript", r"(?<![A-Za-z0-9_.])js\b", r"자바스크립트"],
        "TypeScript": [r"typescript", r"typesc\s*ript", r"(?<![A-Za-z0-9_.])ts\b", r"타입스크립트"],
        "Kotlin": [r"kotlin", r"코틀린"],
        "Swift": [r"swift"],
        "Go": [r"\bgolang\b", r"(?-i:\bGo\b)"],
        "C++": [r"c\+\+", r"\bcpp\b"],
        "C#": [r"c#"],
        "C": [r"(?-i:\bC)\s*언어", r"(?-i:\bC)\s*/\s*C\+\+"],
        "Scala": [r"scala"],
        "Rust": [r"\brust\b"],
        "PHP": [r"\bphp\b"],
        "Ruby": [r"\bruby\b", r"루비"],
        "R": [r"\bR언어\b", r"\bR프로그래밍\b"],
    },
    "백엔드 프레임워크": {
        "Spring": [r"spring\s*boot", r"\bspring\b", r"스프링"],
        "JPA": [r"\bjpa\b", r"hibernate"],
        "MyBatis": [r"mybatis", r"마이바티스"],
        "Django": [r"django", r"장고"],
        "FastAPI": [r"fastapi"],
        "Flask": [r"\bflask\b"],
        "Node.js": [r"node\.js", r"nodejs"],
        "NestJS": [r"nestjs", r"nest\.js"],
        "Express": [r"express\.js", r"\bexpress\b"],
        "Laravel": [r"laravel"],
        ".NET": [r"\.net\b", r"닷넷", r"\bnet\s+core\b"],
        "ORM": [r"\borm\b", r"typeorm", r"\bprisma\b", r"sqlalchemy"],
        "JSP": [r"\bjsp\b"],
    },
    "프론트엔드": {
        "React": [r"\breact\b", r"리액트"],
        "Vue": [r"\bvue\b", r"(?<![가-힣])뷰(?:를|는|와|과|로|가|도|의)?(?![가-힣])"],
        "Angular": [r"angular", r"앵귤러"],
        "Next.js": [r"next\.js", r"nextjs"],
        "Nuxt.js": [r"nuxt\.js", r"nuxtjs"],
        "Svelte": [r"svelte"],
        "HTML": [r"\bhtml5?\b"],
        "CSS": [r"\bcss3?\b"],
        "React Query": [r"react\s*query", r"tanstack\s*query"],
        "Zustand": [r"zustand"],
        "Redux": [r"redux"],
        "Tailwind": [r"tailwind"],
        "Vite": [r"\bvite\b"],
    },
    "모바일": {
        "Flutter": [r"flutter", r"플러터"],
        "React Native": [r"react\s*native", r"리액트\s*네이티브"],
        "Android": [r"\bandroid\b", r"안드로이드"],
        "iOS": [r"\bios\b"],
    },
    "데이터베이스": {
        "SQL": [r"\bsql\b"],
        "RDBMS": [r"\brdbms\b", r"\brdb\b", r"관계형\s*데이터베이스"],
        "NoSQL": [r"\bnosql\b"],
        "MSSQL": [r"\bms[\s-]?sql\b", r"mssql"],
        "MySQL": [r"mysql"],
        "PostgreSQL": [r"postgresql", r"postgres"],
        "MongoDB": [r"mongodb", r"몽고"],
        "Redis": [r"\bredis\b"],
        "Elasticsearch": [r"elasticsearch", r"elastic"],
        "Oracle": [r"\boracle\b", r"오라클"],
        "MariaDB": [r"mariadb"],
        "SQLite": [r"sqlite"],
        "Cassandra": [r"cassandra"],
    },
    "클라우드": {
        "AWS": [r"\baws\b", r"amazon web", r"아마존"],
        "GCP": [r"\bgcp\b", r"google cloud", r"구글 클라우드"],
        "Azure": [r"\bazure\b", r"애저"],
        "NCP": [r"\bncp\b", r"네이버 클라우드"],
        "EC2": [r"\bec2\b"],
        "S3": [r"\bs3\b"],
        "RDS": [r"\brds\b"],
        "EKS": [r"\beks\b"],
        "ECS": [r"\becs\b"],
        "Lambda": [r"\blambda\b"],
        "CloudWatch": [r"cloudwatch"],
        "CloudFormation": [r"cloudformation"],
    },
    "DevOps·인프라": {
        "Docker": [r"docker", r"도커"],
        "Kubernetes": [r"kubernetes", r"\bk8s\b", r"쿠버네티스"],
        "Linux": [r"linux", r"리눅스"],
        "Terraform": [r"terraform"],
        "Jenkins": [r"jenkins"],
        "GitHub Actions": [r"github\s*actions"],
        "Ansible": [r"ansible"],
        "Nginx": [r"nginx"],
        "CI/CD": [r"ci/cd", r"\bcicd\b"],
        "GitHub": [r"\bgithub(?!\s*actions)\b"],
        "GitLab": [r"\bgitlab\b"],
        "IaC": [r"\biac\b", r"infrastructure\s+as\s+code"],
        "ArgoCD": [r"argo\s*cd"],
        "GitOps": [r"gitops"],
        "Helm": [r"\bhelm\b"],
        "Prometheus": [r"prometheus"],
        "Grafana": [r"grafana"],
        "Datadog": [r"datadog"],
        "ELK": [r"\belk\b"],
        "OpenSearch": [r"opensearch"],
        "SRE": [r"\bsre\b"],
        "Shell": [r"\bshell\b", r"\bbash\b", r"셸"],
        "Observability": [r"observability", r"옵저버빌리티"],
    },
    "데이터 엔지니어링": {
        "Pandas": [r"pandas"],
        "Spark": [r"\bspark\b"],
        "Kafka": [r"kafka", r"카프카"],
        "Airflow": [r"airflow"],
        "Hadoop": [r"hadoop"],
        "Hive": [r"\bhive\b"],
        "Flink": [r"\bflink\b"],
        "dbt": [r"\bdbt\b"],
        "ETL·ELT": [r"\betl\b", r"\belt\b"],
        "Databricks": [r"databricks"],
        "BigQuery": [r"bigquery"],
        "Snowflake": [r"snowflake"],
        "RabbitMQ": [r"rabbitmq"],
    },
    "AI·ML": {
        "AI": [r"\bAI\b", r"인공지능", r"AI\s*개발", r"AI\s*서비스", r"AI\s*엔지니어"],
        # "ML"은 대문자일 때만 인정한다("500 ml" 같은 용량 표기에 걸리지 않도록)
        "머신러닝": [r"머신\s*러닝", r"machine\s*learning", r"(?-i:\bML\b)"],
        # 단독 "DL"은 DL이앤씨 같은 회사명에 걸리므로 "ML/DL"처럼 짝지어 나올 때만 인정한다
        "딥러닝": [r"딥\s*러닝", r"deep\s*learning", r"(?-i:\bML\s*/\s*DL\b)"],
        "NLP·자연어처리": [r"\bnlp\b", r"자연어\s*처리", r"natural\s*language"],
        "컴퓨터 비전": [r"컴퓨터\s*비전", r"computer\s*vision", r"opencv", r"\byolo\b"],
        "GPU·CUDA": [r"\bgpu\b", r"cuda"],
        "LLM": [
            r"\bllm\b", r"거대언어모델", r"chatgpt", r"gpt",
            r"생성형\s*ai", r"generative\s*ai", r"langchain", r"\brag\b",
            r"openai", r"anthropic", r"claude(?!\s*code)",
            r"langgraph", r"vllm", r"ollama", r"gemini",
        ],
        # 개발자가 업무에서 접하는 AI: 코딩 도구, 에이전트, 벡터 DB
        "AI 코딩 도구": [r"claude\s*code", r"\bcursor\b", r"copilot", r"\bcodex\b", r"windsurf"],
        "AI 에이전트": [r"ai\s*agent", r"agentic", r"에이전트", r"\bmcp\b", r"(?-i:\bAgents?\b)"],
        "벡터 DB": [r"vector\s*(?:db|database|store)", r"벡터\s*(?:db|데이터베이스)", r"pgvector", r"pinecone"],
        "TensorFlow": [r"tensorflow"],
        "PyTorch": [r"pytorch"],
        "Scikit-learn": [r"scikit.learn", r"sklearn"],
        "MLOps": [r"mlops", r"mlflow", r"kubeflow"],
    },
    "아키텍처·협업": {
        "REST API": [r"rest\s*api", r"restful", r"(?-i:\bREST\b)"],
        "Swagger·OpenAPI": [r"swagger", r"openapi"],
        "MSA": [r"\bmsa\b", r"마이크로서비스"],
        "GraphQL": [r"graphql"],
        "gRPC": [r"\bgrpc\b"],
        "WebSocket": [r"websocket", r"웹소켓"],
        "Git": [r"\bgit\b", r"깃"],
        "Jira": [r"\bjira\b"],
        "Confluence": [r"confluence"],
    },
}

_WORD_START = r"(?<![A-Za-z0-9_])"
_WORD_END = r"(?![A-Za-z0-9_])"


def _ascii_boundaries(pattern):
    """
    \\b를 '영문·숫자·밑줄만 글자로 보는' 경계로 바꾼다.
    토큰 앞(패턴 맨 앞, 또는 '(' ':' '|' 바로 뒤)의 \\b는 직전 글자가 영문·숫자가 아닐 것,
    그 밖의 \\b는 다음 글자가 영문·숫자가 아닐 것으로 바뀐다.
    """
    def replace(match):
        previous = pattern[match.start() - 1] if match.start() > 0 else ""
        return _WORD_START if previous in ("", "(", ":", "|") else _WORD_END

    return re.sub(r"\\b", replace, pattern)


# 기존 코드(processor.py의 extract_keywords)가 쓰는 평평한 사전: {세부 기술: [패턴, ...]}
TECH_KEYWORDS = {
    tech: [_ascii_boundaries(p) for p in patterns]
    for techs in TECH_TAXONOMY.values()
    for tech, patterns in techs.items()
}

# 세부 기술 -> 대분류 (대시보드에서 대분류별로 묶어 볼 때 사용)
CATEGORY_OF = {
    tech: category
    for category, techs in TECH_TAXONOMY.items()
    for tech in techs
}


def _validate():
    """같은 기술이 두 대분류에 중복 등록되면 통계가 이중으로 잡히므로 바로 막는다."""
    total = sum(len(techs) for techs in TECH_TAXONOMY.values())
    if total != len(TECH_KEYWORDS):
        raise ValueError("같은 기술이 둘 이상의 대분류에 들어 있습니다")


_validate()