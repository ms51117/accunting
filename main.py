# Entry point
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.database import engine, Base
from app.config import settings
from app.utils.jalali import format_rial, to_jalali_str

# ساخت پوشه دیتابیس اگر وجود نداشت
os.makedirs("data", exist_ok=True)

# ساخت جداول دیتابیس
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME)

# تنظیم موتور Jinja2 و افزودن فیلترها
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str

# ثبت روت‌ها
from app.routers import auth_router, dashboard_router, persons_router, accounts_router, cheques_router, debts_router, transactions_router

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(persons_router.router)
app.include_router(accounts_router.router)
app.include_router(cheques_router.router)
app.include_router(debts_router.router)
app.include_router(transactions_router.router)

if __name__ == "__main__":
    import uvicorn
    # اجرا روی پورت 8000 با دسترسی عمومی
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
