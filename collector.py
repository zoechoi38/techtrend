import requests
from bs4 import BeautifulSoup
from datetime import date
import time
import json
import os
import logging
from db_connect import get_connection
from saramin_utils import (
    canonical_saramin_url, parse_list_date, extract_rec_idx,
    fetch_saramin_body, needs_body,
)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ── 로깅 설정 ─────────────────────────────────
logging.basicConfig(
    filename="crawler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)
logger = logging.getLogger(__name__)

# 원티드는 현재 수집이 거의 되지 않는다(DB에 43건). 결정이 나기 전까지는 그대로 켜 둔다.
COLLECT_WANTED = True

JOB_CATEGORIES = {
    "백엔드 개발자": "백엔드",
    "프론트엔드 개발자": "프론트엔드",
    "데이터 엔지니어": "데이터엔지니어",
    "데이터 분석가": "데이터분석",
    "ML 엔지니어": "머신러닝",
    "DevOps": "devops",
    "보안 엔지니어": "보안"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 사이트가 요청을 제한(403/429)하면 그날은 본문 수집을 멈춘다
fetch_state = {"blocked": False}


def load_known_bodies():
    """이미 본문을 받아 둔 사람인 공고 {post_url: content}. 같은 공고를 다시 요청하지 않기 위함."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT post_url, content FROM job_postings WHERE source = '사람인'")
    bodies = {url: content for url, content in cur.fetchall() if not needs_body(content)}
    cur.close()
    conn.close()
    return bodies


def save_raw_json(postings, source, job_category):
    today = date.today().strftime("%Y-%m-%d")
    folder = f"raw_data/{today}"
    os.makedirs(folder, exist_ok=True)
    safe_category = job_category.replace(" ", "_").replace("/", "_")
    filename = f"{folder}/{source}_{safe_category}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(postings, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Raw JSON 저장 완료: {filename} ({len(postings)}개)")
    print(f"  Raw JSON 저장: {filename}")

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver

def crawl_saramin(job_category, keyword, pages=3, bodies=None):
    bodies = bodies if bodies is not None else {}
    postings = []
    logger.info(f"사람인 크롤링 시작: {job_category} / {keyword}")

    for page in range(1, pages + 1):
        url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchType=search&searchword={keyword}&recruitPage={page}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select(".item_recruit")

            if not items:
                print(f"  {page}페이지 공고 없음, 종료")
                break

            for item in items:
                try:
                    title_tag = item.select_one(".job_tit a")
                    if not title_tag:
                        continue
                    title = title_tag.get_text(strip=True)

                    # 검색마다 바뀌는 파라미터(search_uuid 등)를 제거해 같은 공고는
                    # 항상 같은 URL로 저장한다 -> DB의 중복 방지가 정상 동작
                    post_url = canonical_saramin_url(
                        "https://www.saramin.co.kr" + title_tag["href"]
                    )

                    company_tag = item.select_one(".corp_name a")
                    company_name = company_tag.get_text(strip=True) if company_tag else "unknown"

                    # 목록에 표시된 실제 등록일/수정일. 못 찾으면 수집일로 대체
                    _, listed_date = parse_list_date(item.get_text(" ", strip=True))
                    posted_date = listed_date or date.today()

                    # 상세 본문: 이미 받아 둔 공고는 재사용하고, 새 공고만 요청한다
                    content = bodies.get(post_url, "")
                    rec_idx = extract_rec_idx(post_url)
                    if post_url not in bodies and rec_idx and not fetch_state["blocked"]:
                        status, body = fetch_saramin_body(rec_idx)
                        time.sleep(1)
                        if status in (403, 429):
                            fetch_state["blocked"] = True
                            logger.error(f"사람인 본문 요청 제한(status={status}), 오늘은 본문 수집 중단")
                        elif body is not None:
                            content = body
                            bodies[post_url] = body

                    postings.append({
                        "source": "사람인",
                        "job_category": job_category,
                        "company_name": company_name,
                        "title": title,
                        "content": content,
                        "post_url": post_url,
                        "posted_date": str(posted_date)
                    })
                except Exception as e:
                    logger.error(f"사람인 공고 파싱 오류: {e}")
                    continue

            print(f"  {page}페이지 완료 ({len(items)}개)")
            time.sleep(1)

        except Exception as e:
            print(f"  {page}페이지 요청 오류: {e}")
            continue

    return postings

def crawl_wanted(job_category, keyword, pages=3):
    postings = []
    logger.info(f"원티드 크롤링 시작: {job_category} / {keyword}")
    driver = get_driver()

    try:
        url = f"https://www.wanted.co.kr/search?query={keyword}&tab=position"
        driver.get(url)
        time.sleep(3)

        for _ in range(pages):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        items = (
            soup.select("li[class*='Card']") or
            soup.select("[class*='JobCard']") or
            soup.select("li[class*='card']")
        )

        print(f"  공고 {len(items)}개 발견")

        for item in items:
            try:
                title_tag = (
                    item.select_one("[class*='title']") or
                    item.select_one("strong") or
                    item.select_one("h2")
                )
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if not title:
                    continue

                company_tag = (
                    item.select_one("[class*='company']") or
                    item.select_one("[class*='corp']")
                )
                company_name = company_tag.get_text(strip=True) if company_tag else "unknown"

                link_tag = item.select_one("a")
                href = link_tag.get("href", "") if link_tag else ""
                post_url = "https://www.wanted.co.kr" + href if href.startswith("/") else href

                if not post_url:
                    continue

                # 상세페이지 본문 추출
                content = ""
                try:
                    driver.get(post_url)
                    time.sleep(2)
                    detail_soup = BeautifulSoup(driver.page_source, "html.parser")
                    detail_div = (
                        detail_soup.select_one("[class*='JobDescription']") or
                        detail_soup.select_one("[class*='job-description']") or
                        detail_soup.select_one("[class*='content']")
                    )
                    if detail_div:
                        content = detail_div.get_text(separator=" ", strip=True)
                    driver.back()
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"원티드 상세페이지 오류: {e}")

                postings.append({
                    "source": "원티드",
                    "job_category": job_category,
                    "company_name": company_name,
                    "title": title,
                    "content": content,
                    "post_url": post_url,
                    "posted_date": str(date.today())
                })
            except Exception as e:
                logger.error(f"원티드 공고 파싱 오류: {e}")
                continue

    except Exception as e:
        logger.error(f"원티드 크롤링 오류: {job_category} / {e}")
        print(f"  원티드 오류: {e}")
    finally:
        driver.quit()

    logger.info(f"원티드 크롤링 완료: {job_category} {len(postings)}개")
    return postings

def save_to_db(postings):
    if not postings:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    saved = 0
    for p in postings:
        try:
            # 충돌 대상을 지정하지 않아 어떤 UNIQUE 제약이든 중복이면 건너뜀
            cur.execute("""
                INSERT INTO job_postings
                    (source, job_category, company_name, title, content, post_url, posted_date, collected_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
            """, (p["source"], p["job_category"], p["company_name"],
                  p["title"], p["content"], p["post_url"], p["posted_date"]))
            saved += cur.rowcount
        except Exception as e:
            logger.error(f"DB 저장 오류: {e}")
            conn.rollback()
            continue
    conn.commit()
    cur.close()
    conn.close()
    return saved

def run_collection():
    """
    사람인 -> 원티드 순으로 수집해 DB에 저장하고, 새로 저장된 총 개수를 돌려준다.
    직무 하나가 실패해도 나머지는 계속 진행한다.
    """
    # 프로세스가 계속 떠 있는 스케줄러에서는 어제 걸린 요청 제한 표시가 남아 있으면
    # 본문 수집이 영원히 멈추므로, 수집을 시작할 때마다 초기화한다.
    fetch_state["blocked"] = False
    logger.info("=== 수집 시작 ===")
    total = 0

    print("=== 사람인 수집 시작 ===")
    # 이미 본문을 받아 둔 공고는 다시 요청하지 않는다(새 공고만 요청)
    bodies = load_known_bodies()
    for job_category, keyword in JOB_CATEGORIES.items():
        print(f"\n[{job_category}] 크롤링 시작...")
        try:
            postings = crawl_saramin(job_category, keyword, pages=3, bodies=bodies)
            save_raw_json(postings, "saramin", job_category)
            saved = save_to_db(postings)
            print(f"  수집 {len(postings)}개 / 저장 {saved}개")
            total += saved
        except Exception as e:
            logger.exception(f"사람인 수집 실패: {job_category}")
            print(f"  사람인 수집 실패: {e}")
        time.sleep(2)

    if COLLECT_WANTED:
        print("\n=== 원티드 수집 시작 ===")
        for job_category, keyword in JOB_CATEGORIES.items():
            print(f"\n[{job_category}] 크롤링 시작...")
            try:
                postings = crawl_wanted(job_category, keyword, pages=3)
                save_raw_json(postings, "wanted", job_category)
                saved = save_to_db(postings)
                print(f"  수집 {len(postings)}개 / 저장 {saved}개")
                total += saved
            except Exception as e:
                logger.exception(f"원티드 수집 실패: {job_category}")
                print(f"  원티드 수집 실패: {e}")
            time.sleep(2)

    logger.info(f"=== 수집 완료: 총 {total}개 ===")
    print(f"\n전체 완료! 총 {total}개 저장")
    return total


if __name__ == "__main__":
    run_collection()