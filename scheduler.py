import schedule
import time
import logging
from pipeline import run_daily

# ── 로깅 설정 ─────────────────────────────────
logging.basicConfig(
    filename="crawler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)
logger = logging.getLogger(__name__)

# 매일 오전 9시에 수집부터 예측까지 전체 파이프라인 실행
schedule.every().day.at("09:00").do(run_daily)

if __name__ == "__main__":
    print("스케줄러 시작 — 매일 09:00 수집 + 분석 + 예측")
    print("종료하려면 Ctrl+C")
    logger.info("스케줄러 시작")

    # 시작하자마자 한 번 바로 실행하고 싶으면 아래 주석 해제
    # run_daily()

    while True:
        try:
            schedule.run_pending()
        except Exception:
            # 예외가 루프를 끝내 스케줄러가 조용히 죽는 일을 막는다
            logger.exception("스케줄러 실행 중 오류")
        time.sleep(60)