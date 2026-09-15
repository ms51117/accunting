import jdatetime
from datetime import datetime, date

def to_jalali_str(d: date | datetime | None, format_str: str = "%Y/%m/%d") -> str:
    if not d:
        return "-"
    if isinstance(d, datetime):
        d = d.date()
    jd = jdatetime.date.fromgregorian(date=d)
    return jd.strftime(format_str)

def parse_jalali_str(j_str: str) -> date:
    """تبدیل رشته شمسی 1403/05/20 به date میلادی برای ذخیره در دیتابیس"""
    j_str = j_str.strip().replace("-", "/")
    parts = [int(p) for p in j_str.split("/")]
    jd = jdatetime.date(parts[0], parts[1], parts[2])
    return jd.togregorian()

def format_rial(amount: int | float | None) -> str:
    """فرمت عدد به صورت لاتین با کاما (مثلاً: 12,500,000)"""
    if amount is None:
        return "0"
    return f"{int(amount):,}"
