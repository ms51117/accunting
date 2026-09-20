FROM python:3.10-slim

WORKDIR /app

# نصب پیش‌نیازها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن کل سورس کد پروژه
COPY . .

# پورت برنامه
EXPOSE 8000

# اجرای FastAPI به صورت مستقیم از main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
