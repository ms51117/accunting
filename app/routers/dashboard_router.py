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
    return str(value)

# ۳. ثبت فیلترها روی محیط Jinja2
templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = format_jalali



@router.get("/")
def dashboard_view(request: Request, db: Session = Depends(get_db)):
    # ۱. موجودی کل حساب‌ها
    total_balance = db.query(func.coalesce(func.sum(Account.balance), 0)).scalar()

    # ۲. وضعیت چک‌های در جریان وصول (PENDING)
    pending_receivable_cheques = db.query(func.coalesce(func.sum(Cheque.amount), 0)) \
        .filter(Cheque.type == "RECEIVABLE", Cheque.status == "PENDING").scalar()

    pending_payable_cheques = db.query(func.coalesce(func.sum(Cheque.amount), 0)) \
        .filter(Cheque.type == "PAYABLE", Cheque.status == "PENDING").scalar()

    # ۳. وضعیت بدهی‌ها و مطالبات فعال (مانده طلب / بدهی)
    active_debts = db.query(Debt).filter(Debt.status == "ACTIVE").all()
    total_receivable_debt = sum((d.amount - d.paid_amount) for d in active_debts if d.type == "RECEIVABLE")
    total_payable_debt = sum((d.amount - d.paid_amount) for d in active_debts if d.type == "PAYABLE")

    # ۴. ۱۰ تراکنش اخیر
    recent_transactions = db.query(Transaction).order_by(Transaction.trans_date.desc(), Transaction.id.desc()).limit(
        10).all()

    # ۵. چک‌های با سررسید نزدیک
    upcoming_cheques = db.query(Cheque).filter(Cheque.status == "PENDING").order_by(Cheque.due_date.asc()).limit(
        5).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"total_balance": total_balance,
        "pending_receivable_cheques": pending_receivable_cheques,
        "pending_payable_cheques": pending_payable_cheques,
        "total_receivable_debt": total_receivable_debt,
        "total_payable_debt": total_payable_debt,
        "recent_transactions": recent_transactions,
        "upcoming_cheques": upcoming_cheques

    })
