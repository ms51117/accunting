from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.transaction import Transaction
from app.utils.jalali import parse_jalali_str

router = APIRouter(prefix="/transactions", tags=["Transactions"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

@router.get("")
def list_transactions(request: Request, db: Session = Depends(get_db)):
    transactions = db.query(Transaction).order_by(Transaction.trans_date.desc(), Transaction.id.desc()).all()
    accounts = db.query(Account).all()
    persons = db.query(Person).all()
    return templates.TemplateResponse(
        request=request,
        name="transactions/list.html",
        context={
        "transactions": transactions,
        "accounts": accounts,
        "persons": persons
    })

@router.post("/create")
def create_transaction(
    trans_type: str = Form(...),  # INCOME, EXPENSE, TRANSFER
    account_id: int = Form(...),
    amount: int = Form(...),
    category: str = Form(...),
    trans_date: str = Form(...),  # فرمت شمسی: 1403/05/20 یا میلادی
    destination_account_id: int = Form(None),
    person_id: int = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    # تبدیل تاریخ شمسی به میلادی
    try:
        if "/" in trans_date and len(trans_date.split("/")[0]) == 4:
            g_date = parse_jalali_str(trans_date.strip())
        else:
            g_date = datetime.strptime(trans_date.strip(), "%Y-%m-%d").date()
    except Exception:
        g_date = date.today()

    source_acc = db.query(Account).filter(Account.id == account_id).first()
    if not source_acc:
        return responses.RedirectResponse(url="/transactions", status_code=status.HTTP_302_FOUND)

    if trans_type == "INCOME":
        source_acc.balance += amount
    elif trans_type == "EXPENSE":
        source_acc.balance -= amount
    elif trans_type == "TRANSFER":
        dest_acc = db.query(Account).filter(Account.id == destination_account_id).first()
        if dest_acc and dest_acc.id != source_acc.id:
            source_acc.balance -= amount
            dest_acc.balance += amount

    new_trans = Transaction(
        account_id=source_acc.id,
        destination_account_id=destination_account_id if trans_type == "TRANSFER" else None,
        person_id=person_id if person_id else None,
        type=trans_type,
        category=category.strip(),
        amount=amount,
        trans_date=g_date,
        description=description.strip() if description else None
    )
    db.add(new_trans)
    db.commit()

    return responses.RedirectResponse(url="/transactions", status_code=status.HTTP_302_FOUND)

@router.post("/{trans_id}/delete")
def delete_transaction(trans_id: int, db: Session = Depends(get_db)):
    # حذف تراکنش و بازگرداندن اثر آن به موجودی
    tx = db.query(Transaction).filter(Transaction.id == trans_id).first()
    if tx:
        acc = db.query(Account).filter(Account.id == tx.account_id).first()
        if acc:
            if tx.type == "INCOME":
                acc.balance -= tx.amount
            elif tx.type == "EXPENSE":
                acc.balance += tx.amount
            elif tx.type == "TRANSFER" and tx.destination_account_id:
                dest_acc = db.query(Account).filter(Account.id == tx.destination_account_id).first()
                acc.balance += tx.amount
                if dest_acc:
                    dest_acc.balance -= tx.amount
        db.delete(tx)
        db.commit()
    return responses.RedirectResponse(url="/transactions", status_code=status.HTTP_302_FOUND)
