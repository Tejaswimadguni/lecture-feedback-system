import os
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def execute_query(query, params=None):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()

    finally:
        conn.close()


def fetch_query(query, params=None):
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        conn = get_connection()

        with conn.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            database_name = cursor.fetchone()[0]

        conn.close()

        print("✅ PostgreSQL connection successful!")
        print(f"📦 Database: {database_name}")

    except Exception as e:
        print("❌ PostgreSQL connection failed:")
        print(e)