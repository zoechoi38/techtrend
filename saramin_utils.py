import re
from datetime import date
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

SARAMIN_VIEW_URL = "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={}"
SARAMIN_DETAIL_URL = (
    "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={}&rec_seq=0"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 목록 페이지에 "등록일 26/09/28" 또는 "수정일 26/09/28" 형태로 표시되는 날짜
_DATE_RE = re.compile(r"(등록일|수정일)\s*(\d{2})/(\d{1,2})/(\d{1,2})")
# 예전 collector가 content에 그대로 저장하던 날짜 문구 전체
_OLD_LABEL_RE = re.compile(r"\s*(등록일|수정일)\s*\d{2}/\d{1,2}/\d{1,2}\s*")


def extract_rec_idx(url):
    """사람인 공고 고유번호(rec_idx)를 URL에서 꺼낸다. 없으면 None."""
    values = parse_qs(urlparse(url).query).get("rec_idx")
    return values[0] if values else None


def canonical_saramin_url(url):
    """
    검색할 때마다 바뀌는 파라미터(search_uuid 등)를 제거하고
    공고 고유번호(rec_idx)만 남긴 URL로 통일한다.
    같은 공고가 매번 다른 URL로 저장돼 중복 방지가 안 되던 문제를 막는다.
    """
    rec_idx = extract_rec_idx(url)
    if rec_idx:
        return SARAMIN_VIEW_URL.format(rec_idx)
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def parse_list_date(text):
    """
    목록 항목 텍스트에서 (구분, 날짜)를 꺼낸다.
    구분은 '등록일' 또는 '수정일'. 못 찾으면 (None, None).
    """
    match = _DATE_RE.search(text or "")
    if not match:
        return None, None
    kind, yy, mm, dd = match.groups()
    try:
        return kind, date(2000 + int(yy), int(mm), int(dd))
    except ValueError:
        return None, None


def needs_body(content):
    """본문이 아직 수집되지 않은 상태인가: 비어 있거나 예전 날짜 문구뿐인 경우."""
    if not content:
        return True
    return _OLD_LABEL_RE.fullmatch(content) is not None


def fetch_saramin_body(rec_idx, timeout=10):
    """
    공고 상세 본문을 받아 (HTTP 상태코드, 본문 텍스트)를 돌려준다.
    네트워크 오류면 (None, None). 본문이 이미지뿐이면 짧은 텍스트가 온다.
    """
    view_url = SARAMIN_VIEW_URL.format(rec_idx)
    try:
        response = requests.get(
            SARAMIN_DETAIL_URL.format(rec_idx),
            headers={**HEADERS, "Referer": view_url},
            timeout=timeout,
        )
    except requests.RequestException:
        return None, None
    if response.status_code != 200:
        return response.status_code, None
    soup = BeautifulSoup(response.text, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    return 200, text