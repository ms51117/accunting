import jdatetime
from datetime import datetime, date

def to_jalali_str(d: date | datetime | str | None, format_str: str = "%Y/%m/%d") -> str:
    """تبدیل تاریخ میلادی به رشته شمسی فرمت‌شده"""
    if not d:
        return "-"
    if isinstance(d, str):
        d_clean = d.strip()[:10]
        try:
            d = datetime.strptime(d_clean, "%Y-%m-%d").date()
        except Exception:
            return d
    if isinstance(d, datetime):
        d = d.date()
    try:
        jd = jdatetime.date.fromgregorian(date=d)
        return jd.strftime(format_str)
    except Exception:
        return str(d)

def parse_jalali_str(j_str: str) -> date:
    """تبدیل رشته شمسی (مثلاً 1403/05/20 یا 1403-05-20) به date میلادی برای ذخیره در دیتابیس"""
    if not j_str:
        return date.today()
    j_str = j_str.strip().replace("-", "/")
    parts = [int(p) for p in j_str.split("/") if p.strip()]
    if len(parts) == 3:
        jd = jdatetime.date(parts[0], parts[1], parts[2])
        return jd.togregorian()
    return date.today()

def format_rial(amount: int | float | str | None) -> str:
    """فرمت عدد به صورت ارقام سه‌رقم سه‌رقم جدا شده (مثلاً: 12,500,000)"""
    if amount is None or str(amount).strip() == "":
        return "0"
    try:
        # حذف هرگونه کاراکتر غیر از عدد و منفی
        clean_val = str(amount).replace(",", "").replace(" ", "").strip()
        return f"{int(clean_val):,}"
    except (ValueError, TypeError):
        return str(amount)
