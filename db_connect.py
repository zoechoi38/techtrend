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
    """
    클라우드 DB에 연결한다. 기본값을 두지 않아, 값이 없으면 KeyError로 바로 드러난다.

    인터넷이 끊겼을 때 응답 없이 무한정 멈춰 있지 않도록 시간 제한을 둔다.
      connect_timeout : 연결을 시도하다 15초 안에 안 되면 오류
      keepalives_*    : 30초 동안 조용하면 확인 신호를 보내고, 10초 간격으로 3번 응답이 없으면
                        연결이 끊긴 것으로 보고 오류를 낸다(대략 1분 뒤)
    """
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=15,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )


if __name__ == "__main__":
    try:
        conn = get_connection()
        print("DB 연결 성공!")
        conn.close()
    except Exception as e:
        print(f"DB 연결 실패: {e}")