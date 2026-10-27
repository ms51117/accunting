# Entry point
import os
import sys
import asyncio
from contextlib import asynccontextmanager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import engine, Base, run_auto_migrations
from app.config import settings
from app.utils.jalali import format_rial, to_jalali_str
from tunnel_service import tunnel_service

# ساخت پوشه دیتابیس اگر وجود نداشت
os.makedirs("data", exist_ok=True)
os.makedirs("backups", exist_ok=True)

# ساخت جداول دیتابیس
Base.metadata.create_all(bind=engine)
# اجرای مهاجرت خودکار فیلدهای جدید برای دیتابیس‌های موجود
run_auto_migrations()

async def cheque_reminder_worker():
    """کارگر پس‌زمینه برای بررسی خودکار دوره‌ای سررسید چک‌ها و ارسال هشدار تلگرام"""
    await asyncio.sleep(10)
    while True:
        try:
            from app.database import SessionLocal
            from app.services.telegram_service import check_and_notify_upcoming_cheques
            with SessionLocal() as db:
                await check_and_notify_upcoming_cheques(db, days_ahead=3, force_send=False)
        except Exception as e:
            print(f"خطا در کارگر یادآور چک‌ها: {e}", flush=True)
        await asyncio.sleep(3 * 3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # چاپ راهنمای دسترسی محلی در کنسول
    print("\n" + "="*60, flush=True)
    print(f"💎 سامانه حسابداری شخصی فعال شد:", flush=True)
    print(f"💻 دسترسی در همین کامپیوتر:   http://localhost:{settings.APP_PORT}", flush=True)
    print(f"📱 دسترسی در گوشی (وای‌فای): http://192.168.1.117:{settings.APP_PORT}", flush=True)
    print("="*60 + "\n", flush=True)

    # شروع تونل و کارگر یادآور چک‌ها در پس‌زمینه
    tunnel_task = asyncio.create_task(tunnel_service.start())
    reminder_task = asyncio.create_task(cheque_reminder_worker())
    yield
    # بستن تسک‌ها هنگام خاموش شدن برنامه
    tunnel_task.cancel()
    reminder_task.cancel()
    try:
        await asyncio.gather(tunnel_task, reminder_task, return_exceptions=True)
    except Exception:
        pass

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

from fastapi.responses import FileResponse

# اتصال فایل‌های استاتیک محلی
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/manifest.json", include_in_schema=False)
async def get_manifest():
    return FileResponse("app/static/manifest.json", media_type="application/manifest+json")

@app.get("/sw.js", include_in_schema=False)
async def get_sw():
    return FileResponse("app/static/sw.js", media_type="application/javascript")

# تنظیم موتور Jinja2 و افزودن فیلترها
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str

# ثبت روت‌ها
from app.routers import (
    auth_router,
    dashboard_router,
    persons_router,
    accounts_router,
    categories_router,
    cheques_router,
    debts_router,
    transactions_router,
    backup_router,
    reports_router
)

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(persons_router.router)
app.include_router(accounts_router.router)
app.include_router(categories_router.router)
app.include_router(cheques_router.router)
app.include_router(debts_router.router)
app.include_router(transactions_router.router)
app.include_router(backup_router.router)
app.include_router(reports_router.router)


if __name__ == "__main__":
    import uvicorn
    # اجرا روی پورت مشخص‌شده با دسترسی عمومی
    uvicorn.run("main:app", host="0.0.0.0", port=settings.APP_PORT, reload=False)
