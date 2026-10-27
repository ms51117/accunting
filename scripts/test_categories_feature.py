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
from app.database import SessionLocal
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User

client = TestClient(app, follow_redirects=True)

def run_tests():
    print("🚀 شروع راستی‌آزمایی جامع قابلیت دسته‌بندی‌ها...")

    db = SessionLocal()
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        user = db.query(User).first()
    assert user is not None, "کاربری در سیستم یافت نشد!"
    user_id = user.id
    print(f"👤 کاربر تستی: {user.username} (ID: {user_id})")

    # ۱. بررسی سلامت ۴۴ تراکنش قبلی
    tx_count = db.query(Transaction).filter(Transaction.user_id == user_id).count()
    print(f"📊 تعداد کل تراکنش‌های کاربر در دیتابیس: {tx_count}")
    assert tx_count >= 44, f"خطا: تعداد تراکنش‌ها کمتر از ۴۴ است ({tx_count})!"

    unlinked = db.query(Transaction).filter(Transaction.user_id == user_id, Transaction.category_id.is_(None)).count()
    print(f"🔗 تراکنش‌های فاقد شناسه دسته‌بندی: {unlinked}")
    assert unlinked == 0, f"خطا: {unlinked} تراکنش بدون category_id هستند!"

    # ۲. شبیه‌سازی لاگین کاربر
    from app.auth import create_session_token, COOKIE_NAME
    token = create_session_token(user_id=user.id, username=user.username)
    client.cookies.set(COOKIE_NAME, token)

    # ۳. تست صفحه دسته‌بندی‌ها
    resp = client.get("/categories")
    assert resp.status_code == 200, f"خطا در دسترسی به /categories: {resp.status_code}"
    assert "مدیریت دسته‌بندی‌ها" in resp.text, "عنوان صفحه دسته‌بندی‌ها در خروجی مشاهده نشد!"
    print("✅ صفحه /categories با کد ۲۰۰ و محتوای صحیح لود شد.")

    # ۴. تست ثبت دسته‌بندی جدید
    test_cat_title = "تست سرفصل ویژه خودکار"
    # اگر قبلا وجود داشته پاک شود
    existing_test = db.query(Category).filter(Category.user_id == user_id, Category.title == test_cat_title).first()
    if existing_test:
        db.delete(existing_test)
        db.commit()

    resp = client.post("/categories/create", data={
        "title": test_cat_title,
        "type": "EXPENSE",
        "color": "#8b5cf6",
        "icon": "gem",
        "description": "توضیح تستی"
    })
    assert resp.status_code == 200, f"خطا در ایجاد دسته‌بندی: {resp.status_code}"
    
    created_cat = db.query(Category).filter(Category.user_id == user_id, Category.title == test_cat_title).first()
    assert created_cat is not None, "دسته‌بندی در دیتابیس ذخیره نشد!"
    print(f"✅ دسته‌بندی جدید با شناسه {created_cat.id} با موفقیت ثبت شد.")

    # ۵. تست صفحه تراکنش‌ها و فیلتر دسته‌بندی
    resp = client.get(f"/transactions?category_filter={created_cat.id}")
    assert resp.status_code == 200
    print("✅ فیلتر تراکنش‌ها بر اساس دسته‌بندی با موفقیت پاسخ ۲۰۰ بازگرداند.")

    # ۶. تست API دسته‌بندی‌ها
    resp = client.get("/categories/api/list")
    assert resp.status_code == 200
    cats_json = resp.json()
    assert isinstance(cats_json, list) and len(cats_json) > 0
    print(f"✅ خروجی API دسته‌بندی‌ها با {len(cats_json)} دسته فعال تایید شد.")

    # ۷. تست دانلود بک‌آپ و وجود categories در خروجی
    resp = client.get("/backups/download")
    assert resp.status_code == 200
    backup_data = resp.json()
    assert "categories" in backup_data, "بخش categories در فایل بک‌آپ موجود نیست!"
    assert len(backup_data["categories"]) > 0, "لیست categories در بک‌آپ خالی است!"
    assert "transactions" in backup_data, "بخش transactions در بک‌آپ موجود نیست!"
    assert any("category_id" in t for t in backup_data["transactions"]), "شناسه category_id در تراکنش‌های بک‌آپ وجود ندارد!"
    print(f"✅ فایل پشتیبان حاوی {len(backup_data['categories'])} دسته‌بندی و {len(backup_data['transactions'])} تراکنش معتبر است.")

    # پاک‌سازی دسته‌بندی تستی
    db.delete(created_cat)
    db.commit()

    db.close()
    print("\n🎉 تمام آزمایش‌ها با موفقیت ۱۰۰٪ پاس شدند! هیچ داده‌ای مخدوش یا حذف نشد.")


if __name__ == "__main__":
    run_tests()
