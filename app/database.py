from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

# فعال‌سازی پشتیبانی از کلیدهای خارجی در SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_auto_migrations():
    """
    بررسی و افزودن خودکار ستون‌های جدید به دیتابیس در صورت عدم وجود (مهاجرت امن و بدون حذف داده)
    """
    try:
        with engine.connect() as conn:
            inspector = inspect(engine)
            tables = inspector.get_table_names()

            # ۱. جدول cheques
            if "cheques" in tables:
                cheque_cols = {c["name"] for c in inspector.get_columns("cheques")}
                if "last_notified_date" not in cheque_cols:
                    conn.execute(text("ALTER TABLE cheques ADD COLUMN last_notified_date DATE"))
                    conn.commit()
                    print("✅ مهاجرت دیتابیس: ستون last_notified_date به جدول cheques اضافه شد.", flush=True)

            # ۲. جدول users
            if "users" in tables:
                user_cols = {c["name"] for c in inspector.get_columns("users")}
                if "telegram_chat_id" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(50)"))
                    conn.commit()
                    print("✅ مهاجرت دیتابیس: ستون telegram_chat_id به جدول users اضافه شد.", flush=True)
                if "is_admin" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
                    conn.commit()
                    print("✅ مهاجرت دیتابیس: ستون is_admin به جدول users اضافه شد.", flush=True)
                if "last_seen" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN last_seen DATETIME"))
                    conn.commit()
                    print("✅ مهاجرت دیتابیس: ستون last_seen به جدول users اضافه شد.", flush=True)

            # ۳. جدول transactions
            if "transactions" in tables:
                tx_cols = {c["name"] for c in inspector.get_columns("transactions")}
                if "category_id" not in tx_cols:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN category_id INTEGER"))
                    conn.commit()
                    print("✅ مهاجرت دیتابیس: ستون category_id به جدول transactions اضافه شد.", flush=True)

    except Exception as e:
        print(f"⚠️ خطای مهاجرت دیتابیس: {e}", flush=True)

