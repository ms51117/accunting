from datetime import datetime, date

from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.debt import Debt, DebtType, DebtStatus
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services.category_service import get_or_create_category
from app.utils.jalali import parse_jalali_str, format_rial, to_jalali_str
from app.utils.parse_amount import parse_int_amount, parse_optional_int

router = APIRouter(prefix="/debts", tags=["Debts"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


def parse_date_input(date_str: str) -> date:
    if not date_str or not date_str.strip():
        return date.today()
    date_str = date_str.strip()
    try:
        if "/" in date_str:
            return parse_jalali_str(date_str)
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return date.today()


@router.get("")
@router.get("/")
def debts_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    type: str = None,
    status: str = "ACTIVE"
):
    query = db.query(Debt).filter(Debt.user_id == current_user.id)

    if not status:
        status = "ACTIVE"

    if type and type != "ALL":
        query = query.filter(Debt.type == type)
    if status != "ALL":
        query = query.filter(Debt.status == status)

    debts = query.order_by(Debt.id.desc()).all()
    persons = db.query(Person).filter(Person.user_id == current_user.id).order_by(Person.full_name).all()
    accounts = db.query(Account).filter(Account.user_id == current_user.id).order_by(Account.title).all()
    return templates.TemplateResponse(
        request=request,
        name="debts/list.html",
        context={
            "debts": debts,
            "persons": persons,
            "accounts": accounts,
            "selected_type": type,
            "selected_status": status,
            "user": current_user
        }
    )


@router.post("/create")
def create_debt(
    type: str = Form(...),
    person_id: str = Form(...),
    amount: str = Form(...),
    account_id: str = Form(None),
    date: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_amount = parse_int_amount(amount)
    if clean_amount <= 0:
        return RedirectResponse(url="/debts?error=مبلغ_نامعتبر_است", status_code=status.HTTP_303_SEE_OTHER)

    clean_person_id = parse_optional_int(person_id)
    if not clean_person_id:
        return RedirectResponse(url="/debts?error=شخص_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

    person = db.query(Person).filter(Person.id == clean_person_id, Person.user_id == current_user.id).first()
    if not person:
        return RedirectResponse(url="/debts?error=شخص_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

    trans_date = parse_date_input(date)

    # ایجاد رکورد بدهی/طلب
    new_debt = Debt(
        user_id=current_user.id,
        type=type,
        person_id=person.id,
        amount=clean_amount,
        paid_amount=0,
        due_date=trans_date,
        description=description.strip() if description else None,
        status=DebtStatus.ACTIVE.value
    )
    db.add(new_debt)
    db.flush()

    # اگر حسابی انتخاب شده باشد، تراکنش اولیه متناظر ثبت می‌شود
    clean_account_id = parse_optional_int(account_id)
    if clean_account_id:
        account = (
            db.query(Account)
            .filter(Account.id == clean_account_id, Account.user_id == current_user.id)
            .with_for_update()
            .first()
        )
        if not account:
            db.rollback()
            return RedirectResponse(url="/debts?error=حساب_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

        if type == DebtType.RECEIVABLE.value:
            # طلبکاری (ما پول قرض دادیم): پول از حساب کسر می‌شود
            if account.balance < clean_amount:
                db.rollback()
                return RedirectResponse(url="/debts?error=موجودی_حساب_کافی_نیست", status_code=status.HTTP_303_SEE_OTHER)
            account.balance -= clean_amount
            tx_type = TransactionType.EXPENSE.value
            tx_cat = "پرداخت قرض/وام"
        else:
            # بدهکاری (ما پول قرض گرفتیم): پول به حساب واریز می‌شود
            account.balance += clean_amount
            tx_type = TransactionType.INCOME.value
            tx_cat = "دریافت قرض/وام"

        tx_desc = f"{tx_cat} به/از {person.full_name}"
        if description:
            tx_desc += f" - {description.strip()}"

        debt_cat = get_or_create_category(db, user_id=current_user.id, title=tx_cat, trans_type=tx_type)

        transaction = Transaction(
            user_id=current_user.id,
            account_id=account.id,
            type=tx_type,
            category=tx_cat,
            category_id=debt_cat.id,
            amount=clean_amount,
            trans_date=trans_date,
            description=tx_desc,
            debt_id=new_debt.id,
            person_id=person.id
        )
        db.add(transaction)

    db.commit()
    return RedirectResponse(url="/debts?msg=ثبت_با_موفقیت_انجام_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{debt_id}/pay")
def pay_debt(
    debt_id: int,
    pay_amount: str = Form(...),
    account_id: str = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_pay_amount = parse_int_amount(pay_amount)
    if clean_pay_amount <= 0:
        return RedirectResponse(url="/debts?error=مبلغ_پرداختی_نامعتبر_است", status_code=status.HTTP_303_SEE_OTHER)

    debt = (
        db.query(Debt)
        .filter(Debt.id == debt_id, Debt.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not debt:
        return RedirectResponse(url="/debts?error=رکورد_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

    remaining_balance = debt.amount - debt.paid_amount
    if remaining_balance <= 0 or debt.status == DebtStatus.SETTLED.value:
        return RedirectResponse(url="/debts?error=این_مورد_قبلاً_تسویه_شده_است", status_code=status.HTTP_303_SEE_OTHER)

    if clean_pay_amount > remaining_balance:
        return RedirectResponse(url="/debts?error=مبلغ_پرداختی_بیشتر_از_مانده_است", status_code=status.HTTP_303_SEE_OTHER)

    clean_account_id = parse_optional_int(account_id)
    if not clean_account_id:
        return RedirectResponse(url="/debts?error=حساب_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

    account = (
        db.query(Account)
        .filter(Account.id == clean_account_id, Account.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not account:
        return RedirectResponse(url="/debts?error=حساب_یافت_نشد", status_code=status.HTTP_303_SEE_OTHER)

    debt.paid_amount += clean_pay_amount
    if debt.paid_amount >= debt.amount:
        debt.status = DebtStatus.SETTLED.value

    # ثبت تراکنش تسویه
    if debt.type == DebtType.RECEIVABLE.value:
        # وصول طلب: پول وارد حساب می‌شود
        account.balance += clean_pay_amount
        tx_type = TransactionType.INCOME.value
        tx_cat = "تسویه طلب"
    else:
        # پرداخت بدهی: پول از حساب کم می‌شود
        if account.balance < clean_pay_amount:
            db.rollback()
            return RedirectResponse(url="/debts?error=موجودی_حساب_کافی_نیست", status_code=status.HTTP_303_SEE_OTHER)
        account.balance -= clean_pay_amount
        tx_type = TransactionType.EXPENSE.value
        tx_cat = "تسویه بدهی"

    person_name = debt.person.full_name if debt.person else "شخص"
    tx_desc = f"{tx_cat} ({person_name})"
    if description:
        tx_desc += f" - {description.strip()}"

    pay_cat = get_or_create_category(db, user_id=current_user.id, title=tx_cat, trans_type=tx_type)

    transaction = Transaction(
        user_id=current_user.id,
        account_id=account.id,
        type=tx_type,
        category=tx_cat,
        category_id=pay_cat.id,
        amount=clean_pay_amount,
        trans_date=date.today(),
        description=tx_desc,
        debt_id=debt.id,
        person_id=debt.person_id
    )
    db.add(transaction)
    db.commit()

    return RedirectResponse(url="/debts?msg=تسویه_با_موفقیت_ثبت_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{debt_id}/update")
def update_debt(
    debt_id: int,
    person_id: str = Form(...),
    amount: str = Form(...),
    type: str = Form(...),
    account_id: str = Form(None),
    paid_amount: str = Form(None),
    due_date: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    debt = (
        db.query(Debt)
        .filter(Debt.id == debt_id, Debt.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not debt:
        return RedirectResponse(url="/debts?error=not_found", status_code=303)

    clean_person_id = parse_optional_int(person_id)
    if clean_person_id:
        debt.person_id = clean_person_id

    new_total_amount = parse_int_amount(amount)
    if new_total_amount <= 0:
        return RedirectResponse(url="/debts?error=مبلغ_کل_نامعتبر_است", status_code=303)

    if paid_amount is not None and paid_amount.strip() != "":
        new_paid_amount = parse_int_amount(paid_amount)
    else:
        new_paid_amount = debt.paid_amount

    if new_paid_amount < 0:
        return RedirectResponse(url="/debts?error=مبلغ_پرداختی_نامعتبر_است", status_code=303)

    if new_paid_amount > new_total_amount:
        return RedirectResponse(url="/debts?error=مبلغ_پرداختی_بیشتر_از_کل_است", status_code=303)

    # همگام‌سازی مبلغ کل و تراکنش اولیه فقط در صورتی که تراکنش اولیه از نوع پرداخت/دریافت اولیه باشد
    total_diff = new_total_amount - debt.amount
    if total_diff != 0:
        initial_tx = (
            db.query(Transaction)
            .filter(
                Transaction.debt_id == debt.id,
                Transaction.user_id == current_user.id,
                Transaction.category.in_(["پرداخت قرض/وام", "دریافت قرض/وام"])
            )
            .order_by(Transaction.id.asc())
            .first()
        )
        if initial_tx:
            init_account = (
                db.query(Account)
                .filter(
                    Account.id == initial_tx.account_id,
                    Account.user_id == current_user.id,
                )
                .with_for_update()
                .first()
            )
            if init_account:
                debt_type_val = debt.type.value if hasattr(debt.type, "value") else debt.type
                if debt_type_val == "RECEIVABLE":
                    init_account.balance -= total_diff
                else:
                    init_account.balance += total_diff

            initial_tx.amount = new_total_amount

    # به‌روزرسانی اطلاعات اصلی بدهی
    debt.person_id = person_id
    debt.type = type
    debt.amount = new_total_amount
    debt.paid_amount = new_paid_amount
    debt.description = description.strip() if description else None

    if due_date:
        debt.due_date = parse_date_input(due_date)
    else:
        debt.due_date = None

    if debt.paid_amount >= debt.amount:
        debt.status = DebtStatus.SETTLED.value
    else:
        debt.status = DebtStatus.ACTIVE.value

    db.commit()
    return RedirectResponse(url="/debts?msg=تغییرات_با_موفقیت_ذخیره_شد", status_code=303)


@router.post("/{debt_id}/delete")
def delete_debt(
    debt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    debt = (
        db.query(Debt)
        .filter(Debt.id == debt_id, Debt.user_id == current_user.id)
        .first()
    )
    if not debt:
        return RedirectResponse(url="/debts?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    transactions = (
        db.query(Transaction)
        .filter(Transaction.debt_id == debt.id, Transaction.user_id == current_user.id)
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
            if tx.type == TransactionType.INCOME.value:
                account.balance -= tx.amount
            elif tx.type == TransactionType.EXPENSE.value:
                account.balance += tx.amount
        db.delete(tx)

    db.delete(debt)
    db.commit()
    return RedirectResponse(url="/debts?msg=مورد_با_موفقیت_حذف_شد", status_code=status.HTTP_303_SEE_OTHER)