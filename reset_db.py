from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

password = os.getenv("DB_PASSWORD", "")
user = os.getenv("DB_USER", "postgres")
host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "5432")

url = f"postgresql://{user}:{password}@{host}:{port}/postgres"
engine = create_engine(url, isolation_level="AUTOCOMMIT")

with engine.connect() as conn:
    conn.execute(text("DROP DATABASE IF EXISTS manifetch"))
    conn.execute(text("CREATE DATABASE manifetch"))

print("DB sıfırlandı.")