import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from app.auth import create_session_token, COOKIE_NAME
from app.database import SessionLocal
from app.models.user import User

client = TestClient(app)
db = SessionLocal()
user = db.query(User).filter(User.username == "admin").first() or db.query(User).first()
db.close()

token = create_session_token(user.id, user.username)
client.cookies.set(COOKIE_NAME, token)

test_urls = [
    "/transactions",
    "/transactions?type_filter=ALL",
    "/transactions?type_filter=INCOME",
    "/transactions?type_filter=EXPENSE",
    "/transactions?type_filter=TRANSFER",
    "/transactions?type_filter=INVALID_TYPE",
    "/transactions?category_filter=",
    "/transactions?category_filter=1",
    "/transactions?category_filter=999999",
    "/transactions?category_filter=invalid_str",
    "/transactions?account_filter=",
    "/transactions?account_filter=1",
    "/transactions?account_filter=999999",
    "/transactions?account_filter=invalid_str",
    "/transactions?month_filter=",
    "/transactions?month_filter=1",
    "/transactions?month_filter=7",
    "/transactions?month_filter=12",
    "/transactions?month_filter=99",
    "/transactions?month_filter=invalid_str",
    "/transactions?year_filter=",
    "/transactions?year_filter=1405",
    "/transactions?year_filter=99999",
    "/transactions?year_filter=invalid_str",
    "/transactions?search=",
    "/transactions?search=طلا",
    "/transactions?search=مهندس",
    # آدرس دقیق کاربر از اسکرین‌شات
    "/transactions?type_filter=EXPENSE&category_filter=32&account_filter=7&month_filter=&year_filter=1405&search=",
    # تمام فیلترها خالی
    "/transactions?type_filter=&category_filter=&account_filter=&month_filter=&year_filter=&search=",
    # تمام فیلترها با مقادیر معتبر
    "/transactions?type_filter=EXPENSE&category_filter=1&account_filter=1&month_filter=7&year_filter=1405&search=طلا",
]

failed = 0
for url in test_urls:
    resp = client.get(url)
    if resp.status_code == 200:
        print(f"✅ OK (200): {url}")
    else:
        print(f"❌ FAIL ({resp.status_code}): {url} -> {resp.text}")
        failed += 1

print("\n" + "="*50)
if failed == 0:
    print(f"🎉 تمام {len(test_urls)} حالت فیلتر با موفقیت کامل تست شدند (100% بدون ارور)!")
else:
    print(f"⚠️ {failed} حالت با خطا مواجه شدند!")
print("="*50)
