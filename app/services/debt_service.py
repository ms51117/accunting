from datetime import date
from sqlalchemy.orm import Session
from app.models.debt import Debt, DebtStatus, DebtType
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType


def get_active_user_debts(db: Session, user_id: int):
    """واکشی بدهی‌ها و طلب‌های فعال کاربر جاری"""
    return (
        db.query(Debt)
        .filter(Debt.user_id == user_id, Debt.status == DebtStatus.ACTIVE.value)
        .all()
    )


def calculate_debt_remaining(debt: Debt) -> int:
    """محاسبه مانده تسویه‌نشده یک بدهی/طلب"""
    return max(0, int(debt.amount) - int(debt.paid_amount or 0))
