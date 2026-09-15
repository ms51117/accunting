from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, Form, responses, status, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.cheque import Cheque
from app.services.cheque_service import clear_cheque, bounce_cheque
from app.utils.jalali import parse_jalali_str
from datetime import datetime, date

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
    return str(value)

# ۳. ثبت فیلترها روی محیط Jinja2
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
        context={"cheques": cheques,
        "accounts": accounts,
        "persons": persons,
        "type_filter": type_filter or "",
        "status_filter": status_filter or ""
    })


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
        status="PENDING"
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
    amount: float = Form(...),
    due_date: str = Form(...),          # ورودی به صورت رشته می‌آید
    status: str = Form(...),
    sayad_number: str = Form(None),
    bank_name: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    cheque = db.query(Cheque).filter(Cheque.id == cheque_id).first()
    if not cheque:
        raise HTTPException(status_status=404, detail="چک یافت نشد")

    # تبدیل رشته تاریخ به شیء date پایتون
    parsed_due_date = None
    if due_date:
        if isinstance(due_date, str):
            # اگر تاریخ میلادی استاندارد مثل '2026-09-11' باشد:
            try:
                parsed_due_date = datetime.strptime(due_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                # اگر فرمت دیگری دارد یا شمسی است، با منطق پروژه تبدیل کنید
                parsed_due_date = datetime.strptime(due_date.strip(), "%Y/%m/%d").date()
        elif isinstance(due_date, date):
            parsed_due_date = due_date

    # به‌روزرسانی فیلدها
    cheque.cheque_type = cheque_type
    cheque.person_id = person_id
    cheque.amount = amount
    cheque.due_date = parsed_due_date  # انتساب آبجکت date به جای رشته
    cheque.status = status
    cheque.sayad_number = sayad_number
    cheque.bank_name = bank_name
    cheque.description = description

    db.commit()
    return RedirectResponse(url="/cheques", status_code=303)


# --- حذف چک ---
@router.post("/{cheque_id}/delete")
def delete_cheque(
    cheque_id: int,
    db: Session = Depends(get_db)
):
    cheque = db.query(Cheque).filter(Cheque.id == cheque_id).first()
    if not cheque:
        raise HTTPException(status_code=404, detail="چک یافت نشد")

    db.delete(cheque)
    db.commit()
    return RedirectResponse(url="/cheques", status_code=status.HTTP_303_SEE_OTHER)