from datetime import date
from sqlalchemy.orm import Session
from app.models.cheque import Cheque, ChequeStatus, ChequeType
from app.models.account import Account
from app.models.transaction import Transaction


def get_status_val(status_obj):
    """استخراج مقدار متنی وضعیت چه به‌صورت Enum چه رشته"""
    if hasattr(status_obj, "value"):
        return status_obj.value
    return str(status_obj)


def clear_cheque(db: Session, cheque_id: int, user_id: int, target_account_id: int = None) -> Cheque:
    """
    وصول چک، افزایش/کاهش موجودی حساب و ثبت خودکار تراکنش برای کاربر مشخص
    """
    # ۱. یافتن چک متعلق به خود کاربر
    cheque = (
        db.query(Cheque)
        .filter(Cheque.id == cheque_id, Cheque.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not cheque:
        raise ValueError("چک مورد نظر یافت نشد یا دسترسی به آن مجاز نیست.")

    current_status = get_status_val(cheque.status)
    cleared_val = get_status_val(ChequeStatus.CLEARED) if hasattr(ChequeStatus, "CLEARED") else "CLEARED"

    if current_status == cleared_val:
        raise ValueError("این چک قبلاً وصول شده است.")

    # ۲. تعیین حساب و اعتبارسنجی مالکیت حساب برای کاربر
    acc_id = target_account_id or cheque.account_id
    if not acc_id:
        raise ValueError("برای وصول چک باید حسابی را انتخاب یا مشخص کنید.")

    account = (
        db.query(Account)
        .filter(Account.id == acc_id, Account.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not account:
        raise ValueError("حساب مشخص‌شده یافت نشد یا متعلق به شما نیست.")

    # ۳. محاسبه تغییر مانده و تعیین نوع تراکنش
    current_type = get_status_val(cheque.type)
    rec_val = get_status_val(ChequeType.RECEIVABLE) if hasattr(ChequeType, "RECEIVABLE") else "RECEIVABLE"

    if current_type == rec_val:
        # چک دریافتی -> افزایش موجودی حساب (درآمد)
        account.balance = (account.balance or 0) + (cheque.amount or 0)
        tx_type = "INCOME"
        tx_desc = f"وصول چک دریافتی شماره {cheque.cheque_number or '-'}"
    else:
        # چک پرداختی -> کاهش موجودی حساب (هزینه)
        account.balance = (account.balance or 0) - (cheque.amount or 0)
        tx_type = "EXPENSE"
        tx_desc = f"پاس شدن چک پرداختی شماره {cheque.cheque_number or '-'}"

    # ۴. به‌روزرسانی وضعیت چک
    cheque.status = ChequeStatus.CLEARED if hasattr(ChequeStatus, "CLEARED") else "CLEARED"
    cheque.account_id = account.id

    # ۵. ثبت تراکنش متصل به چک
    tx = Transaction(
        user_id=user_id,
        account_id=account.id,
        type=tx_type,
        amount=cheque.amount,
        trans_date=date.today(),
        category="وصول چک",
        description=tx_desc,
        person_id=cheque.person_id,
        cheque_id=cheque.id
    )
    db.add(tx)

    db.commit()
    db.refresh(cheque)
    return cheque


def bounce_cheque(db: Session, cheque_id: int, user_id: int) -> Cheque:
    """
    برگشت زدن چک متعلق به کاربر مشخص
    """
    cheque = (
        db.query(Cheque)
        .filter(Cheque.id == cheque_id, Cheque.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not cheque:
        raise ValueError("چک مورد نظر یافت نشد یا دسترسی به آن مجاز نیست.")

    current_status = get_status_val(cheque.status)
    cleared_val = get_status_val(ChequeStatus.CLEARED) if hasattr(ChequeStatus, "CLEARED") else "CLEARED"

    if current_status == cleared_val:
        raise ValueError("چک وصول‌شده را نمی‌توان مستقیماً برگشت زد.")

    cheque.status = ChequeStatus.BOUNCED if hasattr(ChequeStatus, "BOUNCED") else "BOUNCED"
    db.commit()
    db.refresh(cheque)
    return cheque
