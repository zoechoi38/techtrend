import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from db_connect import get_connection
import warnings
warnings.filterwarnings("ignore")


MODELS = {
    "linear_regression": LinearRegression(),
    "ridge": Ridge(alpha=1.0),
    "random_forest": RandomForestRegressor(n_estimators=100, random_state=42)
}


def evaluate_model(model, x, y):
    x_2d = x.reshape(-1, 1)
    model.fit(x_2d, y)
    y_pred = model.predict(x_2d)
    mse = float(mean_squared_error(y, y_pred))
    r2 = float(r2_score(y, y_pred)) if len(y) > 1 else 0.0
    return model, mse, r2


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

    # 기존 model_stats 초기화
    cur.execute("TRUNCATE TABLE model_stats")

    saved = 0
    groups = df.groupby(["job_category", "keyword"])

    for (job_category, keyword), group in groups:
        group = group.sort_values("year_month").reset_index(drop=True)
        if len(group) < 2:
            continue

        x = np.arange(len(group)).astype(float)
        y = group["total_ratio"].astype(float).values

        # 모델별 성능 평가 및 저장
        results = {}
        for name, model in MODELS.items():
            try:
                trained_model, mse, r2 = evaluate_model(model, x, y)
                results[name] = {"model": trained_model, "mse": mse, "r2": r2}

                # model_stats 저장
                cur.execute("""
                    INSERT INTO model_stats
                        (job_category, keyword, model_name, mse, r2, calculated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (job_category, keyword, name, mse, r2))

            except Exception as e:
                print(f"  [{name}] 학습 실패: {e}")
                continue

        if not results:
            continue

        # 최적 모델 선택 (R² 기준)
        best_name = max(results, key=lambda k: results[k]["r2"])
        best_model = results[best_name]["model"]
        best_r2 = results[best_name]["r2"]
        best_mse = results[best_name]["mse"]

        print(f"  [{job_category}] {keyword} → {best_name} (R²={best_r2:.3f}, MSE={best_mse:.5f})")

        # 향후 6개월 예측
        last_month = pd.to_datetime(group["year_month"].iloc[-1] + "-01")
        residuals = y - best_model.predict(x.reshape(-1, 1))
        std = float(np.std(residuals))

        for i in range(1, 7):
            target = last_month + pd.DateOffset(months=i)
            target_month = target.strftime("%Y-%m")
            x_pred = np.array([[len(group) + i - 1]])
            predicted = float(round(max(float(best_model.predict(x_pred)[0]), 0), 4))
            lower = float(round(max(predicted - 1.96 * std, 0), 4))
            upper = float(round(predicted + 1.96 * std, 4))

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

    # 모델별 평균 성능 출력
    cur.execute("""
        SELECT model_name, COUNT(*) as cnt, AVG(r2) as avg_r2, AVG(mse) as avg_mse
        FROM model_stats
        GROUP BY model_name
        ORDER BY avg_r2 DESC
    """)
    print(f"\n=== 모델 성능 비교 ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}개 (평균 R²={row[2]:.3f}, 평균 MSE={row[3]:.5f})")

    cur.close()
    conn.close()
    print(f"\n완료! 총 {saved}개 예측 결과 저장")


if __name__ == "__main__":
    print("=== 수요 예측 시작 ===")
    # forecasts 초기화 후 재실행
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE forecasts")
    conn.commit()
    cur.close()
    conn.close()
    run_forecast()