import schedule
import time
import logging
from collector import crawl_saramin, crawl_wanted, save_raw_json, save_to_db, JOB_CATEGORIES

# ── 로깅 설정 ─────────────────────────────────
logging.basicConfig(
    filename="crawler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)
logger = logging.getLogger(__name__)


def run_collect():
    """매일 자동 실행되는 수집 함수"""
    logger.info("=== 자동 수집 시작 ===")
    print("=== 자동 수집 시작 ===")
    total = 0

    # 사람인 수집
    print("\n=== 사람인 수집 시작 ===")
    for job_category, keyword in JOB_CATEGORIES.items():
        print(f"\n[{job_category}] 크롤링 시작...")
        postings = crawl_saramin(job_category, keyword, pages=3)
        save_raw_json(postings, "saramin", job_category)
        saved = save_to_db(postings)
        print(f"  수집 {len(postings)}개 / 저장 {saved}개")
        total += saved
        time.sleep(2)

    # 원티드 수집
    print("\n=== 원티드 수집 시작 ===")
    for job_category, keyword in JOB_CATEGORIES.items():
        print(f"\n[{job_category}] 크롤링 시작...")
        postings = crawl_wanted(job_category, keyword, pages=3)
        save_raw_json(postings, "wanted", job_category)
        saved = save_to_db(postings)
        print(f"  수집 {len(postings)}개 / 저장 {saved}개")
        total += saved
        time.sleep(2)

    logger.info(f"=== 자동 수집 완료: 총 {total}개 ===")
    print(f"\n전체 완료! 총 {total}개 저장")


# 매일 오전 9시에 자동 실행
schedule.every().day.at("09:00").do(run_collect)

if __name__ == "__main__":
    print("스케줄러 시작 — 매일 09:00 자동 수집")
    print("종료하려면 Ctrl+C")
    logger.info("스케줄러 시작")

    # 시작하자마자 한 번 바로 실행하고 싶으면 아래 주석 해제
    # run_collect()

    while True:
        schedule.run_pending()
        time.sleep(60)