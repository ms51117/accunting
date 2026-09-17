# استفاده از نسخه سبک پایتون
FROM python:3.10-slim

# تنظیم متغیرهای محیطی پایتون
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Tehran

# تنظیم پوشه کاری
WORKDIR /app

# نصب پیش‌نیازهای سیستمی (در صورت نیاز به کامپایل پکیج‌ها)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# کپی و نصب پکیج‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کل پروژه
COPY . .

# ساخت پوشه‌های ضروری برای ذخیره دیتابیس و بک‌آپ
RUN mkdir -p /app/data /app/backups

# پورت برنامه
EXPOSE 8000

# دستور اجرای برنامه با Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
