from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.cheque import Cheque
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.jalali import format_rial, to_jalali_str
from app.utils.parse_amount import parse_int_amount

router = APIRouter(prefix="/accounts", tags=["Accounts"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


@router.get("")
def list_accounts(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    accounts = (
        db.query(Account)
        .filter(Account.user_id == current_user.id)
        .order_by(Account.id.desc())
        .all()
    )
    total_balance = sum(acc.balance or 0 for acc in accounts)
    return templates.TemplateResponse(
        request=request,
        name="accounts/list.html",
        context={
            "total_balance": total_balance,
            "accounts": accounts,
            "user": current_user
        },
    )


@router.post("/create")
def create_account(
    title: str = Form(...),
    bank_name: str = Form(None),
    account_number: str = Form(None),
    card_number: str = Form(None),
    sheba: str = Form(None),
    balance: str = Form("0"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_title = title.strip()
    if not clean_title:
        return RedirectResponse(url="/accounts?error=نام_حساب_الزامی_است", status_code=status.HTTP_303_SEE_OTHER)

    clean_balance = parse_int_amount(balance)

    acc = Account(
        user_id=current_user.id,
        title=clean_title,
        bank_name=bank_name.strip() if bank_name else None,
        account_number=account_number.strip() if account_number else None,
        card_number=card_number.strip() if card_number else None,
        sheba=sheba.strip() if sheba else None,
        balance=clean_balance
    )
    db.add(acc)
    db.commit()
    return RedirectResponse(url="/accounts?msg=حساب_جدید_با_موفقیت_ثبت_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{account_id}/edit")
def edit_account(
    account_id: int,
    title: str = Form(...),
    bank_name: str = Form(None),
    card_number: str = Form(None),
    sheba: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == current_user.id)
        .first()
    )
    if not account:
        return RedirectResponse(url="/accounts?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    clean_title = title.strip()
    if not clean_title:
        return RedirectResponse(url="/accounts?error=نام_حساب_الزامی_است", status_code=status.HTTP_303_SEE_OTHER)

    account.title = clean_title
    account.bank_name = bank_name.strip() if bank_name else None
    account.card_number = card_number.strip() if card_number else None
    account.sheba = sheba.strip() if sheba else None

    db.commit()
    return RedirectResponse(url="/accounts?msg=حساب_با_موفقیت_ویرایش_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{account_id}/delete")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    acc = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == current_user.id)
        .first()
    )
    if not acc:
        return RedirectResponse(url="/accounts?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # بررسی وجود تراکنش یا چک متصل به حساب
    has_transactions = db.query(Transaction).filter(
        (Transaction.account_id == account_id) | (Transaction.destination_account_id == account_id)
    ).first()

    has_cheques = db.query(Cheque).filter(Cheque.account_id == account_id).first()

    if has_transactions or has_cheques:
        return RedirectResponse(url="/accounts?error=has_dependencies", status_code=status.HTTP_303_SEE_OTHER)

    db.delete(acc)
    db.commit()
    return RedirectResponse(url="/accounts?msg=حساب_با_موفقیت_حذف_شد", status_code=status.HTTP_303_SEE_OTHER)