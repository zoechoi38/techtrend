"""
매일 실행하는 전체 파이프라인: 수집 -> 키워드 추출 -> 트렌드 통계 -> 변화율 -> 수요 예측.

한 단계가 실패해도 로그를 남기고 다음 단계로 넘어간다. 예를 들어 사이트가 응답하지 않아
수집이 실패해도, 이미 쌓인 데이터로 통계와 예측은 계속 최신 상태로 유지할 수 있다.

직접 실행하면 한 번 돌고 끝난다:  python pipeline.py
"""
import logging

from collector import run_collection
from processor import process_postings
from analyzer import calculate_trend_stats, calculate_trend_change
from forecaster import run_forecast

logger = logging.getLogger(__name__)

STEPS = [
    ("수집", run_collection),
    ("키워드 추출", process_postings),
    ("트렌드 통계", calculate_trend_stats),
    ("변화율 계산", calculate_trend_change),
    ("수요 예측", run_forecast),
]


def run_step(name, func):
    print(f"\n########## {name} ##########")
    logger.info(f"[파이프라인] {name} 시작")
    try:
        func()
        logger.info(f"[파이프라인] {name} 완료")
        return True
    except Exception as e:
        logger.exception(f"[파이프라인] {name} 실패: {e}")
        print(f"{name} 실패: {e}")
        return False


def run_daily():
    logger.info("=== 파이프라인 시작 ===")
    results = {name: run_step(name, func) for name, func in STEPS}
    failed = [name for name, ok in results.items() if not ok]
    if failed:
        logger.error(f"=== 파이프라인 종료: 실패한 단계 {failed} ===")
        print(f"\n실패한 단계: {', '.join(failed)}")
    else:
        logger.info("=== 파이프라인 종료: 모두 성공 ===")
        print("\n파이프라인 완료: 모든 단계 성공")
    return results


if __name__ == "__main__":
    run_daily()