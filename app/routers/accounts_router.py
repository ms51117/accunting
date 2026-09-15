from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account

router = APIRouter(prefix="/accounts", tags=["Accounts"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

@router.get("")
def list_accounts(request: Request, db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.id.desc()).all()
    total_balance = sum(acc.balance for acc in accounts)
    return templates.TemplateResponse("accounts/list.html", {
        "request": request,
        "accounts": accounts,
        "total_balance": total_balance
    })

@router.post("/create")
def create_account(
    title: str = Form(...),
    bank_name: str = Form(None),
    account_number: str = Form(None),
    card_number: str = Form(None),
    sheba: str = Form(None),
    balance: int = Form(0),
    db: Session = Depends(get_db)
):
    acc = Account(
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

@router.post("/{account_id}/delete")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.id == account_id).first()
    if acc:
        db.delete(acc)
        db.commit()
    return responses.RedirectResponse(url="/accounts", status_code=status.HTTP_302_FOUND)
