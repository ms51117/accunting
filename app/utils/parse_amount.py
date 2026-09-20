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
