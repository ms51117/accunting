import os
import shutil
import sqlite3
import sys
from datetime import datetime

# تنظیم کدگذاری خروجی ترمینال ویندوز برای نمایش صحیح حروف فارسی
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB_PATH = "data/accounting.db"
BACKUP_DIR = "backups"

def get_category_meta(title: str, detected_type: str):
    title_lower = title.strip().lower()
    
    # رنگ و آیکون هوشمند بر اساس موضوع
    if "طلا" in title_lower:
        return "#f59e0b", "gem"  # طلایی / سنگ قیمتی
    elif "بانک" in title_lower or "کارمزد" in title_lower:
        return "#3b82f6", "bank2"  # آبی / بانک
    elif "درمان" in title_lower or "ارتودونسی" in title_lower or "پزشک" in title_lower:
        return "#ec4899", "heart-pulse"  # صورتی / درمان
    elif "تنخواه" in title_lower:
        return "#8b5cf6", "cash-stack"  # بنفش / تنخواه
    elif "مهندس" in title_lower or "ناظر" in title_lower:
        return "#6366f1", "briefcase"  # نیلی / قرارداد مهندسی
    elif "آهن" in title_lower or "اهن" in title_lower or "سیم جوش" in title_lower or "استیل" in title_lower:
        return "#64748b", "tools"  # خاکستری / ابزار و مصالح
    elif "قرارداد" in title_lower:
        return "#0ea5e9", "file-earmark-text"  # فیروزه‌ای / قرارداد
    elif "محضر" in title_lower or "شهرداری" in title_lower:
        return "#14b8a6", "building"  # سبز آبی / اداری
    elif "وام" in title_lower or "قرض" in title_lower or "طلب" in title_lower:
        return "#10b981", "arrow-repeat"  # زمردی / گردش مالی
    elif "چک" in title_lower:
        return "#06b6d4", "card-checklist"  # آبی آسمانی / چک
    elif "نهار" in title_lower or "غذا" in title_lower or "کارگر" in title_lower:
        return "#f97316", "cup-hot"  # نارنجی / پذیرایی
    elif "وانت" in title_lower or "کرایه" in title_lower or "حمل" in title_lower:
        return "#eab308", "truck"  # زرد / حمل و نقل
    elif "کمیسیون" in title_lower:
        return "#f43f5e", "percent"  # رز / درصد و کمیسیون
    elif "حقوق" in title_lower:
        return "#10b981", "wallet2"  # سبز / حقوق
    elif "اجاره" in title_lower or "قبوض" in title_lower:
        return "#ef4444", "receipt"  # قرمز / قبض و اجاره
    else:
        color = "#10b981" if detected_type == "INCOME" else ("#ef4444" if detected_type == "EXPENSE" else "#3b82f6")
        return color, "tag"


