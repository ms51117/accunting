from datetime import datetime, date

from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.cheque import Cheque, ChequeStatus, ChequeType
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services.cheque_service import clear_cheque, bounce_cheque
from app.utils.jalali import parse_jalali_str, format_rial, to_jalali_str
from app.utils.parse_amount import parse_int_amount, parse_optional_int

router = APIRouter(prefix="/cheques", tags=["Cheques"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


@router.get("")
@router.get("/")
def list_cheques(
    request: Request,
    type_filter: str = None,
    status_filter: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Cheque).filter(Cheque.user_id == current_user.id)

    # پیش‌فرض فیلتر: چک‌های در انتظار وصول (PENDING)
    if not status_filter:
        status_filter = "PENDING"

    if type_filter and type_filter != "ALL":
        query = query.filter(Cheque.type == type_filter)
    if status_filter != "ALL":
        query = query.filter(Cheque.status == status_filter)

    cheques = query.order_by(Cheque.due_date.asc(), Cheque.id.desc()).all()
    accounts = db.query(Account).filter(Account.user_id == current_user.id).order_by(Account.title).all()
    persons = db.query(Person).filter(Person.user_id == current_user.id).order_by(Person.full_name).all()

    return templates.TemplateResponse(
        request=request,
        name="cheques/list.html",
        context={
            "cheques": cheques,
            "accounts": accounts,
            "persons": persons,
            "type_filter": type_filter or "",
            "status_filter": status_filter or "PENDING",
            "user": current_user,
            "today": date.today()
        }
    )


@router.post("/create")
def create_cheque(
    cheque_type: str = Form(...),
    person_id: str = Form(...),
    amount: str = Form(...),
    due_date: str = Form(...),
    account_id: str = Form(None),
    issue_date: str = Form(None),
    serial_number: str = Form(None),
    sayad_number: str = Form(None),
    bank_name: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_amount = parse_int_amount(amount)
    if clean_amount <= 0:
        return RedirectResponse(url="/cheques?error=مبلغ_چک_نامعتبر_است", status_code=status.HTTP_303_SEE_OTHER)

    clean_person_id = parse_optional_int(person_id)
    if not clean_person_id:
        return RedirectResponse(url="/cheques?error=طرف_حساب_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

    person = db.query(Person).filter(Person.id == clean_person_id, Person.user_id == current_user.id).first()
    if not person:
        return RedirectResponse(url="/cheques?error=طرف_حساب_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

    valid_account_id = None
    clean_account_id = parse_optional_int(account_id)
    if clean_account_id:
        acc = db.query(Account).filter(Account.id == clean_account_id, Account.user_id == current_user.id).first()
        if acc:
            valid_account_id = acc.id

    try:
        g_due_date = parse_jalali_str(due_date.strip())
    except Exception:
        g_due_date = date.today()

    g_issue_date = date.today()
    if issue_date and issue_date.strip():
        try:
            g_issue_date = parse_jalali_str(issue_date.strip())
        except Exception:
            pass

    new_cheque = Cheque(
        type=cheque_type,
        user_id=current_user.id,
        person_id=person.id,
        account_id=valid_account_id,
        amount=clean_amount,
        due_date=g_due_date,
        issue_date=g_issue_date,
        cheque_number=serial_number.strip() if serial_number else None,
        sayad_number=sayad_number.strip() if sayad_number else None,
        bank_name=bank_name.strip() if bank_name else None,
        description=description.strip() if description else None,
        status=ChequeStatus.PENDING.value
    )
    db.add(new_cheque)
    db.commit()
    return RedirectResponse(url="/cheques?msg=چک_با_موفقیت_ثبت_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cheque_id}/clear")
def process_clear_cheque(
    cheque_id: int,
    account_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_account_id = parse_optional_int(account_id)
    if not clean_account_id:
        return RedirectResponse(url="/cheques?error=حساب_نامعتبر_است", status_code=status.HTTP_303_SEE_OTHER)
    try:
        clear_cheque(db=db, cheque_id=cheque_id, target_account_id=clean_account_id, user_id=current_user.id)
        return RedirectResponse(url="/cheques?msg=چک_با_موفقیت_وصول_شد", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        return RedirectResponse(url=f"/cheques?error={str(e)}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cheque_id}/bounce")
def process_bounce_cheque(
    cheque_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        bounce_cheque(db=db, cheque_id=cheque_id, user_id=current_user.id)
        return RedirectResponse(url="/cheques?msg=وضعیت_چک_به_برگشت‌خورده_تغییر_یافت", status_code=status.HTTP_303_SEE_OTHER)
    except ValueError as e:
        return RedirectResponse(url=f"/cheques?error={str(e)}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cheque_id}/edit")
def edit_cheque(
    cheque_id: int,
    cheque_type: str = Form(...),
    person_id: str = Form(...),
    amount: str = Form(...),
    due_date: str = Form(...),
    status: str = Form(...),
    sayad_number: str = Form(None),
    bank_name: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cheque = (
        db.query(Cheque)
        .filter(Cheque.id == cheque_id, Cheque.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not cheque:
        return RedirectResponse(url="/cheques?error=چک_یافت_نشد", status_code=303)

    clean_person_id = parse_optional_int(person_id)
    if clean_person_id:
        cheque.person_id = clean_person_id

    new_amount = parse_int_amount(amount)
    if new_amount <= 0:
        return RedirectResponse(url="/cheques?error=مبلغ_نامعتبر_است", status_code=303)

    parsed_due_date = cheque.due_date
    if due_date and due_date.strip():
        try:
            parsed_due_date = parse_jalali_str(due_date.strip())
        except Exception:
            pass

    old_status = str(cheque.status.value if hasattr(cheque.status, 'value') else cheque.status).upper()
    new_status = str(status).upper()
    old_amount = cheque.amount

    # یافتن تراکنش‌های ثبت‌شده برای این چک
    transactions = (
        db.query(Transaction)
        .filter(Transaction.cheque_id == cheque.id, Transaction.user_id == current_user.id)
        .all()
    )

    # همگام‌سازی وضعیت و اثرات مالی
    if old_status == "CLEARED" and new_status != "CLEARED":
        # اگر چک پاس شده بود و به حالت دیگری برمی‌گردد، اثر مالی آن خنثی می‌شود
        for tx in transactions:
            if tx.account_id:
                account = (
                    db.query(Account)
                    .filter(Account.id == tx.account_id, Account.user_id == current_user.id)
                    .with_for_update()
                    .first()
                )
                if account:
                    if tx.type == "INCOME":
                        account.balance -= tx.amount
                    else:
                        account.balance += tx.amount
            db.delete(tx)
        cheque.cleared_date = None

    elif old_status != "CLEARED" and new_status == "CLEARED":
        # اگر کاربر در ادیت وضعیت را وصول‌شده کرد، اثر مالی را با سرویس وصول اعمال می‌کنیم
        if cheque.account_id:
            try:
                cheque.amount = new_amount
                db.flush()
                clear_cheque(db=db, cheque_id=cheque.id, target_account_id=cheque.account_id, user_id=current_user.id)
            except Exception:
                pass
        else:
            return RedirectResponse(
                url="/cheques?error=برای_وصول_چک_لطفاً_از_دکمه_سبزرنگ_وصول_چک_استفاده_کنید_تا_حساب_مشخص_شود",
                status_code=303
            )

    elif old_status == "CLEARED" and new_status == "CLEARED" and new_amount != old_amount:
        # تغییر مبلغ چک پاس‌شده
        diff = new_amount - old_amount
        for tx in transactions:
            if tx.account_id:
                account = (
                    db.query(Account)
                    .filter(Account.id == tx.account_id, Account.user_id == current_user.id)
                    .with_for_update()
                    .first()
                )
                if account:
                    if tx.type == "INCOME":
                        account.balance += diff
                    else:
                        account.balance -= diff
            tx.amount = new_amount

    # به‌روزرسانی فیلدهای چک
    cheque.type = cheque_type
    cheque.person_id = person_id
    cheque.amount = new_amount
    cheque.due_date = parsed_due_date
    cheque.status = new_status
    cheque.sayad_number = sayad_number.strip() if sayad_number else None
    cheque.bank_name = bank_name.strip() if bank_name else None
    cheque.description = description.strip() if description else None

    db.commit()
    return RedirectResponse(url="/cheques?msg=مشخصات_چک_به‌روزرسانی_شد", status_code=303)


@router.post("/{cheque_id}/delete")
def delete_cheque(
    cheque_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cheque = (
        db.query(Cheque)
        .filter(Cheque.id == cheque_id, Cheque.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not cheque:
        return RedirectResponse(url="/cheques?error=چک_یافت_نشد", status_code=303)

    # واکشی کلیه تراکنش‌های متصل به این چک و بازگرداندن اثر مالی
    transactions = (
        db.query(Transaction)
        .filter(Transaction.cheque_id == cheque.id, Transaction.user_id == current_user.id)
        .all()
    )
    for tx in transactions:
        account = (
            db.query(Account)
            .filter(Account.id == tx.account_id, Account.user_id == current_user.id)
            .with_for_update()
            .first()
        )
        if account:
            if tx.type == "INCOME":
                account.balance -= tx.amount
            elif tx.type == "EXPENSE":
                account.balance += tx.amount
        db.delete(tx)

    db.delete(cheque)
    db.commit()
    return RedirectResponse(url="/cheques?msg=چک_با_موفقیت_حذف_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/send-reminders")
async def trigger_telegram_reminders(
    days_ahead: int = 3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.services.telegram_service import check_and_notify_upcoming_cheques
    result = await check_and_notify_upcoming_cheques(
        db=db,
        user_id=current_user.id,
        days_ahead=days_ahead,
        force_send=True
    )
    return result
