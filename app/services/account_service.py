from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.account import Account


def get_user_total_balance(db: Session, user_id: int) -> int:
    """محاسبه مجموع موجودی تمام حساب‌های یک کاربر"""
    result = db.query(func.coalesce(func.sum(Account.balance), 0))\
               .filter(Account.user_id == user_id).scalar()
    return int(result or 0)


def get_account_by_id(db: Session, account_id: int, user_id: int) -> Account | None:
    """دریافت یک حساب متعلق به کاربر مشخص"""
    return db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
