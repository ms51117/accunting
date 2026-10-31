FROM python:3.10-slim

# تنظیم دایرکتوری کاری
WORKDIR /app

# متغیرهای محیطی بهینه‌سازی پایتون
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

# نصب پیش‌نیازهای سیستمی و گواهی‌های امنیتی SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# کپی نیازمندی‌ها و نصب پکیج‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کل سورس‌کد
COPY . .

# ساخت پوشه‌های ذخیره‌سازی داده و بک‌آپ
RUN mkdir -p /app/data /app/backups

# پورت برنامه
EXPOSE 8000

# اجرای uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
