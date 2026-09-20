from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from app.database import get_db
from app.auth import get_current_user
from app.models.person import Person
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models.user import User

router = APIRouter(prefix="/persons", tags=["Persons"], dependencies=[Depends(get_current_user)])
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
def list_persons(request: Request, search: str = None, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    query = db.query(Person).filter(Person.user_id == current_user.id)
    if search:
        query = query.filter(Person.full_name.contains(search.strip()) | Person.phone.contains(search.strip()))
    persons = query.order_by(Person.id.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="persons/list.html",
        context={"persons": persons,
        "search": search or "",
        "user": current_user
    })

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
    person = Person(
        user_id=current_user.id,
        full_name=full_name.strip(),
        phone=phone.strip() if phone else None,
        bank_name=bank_name.strip() if bank_name else None,
        card_number=card_number.strip() if card_number else None,
        sheba=sheba.strip() if sheba else None,
        notes=notes.strip() if notes else None
    )
    db.add(person)
    db.commit()
    return responses.RedirectResponse(url="/persons", status_code=status.HTTP_302_FOUND)

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
    person = db.query(Person).filter(Person.id == person_id,Person.user_id== current_user.id).first()
    if not person:
        raise HTTPException(status_code=404, detail="شخص مورد نظر یافت نشد")

    person.full_name = full_name.strip()
    person.phone = phone.strip() if phone else None
    person.bank_name = bank_name.strip() if bank_name else None
    person.card_number = card_number.strip() if card_number else None
    person.sheba = sheba.strip() if sheba else None
    person.notes = notes.strip() if notes else None

    db.commit()
    return RedirectResponse(url="/persons", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{person_id}/delete")
def delete_person(person_id: int, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    person = db.query(Person).filter(Person.id == person_id,Person.user_id == current_user.id).first()
    if person:
        db.delete(person)
        db.commit()
    return responses.RedirectResponse(url="/persons", status_code=status.HTTP_302_FOUND)
