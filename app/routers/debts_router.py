from datetime import datetime, date
from typing import Optional

import jdatetime
from fastapi import APIRouter, Request, Depends, Form, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.person import Person
from app.models.debt import Debt, DebtType, DebtStatus
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.utils.jalali import parse_jalali_str
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from app.utils.parse_amount import parse_int_amount



router = APIRouter(prefix="/debts", tags=["Debts"], dependencies=[Depends(get_current_user)])
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
    try:
        if isinstance(value, str):
            # اگر ورودی رشته است، اول به آبجکت تاریخ میلادی تبدیل شود
            from datetime import datetime
            value = datetime.strptime(value, "%Y-%m-%d").date()
        # تبدیل میلادی به شمسی
        j_date = jdatetime.date.fromgregorian(date=value)
        return j_date.strftime("%Y/%m/%d")
    except Exception:
        return str(value)

# ۳. ثبت فیلترها روی محیط Jinja2
templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = format_jalali

def parse_date_input(date_str: str):
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    try:
        if "/" in date_str:
            parts = [int(p) for p in date_str.split("/")]
            if len(parts) == 3:
                return jdatetime.date(parts[0], parts[1], parts[2]).togregorian()
        elif "-" in date_str:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None
    return None

@router.get("/")
def debts_list(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        type: str = None,
        status: str = None
):
    query = db.query(Debt).filter(Debt.user_id == current_user.id)

    if type:
        query = query.filter(Debt.type == type)
    if status:
        query = query.filter(Debt.status == status)

    debts = query.order_by(Debt.id.desc()).all()
    persons = db.query(Person).filter(Person.user_id == current_user.id).order_by(Person.full_name).all()
    accounts = db.query(Account).filter(Account.user_id == current_user.id).order_by(Account.title).all()
    return templates.TemplateResponse(
        request=request,
        name="debts/list.html",
        context= {
            "debts": debts,
            "persons": persons,
            "accounts": accounts,
            "selected_type": type,
            "selected_status": status,
            "user": current_user
        })

