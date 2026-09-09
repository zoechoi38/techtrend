import psycopg2
import os

def get_connection():
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "aws-0-ap-northeast-2.pooler.supabase.com"),
        port=int(os.environ.get("DB_PORT", 5432)),
        database=os.environ.get("DB_NAME", "postgres"),
        user=os.environ.get("DB_USER", "postgres.foxjvjqadxjsnbjjrtqw"),
        password=os.environ.get("DB_PASSWORD", "Ghkdbs0830!")
    )
    return conn

if __name__ == "__main__":
    try:
        conn = get_connection()
        print("DB 연결 성공!")
        conn.close()
    except Exception as e:
        print(f"DB 연결 실패: {e}")