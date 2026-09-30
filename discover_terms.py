"""
기술 사전에 없는 기술 후보를 본문에서 찾는다. DB는 읽기만 하고 아무것도 바꾸지 않는다.

- 자격요건·우대사항·주요업무 구간의 영문 표기 중 사전에 없는 것을 공고 수 순으로 보여 준다.
- 사전이 본문 있는 공고의 몇 %에서 기술을 하나 이상 잡는지(커버리지)도 함께 출력한다.
- 결과는 term_candidates.csv로도 저장된다. 훑어보고 기술이 맞는 것만 taxonomy.py에 추가한다.

사용법:
    python discover_terms.py              최소 5개 공고에 나온 후보 상위 120개
    python discover_terms.py 8 200        최소 8개 공고, 상위 200개
"""
import csv
import re
import sys
from collections import Counter

from db_connect import get_connection
from processor import extract_keywords, split_required_preferred

MIN_BODY_LENGTH = 300  # 이보다 짧은 본문(이미지 위주 공고)은 분석에서 제외
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,29}")

# 기술은 아니지만 공고에 자주 나오는 영어 표현, 그리고 사전 항목이 쪼개져 나온 조각(CI/CD -> CI, CD)
STOPWORDS = {
    "and", "or", "the", "of", "in", "to", "for", "with", "on", "at", "by", "from", "is", "are",
    "be", "as", "an", "we", "you", "our", "your", "will", "can", "must", "should", "not", "all",
    "experience", "team", "teams", "work", "working", "ability", "skills", "skill", "knowledge",
    "understanding", "development", "developer", "developers", "engineer", "engineers",
    "engineering", "software", "backend", "frontend", "back-end", "front-end", "full", "stack",
    "fullstack", "senior", "junior", "lead", "manager", "service", "services", "system",
    "systems", "data", "cloud", "web", "app", "apps", "mobile", "application", "applications",
    "platform", "product", "products", "project", "projects", "business", "company", "global",
    "new", "etc", "ex", "eg", "ie", "vs", "co", "ltd", "inc", "corp", "it", "ci", "cd",
    "ui", "ux", "hr", "pm", "po", "ceo", "cto", "kpi", "okr", "toeic", "opic", "www", "com",
}


# 후보 목록을 검토해서 기술 사전에 넣지 않기로 한 표현. 다음 실행에서 다시 나오지 않게 기록해 둔다.
# (검토 결과를 바꾸고 싶으면 여기서 지우면 후보로 다시 나온다)
REVIEWED_SKIP = {
    # 범용 단어, 그리고 "Spring Boot", "React Native", "Vector DB"처럼 쪼개져 나온 조각
    "api", "db", "boot", "framework", "code", "native", "search", "server", "model", "graph",
    "language", "learning", "architecture", "tool", "core", "container", "security", "infra",
    "infrastructure", "tech", "network", "database", "query", "actions", "apache", "vector",
    "devops", "devsecops", "rest", "top-tier", "html5", "rdb", "elt", "google", "microsoft",
    # 개발 직무와 무관한 업무·산업 용어와 업무용 도구
    "b2b", "erp", "crm", "scm", "mes", "plc", "cad", "autocad", "iso", "ppt", "excel", "ms",
    "pc", "hw", "sw", "si", "pl", "os", "windows", "slack", "notion", "figma", "qa", "cs", "saas",
    "bi", "poc", "iot", "ax", "mart", "power",
    # 보안 솔루션·자격증 (개발자 취업 범위 밖)
    "isms", "isms-p", "cissp", "cisa", "waf", "ips", "dlp", "edr", "siem", "vpn", "ip", "tcp",
    # 데이터사이언스 세부 분야·분석 도구 (범위 밖)
    "nlp", "vision", "gpu", "tableau", "dw",
    "opencv", "vlm", "cuda", "transformer", "numpy", "mlflow", "mqtt", "npu",
    # 2차 검토: 범용 단어와 쪼개진 조각 ("Machine Learning", "Deep Learning" 등)
    "machine", "deep", "computer", "dl", "lake", "script", "pipeline", "end", "no", "no.1", "job",
    "client", "monitoring", "collaboration", "flow", "solution", "architect", "professional",
    "hybrid", "batch", "streaming", "foundation", "admin", "context", "research", "life",
    "position", "function", "orchestration", "center", "object", "protocol", "feature", "studio",
    "intelligence", "digital", "e-commerce", "analytics", "certified", "pdf", "sdk", "dbms",
    "net", "typesc", "javasc", "ript",
    # 2차 검토: 영업·마케팅·제조·품질·하드웨어·보안 운영 등 개발 직무가 아닌 공고의 용어
    "cctv", "nac", "idc", "dx", "amazon", "b2c", "iam", "se", "seo", "iso27001", "sap", "sk",
    "oa", "mcu", "sns", "qc", "drm", "cx", "emr", "pr", "sm", "ids", "pcb", "fw", "wms", "ir",
    "nvidia", "analyst", "physical", "dns", "unix", "md", "pg", "ocr", "detection", "ga4", "sop",
    "ict", "dm",
    # 2차 검토: 개발 기술이지만 빈도가 2% 미만이라 이번에는 제외 (필요하면 지우고 다시 검토)
    "spa", "ssr", "es6+", "was", "dag", "slo", "vpc", "ecr", "iceberg", "istio",
}

