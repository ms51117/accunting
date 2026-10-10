import jdatetime
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.cheque import Cheque
from app.models.debt import Debt
from app.models.transaction import Transaction
from app.models.user import User
from sqlalchemy.orm import joinedload
from app.models.debt import Debt, DebtStatus, DebtType
from app.models.person import Person


router = APIRouter(tags=["Dashboard"], dependencies=[Depends(get_current_user)])
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



@router.get("/")
def dashboard_view(request: Request, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    # ۱. موجودی کل حساب‌ها
    accounts = db.query(Account).filter(Account.user_id == current_user.id).all()
    total_balance = sum(acc.balance or 0 for acc in accounts)

    # ۲. وضعیت چک‌های در جریان وصول (PENDING)
    user_pending_cheques = db.query(Cheque).filter(
        Cheque.user_id == current_user.id,
        Cheque.status == "PENDING"
    ).all()

    pending_receivable_cheques = sum(c.amount or 0 for c in user_pending_cheques if c.type == "RECEIVABLE")

    pending_payable_cheques = sum(c.amount or 0 for c in user_pending_cheques if c.type == "PAYABLE")

    # ۳. وضعیت بدهی‌ها و مطالبات فعال (مانده طلب / بدهی)
    active_debts = db.query(Debt).filter(Debt.status == "ACTIVE",Debt.user_id == current_user.id,).all()
    total_receivable_debt = sum((d.amount - d.paid_amount) for d in active_debts if d.type == "RECEIVABLE")
    total_payable_debt = sum((d.amount - d.paid_amount) for d in active_debts if d.type == "PAYABLE")

    # ۴. ۱۰ تراکنش اخیر
    recent_transactions = (db.query(Transaction)
                           .filter(Transaction.user_id == current_user.id)
                           .order_by(Transaction.trans_date.desc(), Transaction.id.desc()).limit(10).all())

    # ۵. چک‌های با سررسید نزدیک
    upcoming_cheques = db.query(Cheque).filter(Cheque.status == "PENDING",Cheque.user_id == current_user.id).order_by(Cheque.due_date.asc()).limit(
        10).all()


    # استخراج بدهی‌ها و طلب‌های فعال کاربر جاری به تفکیک اشخاص
    active_debts = (
        db.query(Debt)
        .options(joinedload(Debt.person))
        .filter(Debt.user_id == current_user.id, Debt.status == DebtStatus.ACTIVE)
        .all()
    )

    person_balances = {}
    for debt in active_debts:
        pid = debt.person_id
        if pid not in person_balances:
            person_balances[pid] = {
                "person": debt.person,
                "receivable": 0,  # طلب ما از طرف
                "payable": 0,     # بدهی ما به طرف
            }
        remaining = debt.amount - debt.paid_amount
        if debt.type == DebtType.RECEIVABLE:
            person_balances[pid]["receivable"] += remaining
        elif debt.type == DebtType.PAYABLE:
            person_balances[pid]["payable"] += remaining

    # محاسبه وضعیت خالص برای هر شخص (فقط اشخاصی که مانده صفر ندارند)
    debt_summary_list = []
    for data in person_balances.values():
        net = data["receivable"] - data["payable"]
        if net != 0:
            debt_summary_list.append({
                "person": data["person"],
                "receivable": data["receivable"],
                "payable": data["payable"],
                "net": net,  # اگر مثبت: ما طلبکاریم | اگر منفی: ما بدهکاریم
            })

    # مرتب‌سازی بر اساس بیشترین مانده
    debt_summary_list.sort(key=lambda x: abs(x["net"]), reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"total_balance": total_balance,
        "user": current_user,
        "pending_receivable_cheques": pending_receivable_cheques,
        "pending_payable_cheques": pending_payable_cheques,
        "total_receivable_debt": total_receivable_debt,
        "total_payable_debt": total_payable_debt,
        "recent_transactions": recent_transactions,
        "upcoming_cheques": upcoming_cheques,
        "debt_summary_list": debt_summary_list,  # <-- اضافه شد
    })
