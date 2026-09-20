FROM python:3.10-slim

# تنظیم دایرکتوری کاری
WORKDIR /app

# نصب پیش‌نیازهای سیستمی و دانلود cloudflared
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
    && dpkg -i cloudflared.deb \
    && rm cloudflared.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# کپی نیازمندی‌ها و نصب پکیج‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کل سورس‌کد
COPY . .

# پورت برنامه
EXPOSE 8000

# اجرای مستقیم uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
