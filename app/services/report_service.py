import jdatetime
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.transaction import Transaction, TransactionType
from app.models.category import Category
from app.models.account import Account
from app.utils.jalali import parse_jalali_str, to_jalali_str


PERSIAN_MONTH_NAMES = [
    "", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

PALETTE_COLORS = [
    "#3b82f6", "#10b981", "#f97316", "#a855f7", "#ec4899",
    "#06b6d4", "#eab308", "#f43f5e", "#6366f1", "#14b8a6",
    "#84cc16", "#8b5cf6", "#f59e0b", "#64748b"
]


def get_monthly_trends(db: Session, user_id: int, months_count: int = 6) -> Dict[str, Any]:
    """محاسبه روند درآمد و هزینه ماه‌های اخیر برای نمودار خطی/میله‌ای داشبورد و گزارش"""
    today_jd = jdatetime.date.today()
    
    # ساخت لیست ماه‌های مورد نیاز به ترتیب زمانی
    month_keys = []
    month_labels = []
    
    current_year = today_jd.year
    current_month = today_jd.month
    
    # برای N ماه گذشته
    for i in range(months_count - 1, -1, -1):
        m = current_month - i
        y = current_year
        while m <= 0:
            m += 12
            y -= 1
        key = f"{y}/{m:02d}"
        month_keys.append((y, m, key))
        month_labels.append(f"{PERSIAN_MONTH_NAMES[m]} {y % 100}")

    # دریافت تمام تراکنش‌های کاربر
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .all()
    )

    monthly_stats = {key: {"income": 0, "expense": 0, "transfer": 0} for _, _, key in month_keys}

    for t in txs:
        if not t.trans_date:
            continue
        try:
            jd = jdatetime.date.fromgregorian(date=t.trans_date)
            key = f"{jd.year}/{jd.month:02d}"
            if key in monthly_stats:
                if t.type == "INCOME" or t.type == TransactionType.INCOME:
                    monthly_stats[key]["income"] += t.amount
                elif t.type == "EXPENSE" or t.type == TransactionType.EXPENSE:
                    monthly_stats[key]["expense"] += t.amount
                elif t.type == "TRANSFER" or t.type == TransactionType.TRANSFER:
                    monthly_stats[key]["transfer"] += t.amount
        except Exception:
            continue

    incomes = [monthly_stats[key]["income"] for _, _, key in month_keys]
    expenses = [monthly_stats[key]["expense"] for _, _, key in month_keys]
    net_flows = [inc - exp for inc, exp in zip(incomes, expenses)]

    return {
        "labels": month_labels,
        "keys": [k for _, _, k in month_keys],
        "incomes": incomes,
        "expenses": expenses,
        "net_flows": net_flows,
    }


def get_category_breakdown(
    db: Session,
    user_id: int,
    trans_type: str = "EXPENSE",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None
) -> Dict[str, Any]:
    """محاسبه سهم هر دسته‌بندی از کل هزینه‌ها یا درآمدها همراه با رنگ و درصد"""
    query = (
        db.query(Transaction)
        .options(joinedload(Transaction.category_rel))
        .filter(Transaction.user_id == user_id, Transaction.type == trans_type)
    )

    if start_date:
        query = query.filter(Transaction.trans_date >= start_date)
    if end_date:
        query = query.filter(Transaction.trans_date <= end_date)
    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    txs = query.all()
    total_sum = sum(t.amount for t in txs)

    category_map: Dict[str, Dict[str, Any]] = {}

    for t in txs:
        cat_title = t.category_rel.title if t.category_rel else (t.category or "سایر / متفرقه")
        cat_color = (t.category_rel.color if (t.category_rel and t.category_rel.color) else None)
        cat_icon = (t.category_rel.icon if (t.category_rel and t.category_rel.icon) else "tag")

        if cat_title not in category_map:
            color_index = len(category_map) % len(PALETTE_COLORS)
            chosen_color = cat_color or PALETTE_COLORS[color_index]
            category_map[cat_title] = {
                "title": cat_title,
                "amount": 0,
                "count": 0,
                "color": chosen_color,
                "icon": cat_icon
            }

        category_map[cat_title]["amount"] += t.amount
        category_map[cat_title]["count"] += 1

    sorted_categories = sorted(category_map.values(), key=lambda x: x["amount"], reverse=True)

    labels = []
    amounts = []
    colors = []
    percentages = []

    for item in sorted_categories:
        labels.append(item["title"])
        amounts.append(item["amount"])
        colors.append(item["color"])
        pct = round((item["amount"] / total_sum * 100), 1) if total_sum > 0 else 0
        percentages.append(pct)
        item["percent"] = pct

    return {
        "categories": sorted_categories,
        "labels": labels,
        "amounts": amounts,
        "colors": colors,
        "percentages": percentages,
        "total_sum": total_sum,
        "transaction_count": len(txs),
    }