@router.post("/create")
def create_debt(
    type: str = Form(...),
    person_id: int = Form(...),
    amount: int = Form(...),
    account_id: int = Form(None),  # حساب مبدا/مقصد
    date: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)

):
    if amount <= 0:
        return RedirectResponse(url="/debts?error=invalid_amount", status_code=status.HTTP_303_SEE_OTHER)

    person = db.query(Person).filter(Person.id == person_id, Person.user_id == current_user.id).first()
    if not person:
        return RedirectResponse(url="/debts?error=person_not_found", status_code=status.HTTP_303_SEE_OTHER)

    trans_date = parse_date_input(date) or datetime.now().date()

    # ایجاد رکورد بدهی/طلب
    new_debt = Debt(
        user_id=current_user.id,
        type=type,
        person_id=person_id,
        amount=amount,
        paid_amount=0,
        due_date=trans_date,
        description=description,
        status=DebtStatus.ACTIVE.value
    )
    db.add(new_debt)
    db.flush()  # دریافت شناسه new_debt.id

    # اگر حسابی انتخاب شده باشد، تراکنش متناظر را ثبت می‌کنیم
    if account_id:
        account = db.query(Account).filter(Account.id == account_id, Account.user_id == current_user.id).with_for_update().first()
        if not account:
            db.rollback()
            return RedirectResponse(url="/debts?error=account_not_found", status_code=status.HTTP_303_SEE_OTHER)

        if type == DebtType.RECEIVABLE.value:
            # طلبکاری (ما پول قرض دادیم): پول از حساب کسر می‌شود
            if account.balance < amount:
                db.rollback()
                return RedirectResponse(url="/debts?error=insufficient_funds", status_code=status.HTTP_303_SEE_OTHER)
            account.balance -= amount
            tx_type = TransactionType.EXPENSE.value
            tx_cat = "پرداخت قرض/وام"
        else:
            # بدهکاری (ما پول قرض گرفتیم): پول به حساب واریز می‌شود
            account.balance += amount
            tx_type = TransactionType.INCOME.value
            tx_cat = "دریافت قرض/وام"

        tx_desc = f"{tx_cat} به/از {person.full_name}"
        if description:
            tx_desc += f" - {description}"

        transaction = Transaction(
            user_id=current_user.id,
            account_id=account.id,
            type=tx_type,
            category=tx_cat,
            amount=amount,
            trans_date=trans_date,
            description=tx_desc,
            debt_id=new_debt.id
        )
        db.add(transaction)

    db.commit()
    return RedirectResponse(url="/debts?success=debt_created", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{debt_id}/pay")
def pay_debt(
    debt_id: int,
    pay_amount: str = Form(...),
    account_id: int = Form(...),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)

):
    pay_amount = parse_int_amount(pay_amount)
    if pay_amount <= 0:
        return RedirectResponse(url="/debts?error=invalid_pay_amount", status_code=status.HTTP_303_SEE_OTHER)

    debt = db.query(Debt).filter(Debt.id == debt_id, Debt.user_id == current_user.id).with_for_update().first()
    if not debt:
        return RedirectResponse(url="/debts?error=debt_not_found", status_code=status.HTTP_303_SEE_OTHER)

    remaining_balance = debt.amount - debt.paid_amount
    if remaining_balance <= 0 or debt.status == DebtStatus.SETTLED.value:
        return RedirectResponse(url="/debts?error=already_settled", status_code=status.HTTP_303_SEE_OTHER)

    if pay_amount > remaining_balance:
        return RedirectResponse(url="/debts?error=amount_exceeds_remaining", status_code=status.HTTP_303_SEE_OTHER)

    account = db.query(Account).filter(Account.id == account_id, Account.user_id == current_user.id).with_for_update().first()
    if not account:
        return RedirectResponse(url="/debts?error=account_not_found", status_code=status.HTTP_303_SEE_OTHER)

    debt.paid_amount += pay_amount
    if debt.paid_amount >= debt.amount:
        debt.status = DebtStatus.SETTLED.value

    # ثبت تراکنش تسویه
    if debt.type == DebtType.RECEIVABLE.value:
        # وصول طلب: پول وارد حساب می‌شود
        account.balance += pay_amount
        tx_type = TransactionType.INCOME.value
        tx_cat = "تسویه طلب"
    else:
        # پرداخت بدهی: پول از حساب کم می‌شود
        if account.balance < pay_amount:
            db.rollback()
            return RedirectResponse(url="/debts?error=insufficient_funds", status_code=status.HTTP_303_SEE_OTHER)
        account.balance -= pay_amount
        tx_type = TransactionType.EXPENSE.value
        tx_cat = "تسویه بدهی"

    person_name = debt.person.full_name if debt.person else "شخص"
    tx_desc = f"{tx_cat} ({person_name})"
    if description:
        tx_desc += f" - {description}"

    transaction = Transaction(
        user_id=current_user.id,
        account_id=account.id,
        type=tx_type,
        category=tx_cat,
        amount=pay_amount,
        trans_date=datetime.now().date(),
        description=tx_desc,
        debt_id=debt.id
    )
    db.add(transaction)
    db.commit()

    return RedirectResponse(url="/debts?success=paid", status_code=status.HTTP_303_SEE_OTHER)


