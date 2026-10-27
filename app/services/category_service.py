from sqlalchemy.orm import Session
from app.models.category import Category


def get_or_create_category(
    db: Session,
    user_id: int,
    title: str,
    trans_type: str = "BOTH",
    color: str = None,
    icon: str = None
) -> Category:
    """یافتن یا ایجاد خودکار دسته‌بندی برای کاربر با مقادیر بهینه"""
    clean_title = (title or "سایر").strip()
    if not clean_title:
        clean_title = "سایر"

    cat = (
        db.query(Category)
        .filter(Category.user_id == user_id, Category.title == clean_title)
        .first()
    )
    if cat:
        return cat

    # تعیین هوشمند رنگ و آیکون در صورت عدم ارسال
    if not color or not icon:
        if "چک" in clean_title:
            color, icon = "#06b6d4", "card-checklist"
        elif "قرض" in clean_title or "وام" in clean_title or "طلب" in clean_title or "بدهی" in clean_title:
            color, icon = "#10b981", "arrow-repeat"
        elif trans_type == "INCOME":
            color, icon = "#10b981", "wallet2"
        elif trans_type == "EXPENSE":
            color, icon = "#ef4444", "receipt"
        else:
            color, icon = "#3b82f6", "tag"

    cat = Category(
        user_id=user_id,
        title=clean_title,
        type=trans_type,
        color=color or "#3b82f6",
        icon=icon or "tag"
    )
    db.add(cat)
    db.flush()
    return cat
