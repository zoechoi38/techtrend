import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date
import time
from db_connect import get_connection

AUTH_KEY = "67a465be-968e-4c58-badb-65a082d1cfb8"
BASE_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"

# 직무별 키워드
JOB_CATEGORIES = {
    "백엔드 개발자": "백엔드",
    "프론트엔드 개발자": "프론트엔드",
    "데이터 엔지니어": "데이터엔지니어",
    "데이터 분석가": "데이터분석",
    "ML 엔지니어": "머신러닝",
    "DevOps": "devops",
    "보안 엔지니어": "보안"
}


def fetch_worknet(keyword, start_page=1, display=100):
    """워크넷 API 호출"""
    params = {
        "authKey": AUTH_KEY,
        "callTp": "L",
        "returnType": "XML",
        "startPage": start_page,
        "display": display,
        "keyword": keyword,
        "sortOrderBy": "ASC"  # 오래된 순으로
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=15)
        response.encoding = "utf-8"

        if response.status_code != 200:
            print(f"  API 오류: {response.status_code}")
            return []

        root = ET.fromstring(response.text)
        postings = []

        for wanted in root.findall(".//wanted"):
            try:
                title = wanted.findtext("title", "").strip()
                company = wanted.findtext("company", "").strip()
                url = wanted.findtext("wantedInfoUrl", "").strip()
                reg_dt = wanted.findtext("regDt", "").strip()

                if not title or not url:
                    continue

                # 날짜 파싱
                try:
                    if len(reg_dt) == 8:  # YYYYMMDD
                        posted_date = datetime.strptime(reg_dt, "%Y%m%d").date()
                    else:
                        posted_date = date.today()
                except:
                    posted_date = date.today()

                postings.append({
                    "source": "워크넷",
                    "company_name": company or "unknown",
                    "title": title,
                    "content": "",
                    "post_url": url,
                    "posted_date": posted_date
                })

            except Exception as e:
                continue

        return postings

    except Exception as e:
        print(f"  API 요청 오류: {e}")
        return []


def save_to_db(postings, job_category):
    if not postings:
        return 0

    conn = get_connection()
    cur = conn.cursor()
    saved = 0

    for p in postings:
        try:
            cur.execute("""
                INSERT INTO job_postings
                    (source, job_category, company_name, title, content, post_url, posted_date, collected_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (post_url) DO NOTHING
            """, ("워크넷", job_category, p["company_name"],
                  p["title"], p["content"], p["post_url"], p["posted_date"]))
            saved += cur.rowcount
        except Exception as e:
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()
    return saved

if __name__ == "__main__":
 # API 응답 원문 확인용
    import urllib.request
    import urllib.parse

    params = f"authKey={AUTH_KEY}&callTp=L&returnType=XML&startPage=1&display=10&keyword={urllib.parse.quote('백엔드')}&sortOrderBy=ASC"
    response = requests.get(BASE_URL, params=params, timeout=15)
    response.encoding = "utf-8"
    print(response.text[:3000])

    for job_category, keyword in JOB_CATEGORIES.items():
        print(f"\n[{job_category}] 수집 중...")
        all_postings = []

        # 최대 10페이지 수집 (1000건)
        for page in range(1, 11):
            postings = fetch_worknet(keyword, start_page=page, display=100)
            if not postings:
                print(f"  {page}페이지 데이터 없음, 종료")
                break
            all_postings.extend(postings)
            print(f"  {page}페이지 완료 ({len(postings)}개)")
            time.sleep(0.5)

        saved = save_to_db(all_postings, job_category)
        print(f"  수집 {len(all_postings)}개 / 저장 {saved}개")
        total += saved
        time.sleep(1)

    print(f"\n전체 완료! 총 {total}개 저장")