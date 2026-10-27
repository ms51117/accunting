def parse_int_amount(val: any) -> int:
    """تبدیل رشته‌های عددی شامل کاما یا ارقام فارسی به عدد صحیح"""
    if val is None:
        return 0
    val_str = str(val).strip()
    # تبدیل ارقام فارسی و عربی به انگلیسی
    persian_arabic_digits = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
    english_digits = "01234567890123456789"
    translation_table = str.maketrans(persian_arabic_digits, english_digits)
    val_str = val_str.translate(translation_table)
    # حذف کاما و فاصله‌ها
    val_str = val_str.replace(",", "").replace(" ", "")
    try:
        return int(val_str)
    except (ValueError, TypeError):
        return 0


def parse_optional_int(val: any) -> int | None:
    """تبدیل امن ورودی‌های فرم یا کوئری پارامتر به عدد صحیح یا None در صورت خالی بودن"""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ("none", "null", "undefined", ""):
        return None
    persian_arabic_digits = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
    english_digits = "01234567890123456789"
    translation_table = str.maketrans(persian_arabic_digits, english_digits)
    val_str = val_str.translate(translation_table).replace(",", "").replace(" ", "")
    try:
        return int(val_str)
    except (ValueError, TypeError):
        return None

