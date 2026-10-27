from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
import jdatetime
from starlette import status

from app.database import get_db
from app.models.account import Account
from app.models.person import Person
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.auth import get_current_user
from app.models.user import User
from app.utils.jalali import parse_jalali_str, format_rial, to_jalali_str
from app.utils.parse_amount import parse_int_amount, parse_optional_int

router = APIRouter(prefix="/transactions", tags=["Transactions"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


def parse_date_input(trans_date_str: str) -> date:
    if not trans_date_str:
        return date.today()
    try:
        trans_date_str = trans_date_str.strip()
        if "/" in trans_date_str:
            parts = trans_date_str.split("/")
            if len(parts) == 3 and len(parts[0]) == 4:
                return parse_jalali_str(trans_date_str)
        return datetime.strptime(trans_date_str, "%Y-%m-%d").date()
    except Exception:
        return date.today()


def revert_transaction_balance(db: Session, tx: Transaction, user_id: int):
    """اثر مالی یک تراکنش را روی حساب‌های مبدأ و مقصد خنثی می‌کند."""
    src_account = db.query(Account).filter(Account.id == tx.account_id, Account.user_id == user_id).first()
    dest_id = getattr(tx, "destination_account_id", None)
    dest_account = db.query(Account).filter(Account.id == dest_id, Account.user_id == user_id).first() if dest_id else None

    if tx.type == "INCOME" and src_account:
        src_account.balance -= tx.amount
    elif tx.type == "EXPENSE" and src_account:
        src_account.balance += tx.amount
    elif tx.type == "TRANSFER":
        # فقط در صورتی که هر دو حساب مبدا و مقصد معتبر باشند برگشت زده می‌شود تا باگ تولید موجودی ایجاد نشود
        if src_account and dest_account:
            src_account.balance += tx.amount
            dest_account.balance -= tx.amount
        elif src_account and not dest_account:
            # اگر مقصد نامعتبر بوده، فقط از مبدأ کسر نشده بود پس به مبدأ اضافه نشود
            pass


def apply_transaction_balance(db: Session, trans_type: str, amount: int, src_account: Account,
                              dest_account: Account = None):
    """اثر مالی تراکنش جدید را اعمال می‌کند."""
    if trans_type == "INCOME" and src_account:
        src_account.balance += amount
    elif trans_type == "EXPENSE" and src_account:
        src_account.balance -= amount
    elif trans_type == "TRANSFER" and src_account and dest_account:
        src_account.balance -= amount
        dest_account.balance += amount


PERSIAN_MONTHS = [
    (1, "فروردین"),
    (2, "اردیبهشت"),
    (3, "خرداد"),
    (4, "تیر"),
    (5, "مرداد"),
    (6, "شهریور"),
    (7, "مهر"),
    (8, "آبان"),
    (9, "آذر"),
    (10, "دی"),
    (11, "بهمن"),
    (12, "اسفند")
]


@router.get("")
@router.get("/")
def list_transactions(
    request: Request,
    type_filter: str = None,
    account_filter: str = None,
    category_filter: str = None,
    month_filter: str = None,
    year_filter: str = None,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_account_id = parse_optional_int(account_filter)
    clean_category_id = parse_optional_int(category_filter)
    clean_month = parse_optional_int(month_filter)
    clean_year = parse_optional_int(year_filter)

    today_j = jdatetime.date.today()
    current_j_year = today_j.year
    current_j_month = today_j.month
    active_year = clean_year if clean_year else current_j_year

    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)

    # ۱. فیلتر نوع تراکنش
    if type_filter and type_filter != "ALL":
        query = query.filter(Transaction.type == type_filter)

    # ۲. فیلتر حساب یا بانک
    if clean_account_id:
        query = query.filter(
            (Transaction.account_id == clean_account_id) |
            (Transaction.destination_account_id == clean_account_id)
        )

    # ۳. فیلتر دسته‌بندی
    if clean_category_id:
        query = query.filter(Transaction.category_id == clean_category_id)

    # ۴. فیلتر ماه شمسی
    if clean_month and 1 <= clean_month <= 12:
        try:
            start_j = jdatetime.date(active_year, clean_month, 1)
            start_g = start_j.togregorian()
            from datetime import timedelta
            if clean_month == 12:
                next_month_j = jdatetime.date(active_year + 1, 1, 1)
            else:
                next_month_j = jdatetime.date(active_year, clean_month + 1, 1)
            end_g = next_month_j.togregorian() - timedelta(days=1)
            query = query.filter(Transaction.trans_date >= start_g, Transaction.trans_date <= end_g)
        except Exception:
            pass

    # ۵. جستجوی متنی در توضیحات یا دسته‌بندی
    if search and search.strip():
        s = search.strip()
        query = query.filter(Transaction.category.contains(s) | Transaction.description.contains(s))

    transactions = query.order_by(Transaction.trans_date.desc(), Transaction.id.desc()).all()

    # محاسبه سرجمع تراکنش‌های فیلترشده
    total_income = sum(t.amount for t in transactions if t.type == "INCOME")
    total_expense = sum(t.amount for t in transactions if t.type == "EXPENSE")
    net_flow = total_income - total_expense

    accounts = db.query(Account).filter(Account.user_id == current_user.id).order_by(Account.title).all()
    persons = db.query(Person).filter(Person.user_id == current_user.id).order_by(Person.full_name).all()
    categories = db.query(Category).filter(Category.user_id == current_user.id).order_by(Category.title).all()
    available_years = [current_j_year - 2, current_j_year - 1, current_j_year, current_j_year + 1]

    return templates.TemplateResponse(
        request=request,
        name="transactions/list.html",
        context={
            "transactions": transactions,
            "accounts": accounts,
            "persons": persons,
            "categories": categories,
            "today_jalali": today_j.strftime("%Y/%m/%d"),
            "current_j_year": current_j_year,
            "current_j_month": current_j_month,
            "persian_months": PERSIAN_MONTHS,
            "available_years": available_years,
            "type_filter": type_filter or "ALL",
            "account_filter": clean_account_id,
            "category_filter": clean_category_id,
            "month_filter": clean_month,
            "year_filter": active_year,
            "search": search or "",
            "total_income": total_income,
            "total_expense": total_expense,
            "net_flow": net_flow,
            "user": current_user
        }
    )


@router.post("/create")
def create_transaction(
    trans_type: str = Form(...),
    account_id: str = Form(...),
    amount: str = Form(...),
    trans_date: str = Form(...),
    category_id: str = Form(None),
    category: str = Form(None),
    destination_account_id: str = Form(None),
    person_id: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_account_id = parse_optional_int(account_id)
    clean_destination_account_id = parse_optional_int(destination_account_id)
    clean_category_id = parse_optional_int(category_id)
    clean_person_id = parse_optional_int(person_id)

    clean_amount = parse_int_amount(amount)
    if clean_amount <= 0:
        return RedirectResponse(
            url="/transactions?error=مبلغ_تراکنش_نامعتبر_است",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not clean_account_id:
        return RedirectResponse(
            url="/transactions?error=حساب_مبدأ_الزامی_است",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # بررسی حساب مبدأ
    src_account = (
        db.query(Account)
        .filter(Account.id == clean_account_id, Account.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not src_account:
        return RedirectResponse(
            url="/transactions?error=حساب_مبدأ_یافت_نشد",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    dest_account = None
    if trans_type == "TRANSFER":
        if not clean_destination_account_id:
            return RedirectResponse(
                url="/transactions?error=حساب_مقصد_برای_انتقال_الزامی_است",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if clean_destination_account_id == clean_account_id:
            return RedirectResponse(
                url="/transactions?error=حساب_مبدأ_و_مقصد_نمی‌تواند_یکسان_باشد",
                status_code=status.HTTP_303_SEE_OTHER,
            )

        dest_account = (
            db.query(Account)
            .filter(Account.id == clean_destination_account_id, Account.user_id == current_user.id)
            .with_for_update()
            .first()
        )
        if not dest_account:
            return RedirectResponse(
                url="/transactions?error=حساب_مقصد_یافت_نشد",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    valid_person_id = None
    if clean_person_id:
        p = db.query(Person).filter(Person.id == clean_person_id, Person.user_id == current_user.id).first()
        if p:
            valid_person_id = p.id

    real_date = parse_date_input(trans_date)

    # اعتبارسنجی و نگاشت دسته‌بندی
    final_cat_id = None
    final_cat_title = ""

    if clean_category_id:
        cat_obj = db.query(Category).filter(Category.id == clean_category_id, Category.user_id == current_user.id).first()
        if cat_obj:
            final_cat_id = cat_obj.id
            final_cat_title = cat_obj.title

    if not final_cat_title and category and category.strip():
        clean_cat_title = category.strip()
        existing_cat = db.query(Category).filter(Category.user_id == current_user.id, Category.title == clean_cat_title).first()
        if existing_cat:
            final_cat_id = existing_cat.id
            final_cat_title = existing_cat.title
        else:
            # ایجاد خودکار دسته‌بندی جدید
            new_cat = Category(
                user_id=current_user.id,
                title=clean_cat_title,
                type=trans_type if trans_type in ("INCOME", "EXPENSE") else "BOTH",
                color="#3b82f6",
                icon="tag"
            )
            db.add(new_cat)
            db.flush()
            final_cat_id = new_cat.id
            final_cat_title = new_cat.title

    if not final_cat_title:
        default_cat = db.query(Category).filter(Category.user_id == current_user.id).first()
        if default_cat:
            final_cat_id = default_cat.id
            final_cat_title = default_cat.title
        else:
            final_cat_title = "سایر"

    # اعمال اثر مالی روی مانده‌ها
    apply_transaction_balance(db, trans_type, clean_amount, src_account, dest_account)

    # ایجاد رکورد تراکنش
    tx = Transaction(
        user_id=current_user.id,
        account_id=src_account.id,
        destination_account_id=dest_account.id if dest_account else None,
        person_id=valid_person_id,
        type=trans_type,
        category=final_cat_title,
        category_id=final_cat_id,
        amount=clean_amount,
        trans_date=real_date,
        description=description.strip() if description else None
    )

    db.add(tx)
    db.commit()

    return RedirectResponse(url="/transactions?msg=تراکنش_با_موفقیت_ثبت_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{trans_id}/update")
def update_transaction(
    trans_id: int,
    trans_type: str = Form(...),
    account_id: str = Form(...),
    amount: str = Form(...),
    trans_date: str = Form(...),
    category_id: str = Form(None),
    category: str = Form(None),
    destination_account_id: str = Form(None),
    person_id: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_account_id = parse_optional_int(account_id)
    clean_destination_account_id = parse_optional_int(destination_account_id)
    clean_category_id = parse_optional_int(category_id)
    clean_person_id = parse_optional_int(person_id)

    clean_amount = parse_int_amount(amount)
    if clean_amount <= 0:
        return RedirectResponse(
            url="/transactions?error=مبلغ_تراکنش_نامعتبر_است",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not clean_account_id:
        return RedirectResponse(
            url="/transactions?error=حساب_مبدأ_الزامی_است",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    tx = (
        db.query(Transaction)
        .filter(Transaction.id == trans_id, Transaction.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not tx:
        return RedirectResponse(url="/transactions?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # گارد امنیتی: جلوگیری از ویرایش مستقیم تراکنش‌های متصل به چک و بدهی
    if getattr(tx, "cheque_id", None) or getattr(tx, "debt_id", None):
        return RedirectResponse(
            url="/transactions?error=تراکنش‌های_متصل_به_چک_یا_تسویه_باید_از_بخش_مربوطه_مدیریت_شوند",
            status_code=status.HTTP_303_SEE_OTHER
        )

    src_account = (
        db.query(Account)
        .filter(Account.id == clean_account_id, Account.user_id == current_user.id)
        .with_for_update()
        .first()
    )
    if not src_account:
        return RedirectResponse(
            url="/transactions?error=حساب_مبدأ_یافت_نشد",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    dest_account = None
    if trans_type == "TRANSFER":
        if not clean_destination_account_id or clean_destination_account_id == clean_account_id:
            return RedirectResponse(
                url="/transactions?error=حساب_مقصد_نامعتبر_یا_تکراری_است",
                status_code=status.HTTP_303_SEE_OTHER
            )
        dest_account = (
            db.query(Account)
            .filter(Account.id == clean_destination_account_id, Account.user_id == current_user.id)
            .with_for_update()
            .first()
        )
        if not dest_account:
            return RedirectResponse(
                url="/transactions?error=حساب_مقصد_یافت_نشد",
                status_code=status.HTTP_303_SEE_OTHER
            )

    # اعتبارسنجی و نگاشت دسته‌بندی
    final_cat_id = tx.category_id
    final_cat_title = tx.category

    if clean_category_id:
        cat_obj = db.query(Category).filter(Category.id == clean_category_id, Category.user_id == current_user.id).first()
        if cat_obj:
            final_cat_id = cat_obj.id
            final_cat_title = cat_obj.title
    elif category and category.strip():
        clean_cat_title = category.strip()
        existing_cat = db.query(Category).filter(Category.user_id == current_user.id, Category.title == clean_cat_title).first()
        if existing_cat:
            final_cat_id = existing_cat.id
            final_cat_title = existing_cat.title
        else:
            new_cat = Category(
                user_id=current_user.id,
                title=clean_cat_title,
                type=trans_type if trans_type in ("INCOME", "EXPENSE") else "BOTH",
                color="#3b82f6",
                icon="tag"
            )
            db.add(new_cat)
            db.flush()
            final_cat_id = new_cat.id
            final_cat_title = new_cat.title

    # 1. خنثی کردن اثر تراکنش قبلی
    revert_transaction_balance(db, tx, current_user.id)

    # 2. اعمال اثر مالی جدید
    apply_transaction_balance(db, trans_type, clean_amount, src_account, dest_account)

    # 3. به‌روزرسانی مقادیر رکورد
    tx.type = trans_type
    tx.account_id = src_account.id
    tx.destination_account_id = dest_account.id if dest_account else None
    tx.amount = clean_amount
    tx.category = final_cat_title
    tx.category_id = final_cat_id
    tx.trans_date = parse_date_input(trans_date)
    tx.description = description.strip() if description else None
    tx.person_id = person_id if person_id else None

    db.commit()
    return RedirectResponse(url="/transactions?msg=تراکنش_به‌روزرسانی_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{trans_id}/delete")
def delete_transaction(trans_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == trans_id, Transaction.user_id == current_user.id)
        .first()
    )
    if not tx:
        return RedirectResponse(url="/transactions?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # جلوگیری از حذف تراکنش‌های وابسته به چک یا تسویه
    if getattr(tx, "cheque_id", None) or getattr(tx, "debt_id", None):
        return RedirectResponse(
            url="/transactions?error=این_تراکنش_به_چک_یا_طلب_متصل_است_و_مستقیماً_قابل_حذف_نیست",
            status_code=status.HTTP_303_SEE_OTHER
        )

    revert_transaction_balance(db, tx, current_user.id)
    db.delete(tx)
    db.commit()
    return RedirectResponse(url="/transactions?msg=تراکنش_با_موفقیت_حذف_شد", status_code=status.HTTP_303_SEE_OTHER)
