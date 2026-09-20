from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse

from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from fastapi import HTTPException
from app.models.user import User

router = APIRouter(prefix="/accounts", tags=["Accounts"], dependencies=[Depends(get_current_user)])
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
def list_accounts(request: Request, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    accounts = db.query(Account).filter(Account.user_id == current_user.id).order_by(Account.id.desc()).all()

    total_balance = sum(acc.balance for acc in accounts)
    return templates.TemplateResponse(
        request=request,
        name="accounts/list.html",
        context={"total_balance": total_balance, "accounts": accounts,"user": current_user},
    )

@router.post("/create")
def create_account(
    title: str = Form(...),
    bank_name: str = Form(None),
    account_number: str = Form(None),
    card_number: str = Form(None),
    sheba: str = Form(None),
    balance: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)

):
    acc = Account(
        user_id=current_user.id,
        title=title.strip(),
        bank_name=bank_name.strip() if bank_name else None,
        account_number=account_number.strip() if account_number else None,
        card_number=card_number.strip() if card_number else None,
        sheba=sheba.strip() if sheba else None,
        balance=balance
    )
    db.add(acc)
    db.commit()
    return responses.RedirectResponse(url="/accounts", status_code=status.HTTP_302_FOUND)

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
    account = db.query(Account).filter(Account.id == account_id, Account.user_id == current_user.id).first()
    if not account:
        raise HTTPException(status_code=404, detail="حساب یافت نشد")

    account.title = title
    account.bank_name = bank_name
    account.card_number = card_number
    account.sheba = sheba

    db.commit()
    return RedirectResponse(
        url="/accounts", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/{account_id}/delete")
def delete_account(account_id: int, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)
):
    acc = db.query(Account).filter(Account.id == account_id, Account.user_id == current_user.id).first()
    if acc:
        db.delete(acc)
        db.commit()
    return responses.RedirectResponse(url="/accounts", status_code=status.HTTP_302_FOUND)
