from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import os
#import psycopg
#import psycopg2 #old version
from dotenv import load_dotenv
from src.config import POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER #,DATABASE_URL

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def get_db_sqlalchemy():
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()

# def get_db_conn():
#     conn = None
#     try:
#         conn = psycopg.connect(DATABASE_URL)
#         yield conn
#     except psycopg.DatabaseError as e:
#         print(f"Database connection error: {e}")
#     finally:
#         if conn:
#             conn.close()