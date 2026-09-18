from datetime import datetime, date

import jdatetime
from fastapi import APIRouter, Request, Depends, Form, responses, status, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.cheque import Cheque, ChequeStatus, ChequeType
from app.models.transaction import Transaction, TransactionType
from app.services.cheque_service import clear_cheque, bounce_cheque
from app.utils.jalali import parse_jalali_str

router = APIRouter(prefix="/cheques", tags=["Cheques"], dependencies=[Depends(get_current_user)])
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
    try:
        if isinstance(value, str):
            # اگر ورودی رشته است، اول به آبجکت تاریخ میلادی تبدیل شود
            from datetime import datetime
            value = datetime.strptime(value, "%Y-%m-%d").date()
        # تبدیل میلادی به شمسی
        j_date = jdatetime.date.fromgregorian(date=value)
        return j_date.strftime("%Y/%m/%d")
    except Exception:
        return str(value)

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = format_jalali


@router.get("")
def list_cheques(request: Request, type_filter: str = None, status_filter: str = None, db: Session = Depends(get_db)):
    query = db.query(Cheque)
    if type_filter:
        query = query.filter(Cheque.type == type_filter)
    if status_filter:
        query = query.filter(Cheque.status == status_filter)

    cheques = query.order_by(Cheque.due_date.asc()).all()
    accounts = db.query(Account).all()
    persons = db.query(Person).all()

    return templates.TemplateResponse(
        request=request,
        name="cheques/list.html",
        context={
            "cheques": cheques,
            "accounts": accounts,
            "persons": persons,
            "type_filter": type_filter or "",
            "status_filter": status_filter or ""
        }
    )


@router.post("/create")
def create_cheque(
    cheque_type: str = Form(...),
    person_id: int = Form(...),
    amount: int = Form(...),
    due_date: str = Form(...),
    account_id: int = Form(None),
    issue_date: str = Form(None),
    serial_number: str = Form(None),
    sayad_number: str = Form(None),
    bank_name: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        g_due_date = parse_jalali_str(due_date.strip())
    except Exception:
        g_due_date = date.today()

    g_issue_date = None
    if issue_date and issue_date.strip():
        try:
            g_issue_date = parse_jalali_str(issue_date.strip())
        except Exception:
            g_issue_date = None

    new_cheque = Cheque(
        type=cheque_type,
        person_id=person_id,
        account_id=account_id if account_id else None,
        amount=amount,
        due_date=g_due_date,
        issue_date=g_issue_date,
        cheque_number=serial_number.strip() if serial_number else None,
        sayad_number=sayad_number.strip() if sayad_number else None,
        bank_name=bank_name.strip() if bank_name else None,
        description=description.strip() if description else None,
        status=ChequeStatus.PENDING.value
    )
    db.add(new_cheque)
    db.commit()
    return responses.RedirectResponse(url="/cheques", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cheque_id}/clear")
def process_clear_cheque(cheque_id: int, account_id: int = Form(...), db: Session = Depends(get_db)):
    clear_cheque(db=db, cheque_id=cheque_id, target_account_id=account_id)
    return responses.RedirectResponse(url="/cheques", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cheque_id}/bounce")
def process_bounce_cheque(cheque_id: int, db: Session = Depends(get_db)):
    bounce_cheque(db=db, cheque_id=cheque_id)
    return responses.RedirectResponse(url="/cheques", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cheque_id}/edit")
def edit_cheque(
    cheque_id: int,
    cheque_type: str = Form(...),
    person_id: int = Form(...),
    amount: int = Form(...),
    due_date: str = Form(...),
    status: str = Form(...),
    sayad_number: str = Form(None),
    bank_name: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    cheque = db.query(Cheque).filter(Cheque.id == cheque_id).first()
    if not cheque:
        raise HTTPException(status_code=404, detail="چک یافت نشد")

    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = parse_jalali_str(due_date.strip())
        except Exception:
            try:
                parsed_due_date = datetime.strptime(due_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                parsed_due_date = cheque.due_date

    # به‌روزرسانی فیلدها (اصلاح نام ستون type)
    cheque.type = cheque_type
    cheque.person_id = person_id
    cheque.amount = amount
    cheque.due_date = parsed_due_date
    cheque.status = status
    cheque.sayad_number = sayad_number.strip() if sayad_number else None
    cheque.bank_name = bank_name.strip() if bank_name else None
    cheque.description = description.strip() if description else None

    db.commit()
    return RedirectResponse(url="/cheques", status_code=303)


# --- حذف چک با Revert خودکار مانده و حذف تراکنش‌های وابسته ---
@router.post("/{cheque_id}/delete")
def delete_cheque(
    cheque_id: int,
    db: Session = Depends(get_db)
):
    cheque = db.query(Cheque).filter(Cheque.id == cheque_id).first()
    if not cheque:
        raise HTTPException(status_code=404, detail="چک یافت نشد")

    # ۱. واکشی کلیه تراکنش‌های متصل به این چک
    transactions = db.query(Transaction).filter(Transaction.cheque_id == cheque.id).all()

    # ۲. برگرداندن (Revert) اثر مالی تراکنش‌ها روی مانده حساب
    for tx in transactions:
        account = db.query(Account).filter(Account.id == tx.account_id).with_for_update().first()
        if account:
            if tx.type == TransactionType.INCOME.value:
                account.balance -= tx.amount
            elif tx.type == TransactionType.EXPENSE.value:
                account.balance += tx.amount
        db.delete(tx)

    # ۳. حذف خود رکورد چک
    db.delete(cheque)
    db.commit()

    return RedirectResponse(url="/cheques", status_code=status.HTTP_303_SEE_OTHER)
