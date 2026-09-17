import os
import glob
import sqlite3
import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Depends
from fastapi.responses import FileResponse
from app.auth import get_current_user  # در صورت نیاز به مسیر پکیج: from app.routers.auth_router import get_current_user

router = APIRouter(
    prefix="/backups",
    tags=["Backup"]
)

BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)


def find_database_path() -> str:
    """
    یافتن خودکار و دقیق مسیر فایل SQLite در پروژه (پوشه data، ریشه پروژه یا فایل .env)
    """
    candidates = []

    # ۱. بررسی متغیر DATABASE_PATH
    if env_path := os.getenv("DATABASE_PATH"):
        candidates.append(env_path)

    # ۲. استخراج مسیر از DATABASE_URL
    if db_url := os.getenv("DATABASE_URL"):
        if "sqlite:///" in db_url:
            clean_url = db_url.replace("sqlite:///", "").strip()
            candidates.append(clean_url)
        elif "sqlite://" in db_url:
            clean_url = db_url.replace("sqlite://", "").strip()
            candidates.append(clean_url)

    # ۳. مسیرهای متداول پوشه data و ریشه
    candidates.extend([
        os.path.join("data", "accounting.db"),
        os.path.join(".", "data", "accounting.db"),
        "accounting.db",
        os.path.join(".", "accounting.db")
    ])

    # ۴. جستجوی هرگونه فایل با پسوند .db در پوشه data یا ریشه
    candidates.extend(glob.glob("data/*.db"))
    candidates.extend(glob.glob("*.db"))

    # تست و بازگرداندن اولین مسیر معتبر
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)

    # اگر در مسیر اجرای سرور پیدا نشد، بررسی نسبت به ریشه اسکریپت
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback_data_dir = os.path.join(base_dir, "data", "accounting.db")
    if os.path.isfile(fallback_data_dir):
        return fallback_data_dir

    return None


def remove_temp_file(file_path: str):
    """حذف امن فایل موقت بک‌آپ پس از دانلود"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as err:
        print(f"Error removing backup temp file: {err}")


@router.get("/download-now")
def download_live_backup(
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_user)
):
    """
    تهیه بک‌آپ زنده از دیتابیس بدون قفل شدن دیتابیس در حین نوشتن
    """
    db_file_path = find_database_path()

    if not db_file_path or not os.path.isfile(db_file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="فایل دیتابیس در پوشه data یا مسیرهای تعریف‌شده یافت نشد."
        )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_backup_filename = f"backup_temp_{timestamp}.db"
    temp_backup_path = os.path.join(BACKUP_DIR, temp_backup_filename)

    try:
        # باز کردن دیتابیس مبدا در حالت فقط‌خواندنی جهت جلوگیری از تداخل
        src_conn = sqlite3.connect(f"file:{db_file_path}?mode=ro", uri=True)
        dest_conn = sqlite3.connect(temp_backup_path)

        # تهیه بک‌آپ از طریق SQLite Online Backup API
        with dest_conn:
            src_conn.backup(dest_conn, pages=100, sleep=0.01)

        src_conn.close()
        dest_conn.close()

    except sqlite3.Error as e:
        if os.path.exists(temp_backup_path):
            os.remove(temp_backup_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"خطا در ایجاد نسخه پشتیبان: {str(e)}"
        )

    # پاکسازی فایل موقت پس از اتمام دانلود توسط کلاینت
    background_tasks.add_task(remove_temp_file, temp_backup_path)

    download_filename = f"accounting_backup_{timestamp}.db"

    return FileResponse(
        path=temp_backup_path,
        filename=download_filename,
        media_type="application/x-sqlite3"
    )