def run_migration():
    if not os.path.exists(DB_PATH):
        print(f"❌ دیتابیس در مسیر {DB_PATH} یافت نشد!")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_before_cat_migration_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    print(f"🛡️ فایل پشتیبان ایمن دیتابیس ذخیره شد در: {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ۱. شمارش رکوردهای اولیه برای تضمین عدم حذف داده
    cur.execute("SELECT COUNT(*) FROM transactions")
    initial_tx_count = cur.fetchone()[0]
    print(f"📊 تعداد کل تراکنش‌های موجود قبل از مایگریشن: {initial_tx_count}")

    # ۲. ایجاد جدول categories در صورت عدم وجود
    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title VARCHAR(100) NOT NULL,
        type VARCHAR(20) NOT NULL DEFAULT 'BOTH',
        color VARCHAR(20) DEFAULT '#3b82f6',
        icon VARCHAR(50) DEFAULT 'tag',
        description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # ایندکس‌های جدول دسته‌بندی
    cur.execute("CREATE INDEX IF NOT EXISTS ix_categories_user_id ON categories (user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_categories_id ON categories (id);")

    # ۳. بررسی وجود ستون category_id در جدول transactions
    cur.execute("PRAGMA table_info(transactions)")
    columns = [row[1] for row in cur.fetchall()]
    if "category_id" not in columns:
        print("➕ ستون category_id به جدول transactions اضافه می‌شود...")
        cur.execute("ALTER TABLE transactions ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL;")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_transactions_category_id ON transactions (category_id);")
    else:
        print("✓ ستون category_id از قبل در جدول transactions وجود دارد.")

    # ۴. استخراج تمام کاربران یکتا از جدول transactions و users
    cur.execute("SELECT id FROM users")
    user_ids = [r[0] for r in cur.fetchall()]
    if not user_ids:
        cur.execute("SELECT DISTINCT user_id FROM transactions")
        user_ids = [r[0] for r in cur.fetchall()]

    print(f"👥 کاربران شناسایی شده: {user_ids}")

    total_migrated_categories = 0

    for uid in user_ids:
        # استخراج دسته‌بندی‌های موجود در تراکنش‌های این کاربر
        cur.execute("""
            SELECT category, type, COUNT(*) 
            FROM transactions 
            WHERE user_id = ? 
            GROUP BY category, type
        """, (uid,))
        rows = cur.fetchall()

        # گروه‌بندی دسته‌ها و شناسایی نوع آنها
        category_usage = {}
        for raw_cat, tx_type, count in rows:
            clean_name = (raw_cat or "سایر").strip()
            if not clean_name:
                clean_name = "سایر"
            if clean_name not in category_usage:
                category_usage[clean_name] = set()
            category_usage[clean_name].add(tx_type)

        for cat_title, types in category_usage.items():
            if len(types) > 1 or "TRANSFER" in types:
                detected_type = "BOTH"
            elif "INCOME" in types:
                detected_type = "INCOME"
            else:
                detected_type = "EXPENSE"

            # بررسی اینکه آیا دسته از قبل برای این کاربر ثبت شده یا خیر
            cur.execute("SELECT id FROM categories WHERE user_id = ? AND title = ?", (uid, cat_title))
            existing_cat = cur.fetchone()

            if not existing_cat:
                color, icon = get_category_meta(cat_title, detected_type)
                cur.execute("""
                    INSERT INTO categories (user_id, title, type, color, icon, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (uid, cat_title, detected_type, color, icon, "انتقال یافته خودکار از تراکنش‌های قبلی"))
                cat_id = cur.lastrowid
                total_migrated_categories += 1
                print(f"  ✨ دسته‌بندی ایجاد شد: [{cat_title}] با نوع {detected_type} برای کاربر {uid}")
            else:
                cat_id = existing_cat[0]

            # متصل کردن تمام تراکنش‌های متناظر به این category_id و تمیزکاری نام دسته
            cur.execute("""
                UPDATE transactions 
                SET category_id = ?, category = ? 
                WHERE user_id = ? AND TRIM(category) = ?
            """, (cat_id, cat_title, uid, cat_title))

        # ۵. اضافه کردن دسته‌بندی‌های استاندارد پایه در صورتی که کاربر دسته‌ای نداشته باشد یا تکمیلی باشد
        default_categories = [
            ("حقوق و درآمد", "INCOME", "#10b981", "wallet2", "درآمدهای حاصل از کار، حقوق و پاداش"),
            ("هزینه‌های جاری", "EXPENSE", "#ef4444", "cart", "هزینه‌های روزمره و خریدهای مصرفی"),
            ("قبوض و خدمات", "EXPENSE", "#f97316", "receipt", "قبض آب، برق، گاز، تلفن و اینترنت"),
            ("انتقال بین حسابی", "BOTH", "#3b82f6", "arrow-left-right", "جابجایی وجوه بین حساب‌ها و صندوق‌ها"),
            ("سایر", "BOTH", "#64748b", "tag", "سایر موارد متفرقه")
        ]

        for d_title, d_type, d_color, d_icon, d_desc in default_categories:
            cur.execute("SELECT id FROM categories WHERE user_id = ? AND title = ?", (uid, d_title))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO categories (user_id, title, type, color, icon, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (uid, d_title, d_type, d_color, d_icon, d_desc))

    conn.commit()

    # ۶. راستی‌آزمایی جامع پس از مایگریشن
    cur.execute("SELECT COUNT(*) FROM transactions")
    post_tx_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM transactions WHERE category_id IS NOT NULL")
    linked_tx_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM categories")
    total_categories_in_db = cur.fetchone()[0]

    conn.close()

    print("\n" + "="*50)
    print("✅ فرایند ارتقا و مایگریشن دسته‌بندی‌ها با موفقیت کامل انجام شد:")
    print(f"  • تعداد کل تراکنش‌های قبل از عملیات: {initial_tx_count}")
    print(f"  • تعداد کل تراکنش‌های بعد از عملیات: {post_tx_count} (بدون تغییر)")
    print(f"  • تراکنش‌های متصل شده به شناسه دسته: {linked_tx_count} از {post_tx_count}")
    print(f"  • کل دسته‌بندی‌های فعال در سیستم:     {total_categories_in_db}")
    print("="*50 + "\n")

    if initial_tx_count != post_tx_count:
        raise RuntimeError("هشدار: تعداد تراکنش‌ها مطابقت ندارد!")


if __name__ == "__main__":
    run_migration()