def get_advanced_report(
    db: Session,
    user_id: int,
    period: str = "current_month",
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    trans_type: Optional[str] = None,
) -> Dict[str, Any]:
    """تهیه گزارش مالی جامع با فیلترهای زمانی و مقداری همراه با KPIها"""
    today_jd = jdatetime.date.today()
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    period_title = "ماه جاری"

    if period == "current_month":
        # اول ماه جاری تا آخر ماه جاری
        start_jd = jdatetime.date(today_jd.year, today_jd.month, 1)
        # روز آخر ماه شمسی
        if today_jd.month <= 6:
            last_day = 31
        elif today_jd.month <= 11:
            last_day = 30
        else:
            last_day = 29 if not today_jd.isleap() else 30
        end_jd = jdatetime.date(today_jd.year, today_jd.month, last_day)
        start_date = start_jd.togregorian()
        end_date = end_jd.togregorian()
        period_title = f"{PERSIAN_MONTH_NAMES[today_jd.month]} {today_jd.year}"

    elif period == "last_3_months":
        start_jd = today_jd - timedelta(days=90)
        start_date = start_jd.togregorian()
        end_date = today_jd.togregorian()
        period_title = "۳ ماه اخیر"

    elif period == "last_6_months":
        start_jd = today_jd - timedelta(days=180)
        start_date = start_jd.togregorian()
        end_date = today_jd.togregorian()
        period_title = "۶ ماه اخیر"

    elif period == "current_year":
        start_jd = jdatetime.date(today_jd.year, 1, 1)
        end_jd = jdatetime.date(today_jd.year, 12, 29 if not today_jd.isleap() else 30)
        start_date = start_jd.togregorian()
        end_date = end_jd.togregorian()
        period_title = f"کل سال {today_jd.year}"

    elif period == "custom":
        if custom_from:
            try:
                start_date = parse_jalali_str(custom_from)
            except Exception:
                pass
        if custom_to:
            try:
                end_date = parse_jalali_str(custom_to)
            except Exception:
                pass
        period_title = f"از {custom_from or 'ابتدا'} تا {custom_to or 'اکنون'}"

    elif period == "all":
        start_date = None
        end_date = None
        period_title = "تمام دوران"

    # کوئری پایه
    query = (
        db.query(Transaction)
        .options(joinedload(Transaction.category_rel), joinedload(Transaction.account))
        .filter(Transaction.user_id == user_id)
    )

    if start_date:
        query = query.filter(Transaction.trans_date >= start_date)
    if end_date:
        query = query.filter(Transaction.trans_date <= end_date)
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if trans_type and trans_type != "ALL":
        query = query.filter(Transaction.type == trans_type)

    transactions = query.order_by(Transaction.trans_date.desc(), Transaction.id.desc()).all()

    # محاسبه شاخص‌های کلیدی (KPIs)
    total_income = sum(t.amount for t in transactions if t.type == "INCOME" or t.type == TransactionType.INCOME)
    total_expense = sum(t.amount for t in transactions if t.type == "EXPENSE" or t.type == TransactionType.EXPENSE)
    total_transfer = sum(t.amount for t in transactions if t.type == "TRANSFER" or t.type == TransactionType.TRANSFER)
    net_savings = total_income - total_expense

    # درصد نرخ پس‌انداز (نسبت سود به کل درآمد)
    savings_rate = round((net_savings / total_income * 100), 1) if total_income > 0 else 0

    # محاسبه میانگین هزینه روزانه
    days_count = 1
    if start_date and end_date:
        days_count = max(1, (end_date - start_date).days + 1)
    elif transactions:
        min_date = min(t.trans_date for t in transactions if t.trans_date)
        max_date = max(t.trans_date for t in transactions if t.trans_date)
        days_count = max(1, (max_date - min_date).days + 1)
    daily_avg_expense = round(total_expense / days_count)

    # تفکیک هزینه‌ها بر اساس دسته
    expense_breakdown = get_category_breakdown(
        db=db,
        user_id=user_id,
        trans_type="EXPENSE",
        start_date=start_date,
        end_date=end_date,
        account_id=account_id
    )

    # تفکیک درآمدها بر اساس دسته
    income_breakdown = get_category_breakdown(
        db=db,
        user_id=user_id,
        trans_type="INCOME",
        start_date=start_date,
        end_date=end_date,
        account_id=account_id
    )

    # گردش حساب‌ها در بازه
    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    account_stats = []
    for acc in accounts:
        acc_in = sum(t.amount for t in transactions if t.account_id == acc.id and t.type == "INCOME")
        acc_out = sum(t.amount for t in transactions if t.account_id == acc.id and t.type in ["EXPENSE", "TRANSFER"])
        # انتقالات به این حساب به عنوان مقصد
        acc_trans_in = sum(t.amount for t in transactions if t.destination_account_id == acc.id and t.type == "TRANSFER")
        total_inflow = acc_in + acc_trans_in
        if total_inflow > 0 or acc_out > 0 or acc.balance > 0:
            account_stats.append({
                "account": acc,
                "inflow": total_inflow,
                "outflow": acc_out,
                "balance": acc.balance or 0,
            })

    return {
        "period": period,
        "period_title": period_title,
        "start_date": start_date,
        "end_date": end_date,
        "start_date_jalali": to_jalali_str(start_date) if start_date else "",
        "end_date_jalali": to_jalali_str(end_date) if end_date else "",
        "transactions": transactions,
        "total_income": total_income,
        "total_expense": total_expense,
        "total_transfer": total_transfer,
        "net_savings": net_savings,
        "savings_rate": savings_rate,
        "daily_avg_expense": daily_avg_expense,
        "days_count": days_count,
        "expense_breakdown": expense_breakdown,
        "income_breakdown": income_breakdown,
        "account_stats": account_stats,
    }
