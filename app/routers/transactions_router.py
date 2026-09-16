from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
import jdatetime

from starlette import status

from app.database import get_db
from app.models.account import Account
from app.models.person import Person
from app.models.transaction import Transaction
from app.auth import get_current_user
from app.utils.jalali import parse_jalali_str

from app.models.transaction import TransactionType

router = APIRouter(prefix="/transactions", tags=["Transactions"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")


def format_rial(value):
    if value is None:
        return "۰"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def format_jalali(value):
    if not value:
        return ""
    try:
        if isinstance(value, str):
            value = datetime.strptime(value[:10], "%Y-%m-%d").date()
        if isinstance(value, (date, datetime)):
            j_date = jdatetime.date.fromgregorian(date=value)
            return j_date.strftime("%Y/%m/%d")
    except Exception:
        pass
    return str(value)


templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = format_jalali


def parse_date_input(trans_date_str: str) -> date:
    if not trans_date_str:
        return date.today()
    try:
        if "/" in trans_date_str:
            parts = trans_date_str.strip().split("/")
            if len(parts) == 3 and len(parts[0]) == 4:
                return parse_jalali_str(trans_date_str)
        return datetime.strptime(trans_date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return date.today()


def revert_transaction_balance(db: Session, tx: Transaction):
    """اثر مالی یک تراکنش را روی حساب‌های مبدأ و مقصد خنثی می‌کند."""
    src_account = db.query(Account).filter(Account.id == tx.account_id).first()
    dest_id = getattr(tx, "destination_account_id", None)
    dest_account = db.query(Account).filter(Account.id == dest_id).first() if dest_id else None

    if tx.type == "INCOME" and src_account:
        src_account.balance -= tx.amount
    elif tx.type == "EXPENSE" and src_account:
        src_account.balance += tx.amount
    elif tx.type == "TRANSFER":
        if src_account:
            src_account.balance += tx.amount
        if dest_account:
            dest_account.balance -= tx.amount


def apply_transaction_balance(db: Session, trans_type: str, amount: int, src_account: Account,
                              dest_account: Account = None):
    """اثر مالی تراکنش جدید را اعمال می‌کند."""
    if trans_type == "INCOME" and src_account:
        src_account.balance += amount
    elif trans_type == "EXPENSE" and src_account:
        src_account.balance -= amount
    elif trans_type == "TRANSFER" and src_account and dest_account:
        src_account.balance -= amount
        dest_account.balance += amount


@router.get("")
def list_transactions(request: Request, db: Session = Depends(get_db)):
    transactions = db.query(Transaction).order_by(Transaction.trans_date.desc(), Transaction.id.desc()).all()
    accounts = db.query(Account).all()
    persons = db.query(Person).all()
    return templates.TemplateResponse(request= request,name="transactions/list.html",context= {

            "transactions": transactions,
            "accounts": accounts,
            "persons": persons,
            "today_jalali": jdatetime.date.today().strftime("%Y/%m/%d")
        }
    )


@router.post("/create")
def create_transaction(
        trans_type: str = Form(...),
        account_id: int = Form(...),
        amount: int = Form(...),
        category: str = Form(...),
        trans_date: str = Form(...),
        destination_account_id: int = Form(None),
        person_id: int = Form(None),
        description: str = Form(None),
        db: Session = Depends(get_db)
):

    # ۱. اعتبارسنجی مبلغ
    if amount <= 0:
        return RedirectResponse(
            url="/transactions?error=invalid_amount",
            status_code=status.HTTP_303_SEE_OTHER,
        )



    # ۳. اعتبارسنجی حساب مبدأ
    account = (
        db.query(Account)
        .filter(Account.id == account_id)
        .with_for_update()
        .first()
    )
    if not account:
        return RedirectResponse(
            url="/transactions?error=source_account_not_found",
            status_code=status.HTTP_303_SEE_OTHER,
        )




    real_date = parse_date_input(trans_date)
    src_account = db.query(Account).filter(Account.id == account_id).first()
    if not src_account:
        return RedirectResponse(url="/transactions", status_code=303)

    dest_account = None
    if trans_type == "TRANSFER" and destination_account_id and destination_account_id != account_id:
        dest_account = db.query(Account).filter(Account.id == destination_account_id).first()

    # اعمال اثر مالی
    apply_transaction_balance(db, trans_type, amount, src_account, dest_account)

    # ایجاد رکورد تراکنش با سازگاری ستون‌ها
    tx_kwargs = {
        "account_id": account_id,
        "type": trans_type,
        "category": category,
        "amount": amount,
        "trans_date": real_date,
        "description": description
    }

    if hasattr(Transaction, "destination_account_id") and trans_type == "TRANSFER" and dest_account:
        tx_kwargs["destination_account_id"] = dest_account.id

    if hasattr(Transaction, "person_id") and person_id:
        tx_kwargs["person_id"] = person_id

    tx = Transaction(**tx_kwargs)
    db.add(tx)
    db.commit()

    return RedirectResponse(url="/transactions", status_code=303)


@router.post("/{trans_id}/update")
def update_transaction(
        trans_id: int,
        trans_type: str = Form(...),
        account_id: int = Form(...),
        amount: int = Form(...),
        category: str = Form(...),
        trans_date: str = Form(...),
        destination_account_id: int = Form(None),
        person_id: int = Form(None),
        description: str = Form(None),
        db: Session = Depends(get_db)
):
    # ۱. اعتبارسنجی مبلغ
    if amount <= 0:
        return RedirectResponse(
            url="/transactions?error=invalid_amount",
            status_code=status.HTTP_303_SEE_OTHER,
        )



    # ۳. اعتبارسنجی حساب مبدأ
    account = (
        db.query(Account)
        .filter(Account.id == account_id)
        .with_for_update()
        .first()
    )
    if not account:
        return RedirectResponse(
            url="/transactions?error=source_account_not_found",
            status_code=status.HTTP_303_SEE_OTHER,
        )


    tx = db.query(Transaction).filter(Transaction.id == trans_id).first()
    if not tx:
        return RedirectResponse(url="/transactions", status_code=303)

    # 1. خنثی کردن اثر تراکنش قبلی
    revert_transaction_balance(db, tx)

    # 2. دریافت حساب‌های جدید
    src_account = db.query(Account).filter(Account.id == account_id).first()
    dest_account = None
    if trans_type == "TRANSFER" and destination_account_id and destination_account_id != account_id:
        dest_account = db.query(Account).filter(Account.id == destination_account_id).first()

    # 3. اعمال اثر مالی جدید
    apply_transaction_balance(db, trans_type, amount, src_account, dest_account)

    # 4. به‌روزرسانی مقادیر رکورد
    tx.type = trans_type
    tx.account_id = account_id
    tx.amount = amount
    tx.category = category
    tx.trans_date = parse_date_input(trans_date)
    tx.description = description

    if hasattr(Transaction, "destination_account_id"):
        tx.destination_account_id = dest_account.id if (trans_type == "TRANSFER" and dest_account) else None

    if hasattr(Transaction, "person_id"):
        tx.person_id = person_id if person_id else None

    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@router.post("/{trans_id}/delete")
def delete_transaction(trans_id: int, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == trans_id).first()
    if not tx:
        return RedirectResponse(url="/transactions", status_code=303)

    # جلوگیری از حذف تراکنش‌های وابسته به چک یا تسویه
    if getattr(tx, "cheque_id", None) or getattr(tx, "debt_id", None):
        # این تراکنش از بخش چک یا تسویه ایجاد شده و باید از همان مبدا مدیریت/ابطال شود
        return RedirectResponse(url="/transactions?error=linked_transaction", status_code=303)

    revert_transaction_balance(db, tx)
    db.delete(tx)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)
