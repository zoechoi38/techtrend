import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from db_connect import get_connection
import warnings
warnings.filterwarnings("ignore")


# 모델을 인스턴스가 아니라 팩토리(생성 함수)로 관리
# -> walk-forward validation 중 매 폴드마다 새로운 모델을 학습해야 하므로
MODELS = {
    "linear_regression": lambda: LinearRegression(),
    "ridge": lambda: Ridge(alpha=1.0),
    "random_forest": lambda: RandomForestRegressor(n_estimators=100, random_state=42)
}

MIN_POINTS_FOR_CV = 4  # walk-forward 검증을 하려면 최소 이 정도 데이터는 있어야 함


def walk_forward_validate(model_fn, x, y):
    """
    Expanding window 방식의 시계열 교차검증(walk-forward validation).

    시점 t마다:
      - 0 ~ t-1 데이터로만 모델을 학습
      - t 시점 값을 예측 (미래를 보지 않는 진짜 out-of-sample 예측)
      - 실제값과 비교

    랜덤 train/test split과 달리, "미래 데이터로 과거를 예측"하는
    시계열 데이터 누수(leakage)가 발생하지 않는다.
    """
    n = len(x)
    preds, actuals = [], []

    train_start = 2  # 최소 2개 데이터로 학습 시작
    for t in range(train_start, n):
        x_train = x[:t].reshape(-1, 1)
        y_train = y[:t]
        x_test = x[t].reshape(1, -1)

        model = model_fn()
        model.fit(x_train, y_train)
        pred = model.predict(x_test)[0]

        preds.append(pred)
        actuals.append(y[t])

    if not preds:
        return None

    preds = np.array(preds)
    actuals = np.array(actuals)
    mse = float(mean_squared_error(actuals, preds))
    r2 = float(r2_score(actuals, preds)) if len(actuals) > 1 else 0.0
    return {"mse": mse, "r2": r2, "n_folds": len(preds)}


def fit_final_model(model_fn, x, y):
    """선택된 모델을 전체 데이터로 재학습 (실제 미래 예측용)"""
    model = model_fn()
    model.fit(x.reshape(-1, 1), y)
    return model


def run_forecast():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT job_category, keyword, year_month, total_ratio
        FROM trend_stats
        ORDER BY job_category, keyword, year_month
    """)
    rows = cur.fetchall()

    if not rows:
        print("trend_stats 데이터 없음")
        return

    df = pd.DataFrame(rows, columns=["job_category", "keyword", "year_month", "total_ratio"])
    print(f"예측할 데이터: {len(df)}개")

    cur.execute("TRUNCATE TABLE model_stats")

    saved = 0
    skipped_short = 0
    groups = df.groupby(["job_category", "keyword"])

    for (job_category, keyword), group in groups:
        group = group.sort_values("year_month").reset_index(drop=True)

        if len(group) < MIN_POINTS_FOR_CV:
            skipped_short += 1
            continue

        x = np.arange(len(group)).astype(float)
        y = group["total_ratio"].astype(float).values

        # 1) walk-forward 검증으로 모델별 out-of-sample 성능 측정
        cv_results = {}
        for name, model_fn in MODELS.items():
            try:
                result = walk_forward_validate(model_fn, x, y)
                if result is None:
                    continue
                cv_results[name] = result

                cur.execute("""
                    INSERT INTO model_stats
                        (job_category, keyword, model_name, mse, r2, calculated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (job_category, keyword, name, result["mse"], result["r2"]))

            except Exception as e:
                print(f"  [{name}] 검증 실패: {e}")
                continue

        if not cv_results:
            continue

        # 2) out-of-sample MSE가 가장 낮은 모델을 최종 모델로 선택
        #    (학습 데이터 기준 R²는 RandomForest가 항상 유리하게 나와
        #     과적합된 모델이 잘못 선택될 수 있음 -> OOS 지표로 공정하게 비교)
        best_name = min(cv_results, key=lambda k: cv_results[k]["mse"])
        best_mse = cv_results[best_name]["mse"]
        best_r2 = cv_results[best_name]["r2"]

        print(f"  [{job_category}] {keyword} → {best_name} "
              f"(OOS R²={best_r2:.3f}, OOS MSE={best_mse:.5f}, folds={cv_results[best_name]['n_folds']})")

        # 3) 선택된 모델을 전체 데이터로 재학습 (실제 미래 예측용)
        best_model = fit_final_model(MODELS[best_name], x, y)

        # 신뢰구간은 학습 잔차가 아니라 out-of-sample 오차 기준으로 산정
        # (학습 잔차는 과적합된 모델일수록 작게 나와 신뢰구간을 과소평가하게 됨)
        oos_std = float(np.sqrt(best_mse))

        # year_month는 이제 "그 주의 월요일 날짜"(YYYY-MM-DD) 형식이므로
        # "-01"을 붙일 필요 없이 바로 날짜로 파싱 가능
        last_period = pd.to_datetime(group["year_month"].iloc[-1])

        FORECAST_WEEKS_AHEAD = 8  # 향후 8주치 예측 (월 단위 6개월 예측을 주 단위로 대체)
        for i in range(1, FORECAST_WEEKS_AHEAD + 1):
            target = last_period + pd.DateOffset(weeks=i)
            target_month = target.strftime("%Y-%m-%d")
            x_pred = np.array([[len(group) + i - 1]])
            predicted = float(round(max(float(best_model.predict(x_pred)[0]), 0), 4))
            lower = float(round(max(predicted - 1.96 * oos_std, 0), 4))
            upper = float(round(predicted + 1.96 * oos_std, 4))

            try:
                cur.execute("""
                    INSERT INTO forecasts
                        (job_category, keyword, target_month, predicted_ratio,
                         lower_bound, upper_bound, forecasted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (job_category, keyword, target_month, predicted, lower, upper))
                saved += 1
            except Exception as e:
                print(f"  저장 오류: {e}")
                conn.rollback()
                continue

    conn.commit()

    cur.execute("""
        SELECT model_name, COUNT(*) as cnt, AVG(r2) as avg_r2, AVG(mse) as avg_mse
        FROM model_stats
        GROUP BY model_name
        ORDER BY avg_r2 DESC
    """)
    print(f"\n=== 모델 성능 비교 (Out-of-Sample) ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}개 (평균 R²={row[2]:.3f}, 평균 MSE={row[3]:.5f})")

    if skipped_short:
        print(f"\n데이터 부족으로 건너뛴 키워드: {skipped_short}개 (최소 {MIN_POINTS_FOR_CV}주 필요)")

    cur.close()
    conn.close()
    print(f"\n완료! 총 {saved}개 예측 결과 저장")


if __name__ == "__main__":
    print("=== 수요 예측 시작 ===")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE forecasts")
    conn.commit()
    cur.close()
    conn.close()
    run_forecast()