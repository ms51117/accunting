import csv
import io
from fastapi import APIRouter, Request, Depends, Query, status
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.models.category import Category
from app.services.report_service import (
    get_advanced_report,
    get_monthly_trends,
    get_category_breakdown,
    PERSIAN_MONTH_NAMES
)
from app.utils.jalali import format_rial, to_jalali_str
from app.utils.parse_amount import parse_optional_int

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


@router.get("")
@router.get("/")
def reports_dashboard(
    request: Request,
    period: str = "current_month",
    custom_from: str = None,
    custom_to: str = None,
    account_id: str = None,
    category_id: str = None,
    trans_type: str = "ALL",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_account_id = parse_optional_int(account_id)
    clean_category_id = parse_optional_int(category_id)

    report_data = get_advanced_report(
        db=db,
        user_id=current_user.id,
        period=period or "current_month",
        custom_from=custom_from,
        custom_to=custom_to,
        account_id=clean_account_id,
        category_id=clean_category_id,
        trans_type=trans_type or "ALL",
    )

    # روند ۶ ماهه برای نمودار روند ماه به ماه
    monthly_trends = get_monthly_trends(db=db, user_id=current_user.id, months_count=6)

    accounts = db.query(Account).filter(Account.user_id == current_user.id).order_by(Account.title).all()
    categories = db.query(Category).filter(Category.user_id == current_user.id).order_by(Category.title).all()

    return templates.TemplateResponse(
        request=request,
        name="reports/index.html",
        context={
            "user": current_user,
            "report": report_data,
            "monthly_trends": monthly_trends,
            "accounts": accounts,
            "categories": categories,
            "selected_period": period or "current_month",
            "selected_account_id": clean_account_id,
            "selected_category_id": clean_category_id,
            "selected_trans_type": trans_type or "ALL",
            "custom_from": custom_from or "",
            "custom_to": custom_to or "",
        }
    )


@router.get("/export-csv")
def export_report_csv(
    period: str = "current_month",
    custom_from: str = None,
    custom_to: str = None,
    account_id: str = None,
    category_id: str = None,
    trans_type: str = "ALL",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_account_id = parse_optional_int(account_id)
    clean_category_id = parse_optional_int(category_id)

    report_data = get_advanced_report(
        db=db,
        user_id=current_user.id,
        period=period or "current_month",
        custom_from=custom_from,
        custom_to=custom_to,
        account_id=clean_account_id,
        category_id=clean_category_id,
        trans_type=trans_type or "ALL",
    )

    transactions = report_data["transactions"]

    # ساخت فایل CSV همراه با BOM یوتی‌اف-۸ برای سازگاری کامل با اکسل فارسی
    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM
    writer = csv.writer(output)

    # سربرگ گزارش
    writer.writerow(["شناسه", "نوع تراکنش", "سرفصل / دسته‌بندی", "حساب مبدأ", "حساب مقصد", "مبلغ (ریال)", "تاریخ شمسی", "توضیحات"])

    type_translations = {
        "INCOME": "درآمد",
        "EXPENSE": "هزینه",
        "TRANSFER": "انتقال"
    }

    for tx in transactions:
        tx_type_fa = type_translations.get(str(tx.type), str(tx.type))
        cat_title = tx.category_rel.title if tx.category_rel else (tx.category or "-")
        acc_title = tx.account.title if tx.account else "-"
        dest_acc_title = tx.destination_account.title if tx.destination_account else "-"
        trans_date_fa = to_jalali_str(tx.trans_date)

        writer.writerow([
            tx.id,
            tx_type_fa,
            cat_title,
            acc_title,
            dest_acc_title,
            tx.amount,
            trans_date_fa,
            tx.description or ""
        ])

    # ردیف جمع کل
    writer.writerow([])
    writer.writerow(["جمع کل درآمد", report_data["total_income"], "ریال"])
    writer.writerow(["جمع کل هزینه", report_data["total_expense"], "ریال"])
    writer.writerow(["تراز خالص", report_data["net_savings"], "ریال"])

    output.seek(0)
    filename = f"financial_report_{period}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
