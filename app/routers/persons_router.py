from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.person import Person
from app.models.debt import Debt
from app.models.cheque import Cheque
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.jalali import format_rial, to_jalali_str

router = APIRouter(prefix="/persons", tags=["Persons"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


@router.get("")
def list_persons(
    request: Request,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Person).filter(Person.user_id == current_user.id)
    if search and search.strip():
        term = search.strip()
        query = query.filter(Person.full_name.contains(term) | Person.phone.contains(term))

    persons = query.order_by(Person.id.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="persons/list.html",
        context={
            "persons": persons,
            "search": search or "",
            "user": current_user
        }
    )


@router.post("/create")
def create_person(
    full_name: str = Form(...),
    phone: str = Form(None),
    bank_name: str = Form(None),
    card_number: str = Form(None),
    sheba: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_name = full_name.strip()
    if not clean_name:
        return RedirectResponse(url="/persons?error=نام_شخص_الزامی_است", status_code=status.HTTP_303_SEE_OTHER)

    person = Person(
        user_id=current_user.id,
        full_name=clean_name,
        phone=phone.strip() if phone else None,
        bank_name=bank_name.strip() if bank_name else None,
        card_number=card_number.strip() if card_number else None,
        sheba=sheba.strip() if sheba else None,
        notes=notes.strip() if notes else None
    )
    db.add(person)
    db.commit()
    return RedirectResponse(url="/persons?msg=شخص_با_موفقیت_ثبت_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{person_id}/edit")
def edit_person(
    person_id: int,
    full_name: str = Form(...),
    phone: str = Form(None),
    bank_name: str = Form(None),
    card_number: str = Form(None),
    sheba: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    person = db.query(Person).filter(Person.id == person_id, Person.user_id == current_user.id).first()
    if not person:
        return RedirectResponse(url="/persons?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    clean_name = full_name.strip()
    if not clean_name:
        return RedirectResponse(url="/persons?error=نام_شخص_الزامی_است", status_code=status.HTTP_303_SEE_OTHER)

    person.full_name = clean_name
    person.phone = phone.strip() if phone else None
    person.bank_name = bank_name.strip() if bank_name else None
    person.card_number = card_number.strip() if card_number else None
    person.sheba = sheba.strip() if sheba else None
    person.notes = notes.strip() if notes else None

    db.commit()
    return RedirectResponse(url="/persons?msg=اطلاعات_شخص_به‌روزرسانی_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{person_id}/delete")
def delete_person(
    person_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    person = db.query(Person).filter(Person.id == person_id, Person.user_id == current_user.id).first()
    if not person:
        return RedirectResponse(url="/persons?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # بررسی وابستگی‌ها (چک، بدهی، تراکنش)
    has_debts = db.query(Debt).filter(Debt.person_id == person_id).first()
    has_cheques = db.query(Cheque).filter(Cheque.person_id == person_id).first()
    has_transactions = db.query(Transaction).filter(Transaction.person_id == person_id).first()

    if has_debts or has_cheques or has_transactions:
        return RedirectResponse(url="/persons?error=has_dependencies", status_code=status.HTTP_303_SEE_OTHER)

    db.delete(person)
    db.commit()
    return RedirectResponse(url="/persons?msg=شخص_با_موفقیت_حذف_شد", status_code=status.HTTP_303_SEE_OTHER)