# 사전 확장 종료 기준: 가장 흔한 후보도 전체 공고의 이 비율 미만이면 사전이 충분히 수렴한 것으로 본다
CONVERGED_BELOW = 0.02


def find_candidates(texts, min_docs=5, top=120):
    """
    texts: 공고별 본문(필수+우대 구간) 목록.
    반환: [(후보, 나온 공고 수, 예문), ...]  공고 수가 많은 순.
    """
    doc_freq = Counter()   # 후보가 나온 공고 수
    exact = Counter()      # 표기 그대로(대소문자 구분) 나온 총 횟수
    first_seen = {}        # 후보별 예문

    for text in texts:
        seen = set()
        for match in TOKEN_RE.finditer(text):
            token = match.group().rstrip(".-")
            if len(token) < 2:
                continue
            exact[token] += 1
            if token not in seen:
                seen.add(token)
                first_seen.setdefault(token, text[max(0, match.start() - 25): match.end() + 40])
        doc_freq.update(seen)

    candidates = []
    for token, docs in doc_freq.most_common():
        if docs < min_docs:
            break
        lower = token.lower()
        # 이미 사전에 있거나, 기술이 아닌 흔한 표현
        if lower in STOPWORDS or lower in REVIEWED_SKIP or extract_keywords(token):
            continue
        # 기술 이름은 대문자·숫자·기호(+ # .)를 포함하는 경우가 대부분이라, 소문자 일반 단어는 제외
        if not (any(c.isupper() for c in token) or any(c.isdigit() or c in "+#." for c in token)):
            continue
        # 문장 첫머리의 대문자 표기("Team")처럼, 소문자로도 자주 쓰이는 일반 단어는 제외
        if lower != token and exact.get(lower, 0) >= 0.3 * exact[token]:
            continue
        sample = re.sub(r"\s+", " ", first_seen[token])
        candidates.append((token, docs, sample))
        if len(candidates) >= top:
            break
    return candidates


def coverage(texts):
    """사전이 기술을 하나 이상 잡은 공고 수와 전체 공고 수."""
    covered = sum(1 for text in texts if extract_keywords(text))
    return covered, len(texts)


def load_texts():
    """본문이 있는 사람인 공고를 (같은 공고는 한 번만) 읽어 필수+우대 구간 텍스트로 만든다."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (post_url) content
        FROM job_postings
        WHERE source = '사람인' AND LENGTH(content) >= %s
        ORDER BY post_url
    """, (MIN_BODY_LENGTH,))
    texts = []
    for (content,) in cur.fetchall():
        required, preferred = split_required_preferred(content)
        texts.append(f"{required} {preferred}")
    cur.close()
    conn.close()
    return texts


def main():
    min_docs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    top = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    texts = load_texts()
    if not texts:
        print("본문이 있는 공고가 없습니다.")
        return

    covered, total = coverage(texts)
    print(f"본문이 있는 공고 {total}개 중 {covered}개({covered / total:.1%})에서 "
          f"사전의 기술이 하나 이상 잡힘")
    print(f"나머지 {total - covered}개({(total - covered) / total:.1%})는 사전으로 잡히는 기술이 없음\n")

    candidates = find_candidates(texts, min_docs=min_docs, top=top)
    if candidates:
        top_ratio = candidates[0][1] / total
        if top_ratio < CONVERGED_BELOW:
            print(f"확장 종료 기준 충족: 검토하지 않은 후보 중 가장 흔한 '{candidates[0][0]}'도 "
                  f"전체 공고의 {top_ratio:.1%}({CONVERGED_BELOW:.0%} 미만)입니다. 사전은 충분히 수렴했습니다.\n")
        else:
            print(f"확장 계속: 가장 흔한 후보 '{candidates[0][0]}'가 전체 공고의 {top_ratio:.1%}"
                  f"({CONVERGED_BELOW:.0%} 이상)입니다.\n")
    else:
        print("검토하지 않은 후보가 없습니다. 사전은 충분히 수렴했습니다.\n")
    print(f"사전에 없는 후보 (최소 {min_docs}개 공고, 상위 {len(candidates)}개)")
    print("기술이 맞는 것만 taxonomy.py에 추가하세요. 회사명·약어 등은 무시하면 됩니다.\n")
    for rank, (term, docs, sample) in enumerate(candidates, start=1):
        print(f"{rank:>3}. {term:<24}{docs:>5}개 ({docs / total:.1%})   ...{sample}...")

    with open("term_candidates.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["후보", "공고 수", "비율", "예문"])
        for term, docs, sample in candidates:
            writer.writerow([term, docs, f"{docs / total:.1%}", sample])
    print("\nterm_candidates.csv 저장 완료")


if __name__ == "__main__":
    main()