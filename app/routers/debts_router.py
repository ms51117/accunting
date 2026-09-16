from datetime import datetime, date
from typing import Optional

import jdatetime
from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.debt import Debt, DebtType, DebtStatus
from app.models.transaction import Transaction, TransactionType
from app.utils.jalali import parse_jalali_str
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse



router = APIRouter(prefix="/debts", tags=["Debts"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")
def format_rial(value):
    if value is None:
        return "0"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)

def format_jalali(value):
    if not value:
        return "-"
    return str(value)

# ۳. ثبت فیلترها روی محیط Jinja2
templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = format_jalali

def parse_date_input(date_str: str):
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    try:
        if "/" in date_str:
            parts = [int(p) for p in date_str.split("/")]
            if len(parts) == 3:
                return jdatetime.date(parts[0], parts[1], parts[2]).togregorian()
        elif "-" in date_str:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None
    return None

@router.get("/")
def debts_list(request: Request, db: Session = Depends(get_db)):
    debts = db.query(Debt).order_by(Debt.created_at.desc()).all()
    persons = db.query(Person).all()
    accounts = db.query(Account).all()
    return templates.TemplateResponse(
        request=request,
        name="debts/list.html",
        context= {
            "debts": debts,
            "persons": persons,
            "accounts": accounts
        })

@router.post("/create")
def create_debt(
    type: str = Form(...),
    person_id: int = Form(...),
    amount: int = Form(...),
    account_id: int = Form(None),  # حساب مبدا/مقصد
    date: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    if amount <= 0:
        return RedirectResponse(url="/debts?error=invalid_amount", status_code=status.HTTP_303_SEE_OTHER)

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        return RedirectResponse(url="/debts?error=person_not_found", status_code=status.HTTP_303_SEE_OTHER)

    trans_date = parse_date_input(date) or datetime.now().date()

    # ایجاد رکورد بدهی/طلب
    new_debt = Debt(
        type=type,
        person_id=person_id,
        amount=amount,
        paid_amount=0,
        due_date=trans_date,
        description=description,
        status=DebtStatus.ACTIVE.value
    )
    db.add(new_debt)
    db.flush()  # دریافت شناسه new_debt.id

    # اگر حسابی انتخاب شده باشد، تراکنش متناظر را ثبت می‌کنیم
    if account_id:
        account = db.query(Account).filter(Account.id == account_id).with_for_update().first()
        if not account:
            db.rollback()
            return RedirectResponse(url="/debts?error=account_not_found", status_code=status.HTTP_303_SEE_OTHER)

        if type == DebtType.RECEIVABLE.value:
            # طلبکاری (ما پول قرض دادیم): پول از حساب کسر می‌شود
            if account.balance < amount:
                db.rollback()
                return RedirectResponse(url="/debts?error=insufficient_funds", status_code=status.HTTP_303_SEE_OTHER)
            account.balance -= amount
            tx_type = TransactionType.EXPENSE.value
            tx_cat = "پرداخت قرض/وام"
        else:
            # بدهکاری (ما پول قرض گرفتیم): پول به حساب واریز می‌شود
            account.balance += amount
            tx_type = TransactionType.INCOME.value
            tx_cat = "دریافت قرض/وام"

        tx_desc = f"{tx_cat} به/از {person.full_name}"
        if description:
            tx_desc += f" - {description}"

        transaction = Transaction(
            account_id=account.id,
            type=tx_type,
            category=tx_cat,
            amount=amount,
            trans_date=trans_date,
            description=tx_desc,
            debt_id=new_debt.id
        )
        db.add(transaction)

    db.commit()
    return RedirectResponse(url="/debts?success=debt_created", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{debt_id}/pay")
def pay_debt(
    debt_id: int,
    pay_amount: int = Form(...),
    account_id: int = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    if pay_amount <= 0:
        return RedirectResponse(url="/debts?error=invalid_pay_amount", status_code=status.HTTP_303_SEE_OTHER)

    debt = db.query(Debt).filter(Debt.id == debt_id).with_for_update().first()
    if not debt:
        return RedirectResponse(url="/debts?error=debt_not_found", status_code=status.HTTP_303_SEE_OTHER)

    remaining_balance = debt.amount - debt.paid_amount
    if remaining_balance <= 0 or debt.status == DebtStatus.SETTLED.value:
        return RedirectResponse(url="/debts?error=already_settled", status_code=status.HTTP_303_SEE_OTHER)

    if pay_amount > remaining_balance:
        return RedirectResponse(url="/debts?error=amount_exceeds_remaining", status_code=status.HTTP_303_SEE_OTHER)

    account = db.query(Account).filter(Account.id == account_id).with_for_update().first()
    if not account:
        return RedirectResponse(url="/debts?error=account_not_found", status_code=status.HTTP_303_SEE_OTHER)

    debt.paid_amount += pay_amount
    if debt.paid_amount >= debt.amount:
        debt.status = DebtStatus.SETTLED.value

    # ثبت تراکنش تسویه
    if debt.type == DebtType.RECEIVABLE.value:
        # وصول طلب: پول وارد حساب می‌شود
        account.balance += pay_amount
        tx_type = TransactionType.INCOME.value
        tx_cat = "تسویه طلب"
    else:
        # پرداخت بدهی: پول از حساب کم می‌شود
        if account.balance < pay_amount:
            db.rollback()
            return RedirectResponse(url="/debts?error=insufficient_funds", status_code=status.HTTP_303_SEE_OTHER)
        account.balance -= pay_amount
        tx_type = TransactionType.EXPENSE.value
        tx_cat = "تسویه بدهی"

    person_name = debt.person.full_name if debt.person else "شخص"
    tx_desc = f"{tx_cat} ({person_name})"
    if description:
        tx_desc += f" - {description}"

    transaction = Transaction(
        account_id=account.id,
        type=tx_type,
        category=tx_cat,
        amount=pay_amount,
        trans_date=datetime.now().date(),
        description=tx_desc,
        debt_id=debt.id
    )
    db.add(transaction)
    db.commit()

    return RedirectResponse(url="/debts?success=paid", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{debt_id}/delete")
def delete_debt(debt_id: int, db: Session = Depends(get_db)):
    debt = db.query(Debt).filter(Debt.id == debt_id).first()
    if not debt:
        return RedirectResponse(url="/debts?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # 1. واکشی کلیه تراکنش‌های متصل به این بدهی
    transactions = db.query(Transaction).filter(Transaction.debt_id == debt.id).all()

    # 2. برگرداندن (Revert) اثر تراکنش‌ها از مانده حساب‌ها
    for tx in transactions:
        account = db.query(Account).filter(Account.id == tx.account_id).with_for_update().first()
        if account:
            if tx.type == TransactionType.INCOME.value:
                account.balance -= tx.amount
            elif tx.type == TransactionType.EXPENSE.value:
                account.balance += tx.amount
        db.delete(tx)

    # 3. حذف رکورد بدهی
    db.delete(debt)
    db.commit()

    return RedirectResponse(url="/debts?success=deleted", status_code=status.HTTP_303_SEE_OTHER)