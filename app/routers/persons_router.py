from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.person import Person

router = APIRouter(prefix="/persons", tags=["Persons"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

@router.get("")
def list_persons(request: Request, search: str = None, db: Session = Depends(get_db)):
    query = db.query(Person)
    if search:
        query = query.filter(Person.full_name.contains(search.strip()) | Person.phone.contains(search.strip()))
    persons = query.order_by(Person.id.desc()).all()
    return templates.TemplateResponse("persons/list.html", {
        "request": request,
        "persons": persons,
        "search": search or ""
    })

@router.post("/create")
def create_person(
    full_name: str = Form(...),
    phone: str = Form(None),
    bank_name: str = Form(None),
    card_number: str = Form(None),
    sheba: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    person = Person(
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

@router.post("/{person_id}/delete")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if person:
        db.delete(person)
        db.commit()
    return responses.RedirectResponse(url="/persons", status_code=status.HTTP_302_FOUND)
