from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.cheque import Cheque
from app.services.cheque_service import clear_cheque, bounce_cheque
from app.utils.jalali import jalali_to_gregorian

router = APIRouter(prefix="/cheques", tags=["Cheques"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")


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

    return templates.TemplateResponse("cheques/list.html", {
        "request": request,
        "cheques": cheques,
        "accounts": accounts,
        "persons": persons,
        "type_filter": type_filter or "",
        "status_filter": status_filter or ""
    })


@router.post("/create")
def create_cheque(
        cheque_type: str = Form(...),  # RECEIVABLE (دریافتی), PAYABLE (پرداختی)
        person_id: int = Form(...),
        account_id: int = Form(None),
        amount: int = Form(...),
        due_date: str = Form(...),
        issue_date: str = Form(None),
        serial_number: str = Form(None),
        sayad_id: str = Form(None),
        bank_name: str = Form(None),
        description: str = Form(None),
        db: Session = Depends(get_db)
):
    try:
        g_due_date = jalali_to_gregorian(due_date.strip()) if "/" in due_date else datetime.strptime(due_date.strip(),
                                                                                                     "%Y-%m-%d").date()
    except Exception:
        g_due_date = date.today()

    g_issue_date = None
    if issue_date:
        try:
            g_issue_date = jalali_to_gregorian(issue_date.strip()) if "/" in issue_date else datetime.strptime(
                issue_date.strip(), "%Y-%m-%d").date()
        except Exception:
            g_issue_date = date.today()

    new_cheque = Cheque(
        type=cheque_type,
        person_id=person_id,
        account_id=account_id if account_id else None,
        amount=amount,
        due_date=g_due_date,
        issue_date=g_issue_date,
        serial_number=serial_number.strip() if serial_number else None,
        sayad_id=sayad_id.strip() if sayad_id else None,
        bank_name=bank_name.strip() if bank_name else None,
        description=description.strip() if description else None,
        status="PENDING"
    )
    db.add(new_cheque)
    db.commit()
    return responses.RedirectResponse(url="/cheques", status_code=status.HTTP_302_FOUND)


@router.post("/{cheque_id}/clear")
def process_clear_cheque(cheque_id: int, account_id: int = Form(...), db: Session = Depends(get_db)):
    # استفاده از سرویس استاندارد برای اثرگذاری روی موجودی
    clear_cheque(db=db, cheque_id=cheque_id, target_account_id=account_id)
    return responses.RedirectResponse(url="/cheques", status_code=status.HTTP_302_FOUND)


@router.post("/{cheque_id}/bounce")
def process_bounce_cheque(cheque_id: int, db: Session = Depends(get_db)):
    bounce_cheque(db=db, cheque_id=cheque_id)
    return responses.RedirectResponse(url="/cheques", status_code=status.HTTP_302_FOUND)
