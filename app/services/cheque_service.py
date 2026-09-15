from sqlalchemy.orm import Session
from datetime import date
from app.models.cheque import Cheque
from app.models.account import Account
from app.models.transaction import Transaction

def process_cheque_status_change(db: Session, cheque: Cheque, new_status: str, account_id: int | None = None):
    old_status = cheque.status
    if old_status == new_status:
        return

    target_account_id = account_id or cheque.account_id
    if not target_account_id and new_status == "CLEARED":
        raise ValueError("برای وصول چک باید یک حساب بانکی مشخص شود.")

    account = db.query(Account).filter(Account.id == target_account_id).first() if target_account_id else None

    # اگر قبلا پاس شده بوده و الان تغییر وضعیت میده، اثر قبلی خنثی بشه
    if old_status == "CLEARED" and cheque.account:
        if cheque.type == "RECEIVABLE":
            cheque.account.balance -= cheque.amount
        elif cheque.type == "PAYABLE":
            cheque.account.balance += cheque.amount

    # اعمال وضعیت جدید
    if new_status == "CLEARED" and account:
        cheque.account_id = account.id
        cheque.cleared_date = date.today()
        if cheque.type == "RECEIVABLE": # چک دریافتی پاس شد -> پول میاد به حساب
            account.balance += cheque.amount
            # ثبت تراکنش متناظر
            db.add(Transaction(
                account_id=account.id,
                type="INCOME",
                category="وصول چک",
                amount=cheque.amount,
                trans_date=date.today(),
                description=f"وصول چک دریافتی شماره {cheque.cheque_number} - {cheque.person.full_name}"
            ))
        elif cheque.type == "PAYABLE": # چک پرداختی ما پاس شد -> پول از حساب کسر میشه
            account.balance -= cheque.amount
            db.add(Transaction(
                account_id=account.id,
                type="EXPENSE",
                category="پاس شدن چک",
                amount=cheque.amount,
                trans_date=date.today(),
                description=f"پاس شدن چک پرداختی شماره {cheque.cheque_number} - {cheque.person.full_name}"
            ))

    cheque.status = new_status
    db.commit()
