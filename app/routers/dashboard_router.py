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
        "upcoming_cheques": upcoming_cheques

    })
