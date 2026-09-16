from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.debt import Debt
from app.models.transaction import Transaction
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


@router.get("")
def list_debts(request: Request, db: Session = Depends(get_db)):
    debts = db.query(Debt).order_by(Debt.id.desc()).all()
    persons = db.query(Person).all()
    accounts = db.query(Account).all()
    return templates.TemplateResponse(
        request=request,
        name="debts/list.html",
        context={
            "debts": debts,
        "persons": persons,
        "accounts": accounts
    })


@router.post("/create")
def create_debt(
        type: str = Form(...),  # RECEIVABLE (طلب ما از شخص), PAYABLE (بدهی ما به شخص)
        person_id: int = Form(...),
        amount: int = Form(...),
        due_date: str = Form(None),
        description: str = Form(None),
        db: Session = Depends(get_db)
):
    # ۱. اعتبارسنجی مبلغ
    if amount <= 0:
        return RedirectResponse(
            url="/debts?error=invalid_amount",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    g_due_date = None
    if due_date:
        try:
            g_due_date = parse_jalali_str(due_date.strip()) if "/" in due_date else datetime.strptime(
                due_date.strip(), "%Y-%m-%d").date()
        except Exception:
            g_due_date = None


    debt = Debt(
        type=type,
        person_id=person_id,
        amount=amount,
        paid_amount=0,
        due_date=g_due_date,
        description=description.strip() if description else None,
        status="ACTIVE"
    )
    db.add(debt)
    db.commit()
    return responses.RedirectResponse(url="/debts", status_code=status.HTTP_302_FOUND)


@router.post("/{debt_id}/update")
def update_debt(
    debt_id: int,
    type: str = Form(...),
    person_id: int = Form(...),
    amount: int = Form(...),
    due_date: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    # ۱. اعتبارسنجی مبلغ
    if amount <= 0:
        return RedirectResponse(
            url="/debts?error=invalid_amount",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    debt = db.query(Debt).filter(Debt.id == debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="رکورد یافت نشد")

    parsed_due_date = None
    if due_date and due_date.strip():
        try:
            parsed_due_date = parse_jalali_str(due_date.strip())
        except Exception:
            parsed_due_date = None

    debt.type = type
    debt.person_id = person_id
    debt.amount = amount
    debt.due_date = parsed_due_date
    debt.description = description.strip() if description else None

    # بررسی وضعیت جدید بر اساس مبالغ
    if debt.paid_amount >= debt.amount:
        debt.status = "SETTLED"
    else:
        debt.status = "ACTIVE"

    db.commit()
    return RedirectResponse(url="/debts", status_code=status.HTTP_303_SEE_OTHER)



@router.post("/{debt_id}/delete")
def delete_debt(debt_id: int, db: Session = Depends(get_db)):
    debt = db.query(Debt).filter(Debt.id == debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="رکورد یافت نشد")

    db.delete(debt)
    db.commit()
    return RedirectResponse(url="/debts", status_code=status.HTTP_303_SEE_OTHER)



@router.post("/{debt_id}/pay")
def pay_debt_installment(
        debt_id: int,
        pay_amount: int = Form(...),
        account_id: int = Form(...),
        db: Session = Depends(get_db)
):
    debt = db.query(Debt).filter(Debt.id == debt_id).first()
    account = db.query(Account).filter(Account.id == account_id).first()

    if not debt or not account or pay_amount <= 0:
        return responses.RedirectResponse(url="/debts", status_code=status.HTTP_302_FOUND)

    # ۳. بررسی وضعیت بدهی (آیا از قبل تسویه شده؟)
    remaining_balance = debt.amount - debt.paid_amount
    if debt.status == "SETTLED" or remaining_balance <= 0:
        return RedirectResponse(
            url="/debts?error=already_settled",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if pay_amount > remaining_balance:
        return RedirectResponse(
            url="/debts?error=amount_exceeds_remaining",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # به‌روزرسانی مانده طلب/بدهی
    debt.paid_amount += pay_amount
    if debt.paid_amount >= debt.amount:
        debt.status = "SETTLED"

    # ثبت تراکنش متناظر و اثر روی حساب
    if debt.type == "RECEIVABLE":
        # دریافت طلب -> افزایش موجودی حساب (درآمد/دریافت)
        account.balance += pay_amount
        tx = Transaction(
            account_id=account.id,
            person_id=debt.person_id,
            type="INCOME",
            category="تسویه طلب",
            amount=pay_amount,
            trans_date=date.today(),
            description=f"تسویه طلب از {debt.person.full_name}"
        )
    else:
        # پرداخت بدهی -> کاهش موجودی حساب (هزینه/پرداخت)
        account.balance -= pay_amount
        tx = Transaction(
            account_id=account.id,
            person_id=debt.person_id,
            type="EXPENSE",
            category="تسویه بدهی",
            amount=pay_amount,
            trans_date=date.today(),
            description=f"پرداخت بدهی به {debt.person.full_name}"
        )

    db.add(tx)
    db.commit()
    return responses.RedirectResponse(url="/debts", status_code=status.HTTP_302_FOUND)
