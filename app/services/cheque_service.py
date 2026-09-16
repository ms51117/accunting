from datetime import date, datetime

from sqlalchemy.orm import Session
from app.models.cheque import Cheque, ChequeStatus, ChequeType
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType


def clear_cheque(db: Session, cheque_id: int, target_account_id: int = None) -> Cheque:
    cheque = db.query(Cheque).filter(Cheque.id == cheque_id).first()
    if not cheque:
        raise ValueError("چک مورد نظر یافت نشد.")

    if cheque.status == ChequeStatus.CLEARED.value if hasattr(ChequeStatus, 'value') else cheque.status == "CLEARED":
        raise ValueError("این چک قبلاً وصول شده است.")

    account_id = target_account_id or cheque.account_id
    if not account_id:
        raise ValueError("حساب بانکی جهت وصول چک مشخص نشده است.")

    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError("حساب بانکی مورد نظر یافت نشد.")

    # اعمال اثر مالی بر موجودی و ثبت تراکنش
    is_receivable = cheque.type in [ChequeType.RECEIVABLE, "RECEIVABLE"] if hasattr(ChequeType, 'RECEIVABLE') else cheque.type == "RECEIVABLE"

    if is_receivable:
        account.balance += cheque.amount
        tx_type = TransactionType.INCOME if hasattr(TransactionType, 'INCOME') else "INCOME"
        tx_desc = f"وصول چک دریافتی شماره {cheque.sayad_number or cheque.cheque_number or ''} - طرف حساب: {cheque.person.full_name if cheque.person else '---'}"
    else:
        account.balance -= cheque.amount
        tx_type = TransactionType.EXPENSE if hasattr(TransactionType, 'EXPENSE') else "EXPENSE"
        tx_desc = f"پاس شدن چک پرداختی شماره {cheque.sayad_number or cheque.cheque_number or ''} - طرف حساب: {cheque.person.full_name if cheque.person else '---'}"

    cheque.status = ChequeStatus.CLEARED if hasattr(ChequeStatus, 'CLEARED') else "CLEARED"
    cheque.account_id = account_id

    transaction = Transaction(
        account_id=target_account_id,
        type=TransactionType.INCOME.value if cheque.type == ChequeType.RECEIVABLE.value else TransactionType.EXPENSE.value,
        category="وصول چک",
        amount=cheque.amount,
        trans_date=datetime.now().date(),
        description=f"وصول چک شماره {cheque.cheque_number or cheque.sayad_number}",
        cheque_id=cheque.id  # <-- اتصال تراکنش به چک
    )
    db.add(transaction)
    db.commit()
    db.refresh(cheque)
    return cheque


def bounce_cheque(db: Session, cheque_id: int) -> Cheque:
    cheque = db.query(Cheque).filter(Cheque.id == cheque_id).first()
    if not cheque:
        raise ValueError("چک مورد نظر یافت نشد.")

    cleared_val = ChequeStatus.CLEARED if hasattr(ChequeStatus, 'CLEARED') else "CLEARED"
    if cheque.status == cleared_val:
        raise ValueError("چک وصول‌شده را نمی‌توان مستقیماً برگشت زد.")

    cheque.status = ChequeStatus.BOUNCED if hasattr(ChequeStatus, 'BOUNCED') else "BOUNCED"
    db.commit()
    db.refresh(cheque)
    return cheque
