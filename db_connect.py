import os
import psycopg2

# 로컬에서는 .env 파일을 읽고, 배포 환경(Streamlit Cloud)에서는 Secrets가
# 환경변수로 들어오므로 dotenv가 없어도 동작하게 처리
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_connection():
    # 기본값을 두지 않는다: 값이 없으면 KeyError로 바로 드러나게 함
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


if __name__ == "__main__":
    try:
        conn = get_connection()
        print("DB 연결 성공!")
        conn.close()
    except Exception as e:
        print(f"DB 연결 실패: {e}")