# متد ویرایش بدهی (همگام با action فرم در list.html: /debts/{id}/update)
@router.post("/{debt_id}/update")
def update_debt(
    debt_id: int,
    person_id: int = Form(...),
    amount: str = Form(...),
    type: str = Form(...),
    account_id: int = Form(None),
    paid_amount: str = Form(None),  # 👈 امکان ویرایش مبلغ پرداخت/تسویه شده
    due_date: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ۱. واکشی بدهی با قفل سطری
    debt = (
        db.query(Debt)
        .filter(Debt.id == debt_id, Debt.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not debt:
        raise HTTPException(status_code=404, detail="رکورد بدهی/طلب یافت نشد")

    # ۲. تبدیل و اعتبارسنجی مبالغ
    new_total_amount = parse_int_amount(amount)
    if new_total_amount <= 0:
        return RedirectResponse(
            url="/debts?error=مبلغ_کل_نامعتبر_است", status_code=303
        )

    # اگر فیلد پرداختی پر نشده بود، همان مقدار قبلی بدهی حفظ می‌شود
    if paid_amount is not None and paid_amount.strip() != "":
        new_paid_amount = parse_int_amount(paid_amount)
    else:
        new_paid_amount = debt.paid_amount

    if new_paid_amount < 0:
        return RedirectResponse(
            url="/debts?error=مبلغ_پرداختی_نامعتبر_است", status_code=303
        )

    if new_paid_amount > new_total_amount:
        return RedirectResponse(
            url="/debts?error=مبلغ_پرداختی_بیشتر_از_کل_است", status_code=303
        )

    # ==================== بخش اضافه شده: همگام‌سازی مبلغ کل و تراکنش اولیه ====================
    total_diff = new_total_amount - debt.amount
    if total_diff != 0:
        initial_tx = (
            db.query(Transaction)
            .filter(
                Transaction.debt_id == debt.id,
                Transaction.user_id == current_user.id,
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
    # =========================================================================================

    # ۳. محاسبه اختلاف مبلغ پرداختی و اعمال روی حساب و تراکنش‌ها
    diff = new_paid_amount - debt.paid_amount

    if diff != 0:
        # انتخاب حساب بانکی (حساب ارسالی فرم یا حساب متصل به آخرین تراکنش بدهی)
        target_account_id = account_id
        if not target_account_id:
            last_tx = (
                db.query(Transaction)
                .filter(
                    Transaction.debt_id == debt.id,
                    Transaction.user_id == current_user.id,
                )
                .order_by(Transaction.id.desc())
                .first()
            )
            if last_tx:
                target_account_id = last_tx.account_id

        if target_account_id:
            account = (
                db.query(Account)
                .filter(
                    Account.id == target_account_id,
                    Account.user_id == current_user.id,
                )
                .with_for_update()
                .first()
            )

            if account:
                debt_type_val = debt.type.value if hasattr(debt.type, "value") else debt.type
                # اگر نوع طلب (RECEIVABLE) باشد:
                # افزایش پرداختی = واریز پول به حساب (INCOME) / کاهش پرداختی = کسر از حساب
                if debt_type_val == "RECEIVABLE":
                    account.balance += diff
                    tx_type = (
                        TransactionType.INCOME
                        if diff > 0
                        else TransactionType.EXPENSE
                    )
                    tx_desc = f"اصلاحیه تسویه طلب ({debt.id}) - تغییر مبلغ: {abs(diff):,} ریال"
                else:
                    # اگر نوع بدهی ما (PAYABLE) باشد:
                    # افزایش پرداختی = برداشت از حساب (EXPENSE) / کاهش پرداختی = بازگشت پول به حساب
                    if diff > 0 and account.balance < diff:
                        return RedirectResponse(
                            url="/debts?error=موجودی_حساب_کافی_نیست",
                            status_code=303,
                        )
                    account.balance -= diff
                    tx_type = (
                        TransactionType.EXPENSE
                        if diff > 0
                        else TransactionType.INCOME
                    )
                    tx_desc = f"اصلاحیه پرداخت بدهی ({debt.id}) - تغییر مبلغ: {abs(diff):,} ریال"

                # ثبت تراکنش تعدیلی برای حفظ تاریخچه مالی
                adjustment_tx = Transaction(
                    user_id=current_user.id,
                    account_id=account.id,
                    type=tx_type,
                    category="اصلاحیه بدهی/طلب",
                    amount=abs(diff),
                    trans_date=datetime.now(),
                    description=tx_desc,
                    debt_id=debt.id,
                )
                db.add(adjustment_tx)

    # ۴. به‌روزرسانی اطلاعات اصلی بدهی
    debt.person_id = person_id
    debt.type = type
    debt.amount = new_total_amount
    debt.paid_amount = new_paid_amount
    debt.description = description

    if due_date:
        debt.due_date = parse_date_input(due_date)
    else:
        debt.due_date = None

    # ۵. به‌روزرسانی خودکار وضعیت (ACTIVE یا SETTLED)
    if debt.paid_amount >= debt.amount:
        debt.status = DebtStatus.SETTLED
    else:
        debt.status = DebtStatus.ACTIVE

    db.commit()
    return RedirectResponse(url="/debts?success=updated", status_code=303)



@router.post("/{debt_id}/delete")
def delete_debt(debt_id: int, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)
):
    debt = db.query(Debt).filter(Debt.id == debt_id, Debt.user_id == current_user.id).first()
    if not debt:
        return RedirectResponse(url="/debts?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # 1. واکشی کلیه تراکنش‌های متصل به این بدهی
    transactions = db.query(Transaction).filter(Transaction.debt_id == debt.id,Transaction.user_id == current_user.id).all()

    # 2. برگرداندن (Revert) اثر تراکنش‌ها از مانده حساب‌ها
    for tx in transactions:
        account = db.query(Account).filter(Account.id == tx.account_id, Account.user_id == current_user.id).with_for_update().first()
        if account:
            if tx.type == TransactionType.INCOME.value:
                account.balance -= tx.amount
            elif tx.type == TransactionType.EXPENSE.value:
                account.balance += tx.amount
        db.delete(tx)

    # 3. حذف رکورد بدهی
    db.delete(debt)
    db.commit()

    return RedirectResponse(url="/debts?success=deleted", status_code=status.HTTP_303_SEE_OTHER)