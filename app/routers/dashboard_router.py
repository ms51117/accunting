from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.auth import get_current_user
from app.models.account import Account
from app.models.cheque import Cheque
from app.models.debt import Debt, DebtStatus, DebtType
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.jalali import format_rial, to_jalali_str

router = APIRouter(tags=["Dashboard"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


from app.services.report_service import get_monthly_trends, get_category_breakdown

@router.get("/")
def dashboard_view(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ۱. موجودی کل حساب‌ها
    accounts = db.query(Account).filter(Account.user_id == current_user.id).all()
    total_balance = sum(acc.balance or 0 for acc in accounts)

    # ۲. وضعیت چک‌های در جریان وصول (PENDING)
    user_pending_cheques = (
        db.query(Cheque)
        .filter(Cheque.user_id == current_user.id, Cheque.status == "PENDING")
        .all()
    )
    pending_receivable_cheques = sum(c.amount or 0 for c in user_pending_cheques if c.type == "RECEIVABLE")
    pending_payable_cheques = sum(c.amount or 0 for c in user_pending_cheques if c.type == "PAYABLE")

    # ۳. وضعیت بدهی‌ها و مطالبات فعال به صورت یکپارچه
    active_debts = (
        db.query(Debt)
        .options(joinedload(Debt.person))
        .filter(Debt.user_id == current_user.id, Debt.status == "ACTIVE")
        .all()
    )
    total_receivable_debt = sum((d.amount - (d.paid_amount or 0)) for d in active_debts if d.type == "RECEIVABLE")
    total_payable_debt = sum((d.amount - (d.paid_amount or 0)) for d in active_debts if d.type == "PAYABLE")

    # ۴. محاسبات نمودارهای کاربردی داشبورد
    monthly_trends = get_monthly_trends(db=db, user_id=current_user.id, months_count=6)
    category_expenses = get_category_breakdown(db=db, user_id=current_user.id, trans_type="EXPENSE")
    top_categories = category_expenses["categories"][:5]
    total_expense_period = sum(monthly_trends["expenses"])
    total_income_period = sum(monthly_trends["incomes"])
    net_period = total_income_period - total_expense_period
    top_cat = top_categories[0] if top_categories else None

    # ۵. چک‌های با سررسید نزدیک
    upcoming_cheques = (
        db.query(Cheque)
        .filter(Cheque.user_id == current_user.id, Cheque.status == "PENDING")
        .order_by(Cheque.due_date.asc())
        .limit(10)
        .all()
    )

    # ۶. وضعیت مانده اشخاص (بدهکاران / طلبکاران)
    person_balances = {}
    for debt in active_debts:
        pid = debt.person_id
        if pid not in person_balances:
            person_balances[pid] = {
                "person": debt.person,
                "receivable": 0,
                "payable": 0,
            }
        remaining = debt.amount - (debt.paid_amount or 0)
        if debt.type == "RECEIVABLE" or debt.type == DebtType.RECEIVABLE:
            person_balances[pid]["receivable"] += remaining
        elif debt.type == "PAYABLE" or debt.type == DebtType.PAYABLE:
            person_balances[pid]["payable"] += remaining

    debt_summary_list = []
    for data in person_balances.values():
        net = data["receivable"] - data["payable"]
        if net != 0:
            debt_summary_list.append({
                "person": data["person"],
                "receivable": data["receivable"],
                "payable": data["payable"],
                "net": net,
            })

    debt_summary_list.sort(key=lambda x: abs(x["net"]), reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "total_balance": total_balance,
            "user": current_user,
            "pending_receivable_cheques": pending_receivable_cheques,
            "pending_payable_cheques": pending_payable_cheques,
            "total_receivable_debt": total_receivable_debt,
            "total_payable_debt": total_payable_debt,
            "monthly_trends": monthly_trends,
            "category_expenses": category_expenses,
            "top_categories": top_categories,
            "total_expense_period": total_expense_period,
            "total_income_period": total_income_period,
            "net_period": net_period,
            "top_cat": top_cat,
            "upcoming_cheques": upcoming_cheques,
            "debt_summary_list": debt_summary_list,
        }
    )
