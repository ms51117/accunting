from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.auth import get_current_user
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.jalali import format_rial, to_jalali_str

router = APIRouter(prefix="/categories", tags=["Categories"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


POPULAR_ICONS = [
    ("tag", "برچسب (عمومی)"),
    ("cart", "خرید و کالا"),
    ("cash-stack", "پول و وجه نقد"),
    ("wallet2", "کیف پول و حقوق"),
    ("bank2", "امور بانکی و اداری"),
    ("gem", "طلا و جواهرات"),
    ("heart-pulse", "پزشکی و سلامت"),
    ("tools", "ابزار و ساخت‌وساز"),
    ("briefcase", "کار و پروژه"),
    ("receipt", "قبوض و اجاره"),
    ("truck", "حمل و باربری"),
    ("cup-hot", "غذا و پذیرایی"),
    ("lightning", "انرژی و تاسیسات"),
    ("file-earmark-text", "قرارداد و سند"),
    ("arrow-repeat", "وام و تسویه"),
    ("card-checklist", "چک و اسناد"),
    ("percent", "کمیسیون و درصد"),
    ("car-front", "خودرو و بنزین"),
    ("phone", "تلفن و اینترنت"),
    ("house", "مسکن و ملک"),
]

COLOR_PALETTE = [
    "#3b82f6",  # آبی
    "#10b981",  # سبز زمردی
    "#ef4444",  # سرخ
    "#f59e0b",  # کهربایی / طلایی
    "#8b5cf6",  # بنفش
    "#ec4899",  # صورتی
    "#06b6d4",  # فیروزه‌ای
    "#f97316",  # نارنجی
    "#64748b",  # خاکستری تیره
    "#14b8a6",  # سدری / تیال
]


@router.get("")
@router.get("/")
def list_categories(
    request: Request,
    type_filter: str = "ALL",
    search: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Category).filter(Category.user_id == current_user.id)

    if type_filter and type_filter != "ALL":
        query = query.filter((Category.type == type_filter) | (Category.type == "BOTH"))

    if search and search.strip():
        s = search.strip()
        query = query.filter(Category.title.contains(s) | Category.description.contains(s))

    categories = query.order_by(Category.title.asc()).all()

    # استخراج آمار تراکنش‌ها و مبالغ برای هر دسته
    category_stats = {}
    stats_query = (
        db.query(
            Transaction.category_id,
            func.count(Transaction.id).label("tx_count"),
            func.sum(Transaction.amount).label("total_amount")
        )
        .filter(Transaction.user_id == current_user.id, Transaction.category_id.isnot(None))
        .group_by(Transaction.category_id)
        .all()
    )
    for cat_id, tx_count, total_amount in stats_query:
        category_stats[cat_id] = {
            "count": tx_count or 0,
            "total_amount": total_amount or 0
        }

    # آمار کل دسته‌بندی‌های کاربر
    all_user_cats = db.query(Category).filter(Category.user_id == current_user.id).all()
    total_count = len(all_user_cats)
    expense_count = sum(1 for c in all_user_cats if c.type in ("EXPENSE", "BOTH"))
    income_count = sum(1 for c in all_user_cats if c.type in ("INCOME", "BOTH"))

    return templates.TemplateResponse(
        request=request,
        name="categories/list.html",
        context={
            "categories": categories,
            "category_stats": category_stats,
            "total_count": total_count,
            "expense_count": expense_count,
            "income_count": income_count,
            "type_filter": type_filter,
            "search": search or "",
            "popular_icons": POPULAR_ICONS,
            "color_palette": COLOR_PALETTE,
            "user": current_user
        }
    )


@router.post("/create")
def create_category(
    title: str = Form(...),
    type: str = Form("BOTH"),
    color: str = Form("#3b82f6"),
    icon: str = Form("tag"),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    clean_title = title.strip()
    if not clean_title:
        return RedirectResponse(url="/categories?error=عنوان_دسته‌بندی_الزامی_است", status_code=status.HTTP_303_SEE_OTHER)

    clean_type = type.upper() if type in ("INCOME", "EXPENSE", "BOTH") else "BOTH"
    clean_color = color.strip() if color else "#3b82f6"
    clean_icon = icon.strip() if icon else "tag"

    # بررسی عدم تکراری بودن عنوان برای این کاربر
    existing = (
        db.query(Category)
        .filter(Category.user_id == current_user.id, Category.title == clean_title)
        .first()
    )
    if existing:
        return RedirectResponse(
            url="/categories?error=دسته‌بندی_با_این_عنوان_از_قبل_وجود_دارد",
            status_code=status.HTTP_303_SEE_OTHER
        )

    cat = Category(
        user_id=current_user.id,
        title=clean_title,
        type=clean_type,
        color=clean_color,
        icon=clean_icon,
        description=description.strip() if description else None
    )
    db.add(cat)
    db.commit()

    return RedirectResponse(url="/categories?msg=دسته‌بندی_جدید_با_موفقیت_ثبت_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cat_id}/edit")
def edit_category(
    cat_id: int,
    title: str = Form(...),
    type: str = Form("BOTH"),
    color: str = Form("#3b82f6"),
    icon: str = Form("tag"),
    description: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cat = (
        db.query(Category)
        .filter(Category.id == cat_id, Category.user_id == current_user.id)
        .first()
    )
    if not cat:
        return RedirectResponse(url="/categories?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    clean_title = title.strip()
    if not clean_title:
        return RedirectResponse(url="/categories?error=عنوان_دسته‌بندی_الزامی_است", status_code=status.HTTP_303_SEE_OTHER)

    # بررسی تکراری نبودن عنوان جدید با دسته دیگر
    conflict = (
        db.query(Category)
        .filter(Category.user_id == current_user.id, Category.title == clean_title, Category.id != cat_id)
        .first()
    )
    if conflict:
        return RedirectResponse(
            url="/categories?error=دسته‌بندی_دیگری_با_این_عنوان_وجود_دارد",
            status_code=status.HTTP_303_SEE_OTHER
        )

    clean_type = type.upper() if type in ("INCOME", "EXPENSE", "BOTH") else "BOTH"
    clean_color = color.strip() if color else "#3b82f6"
    clean_icon = icon.strip() if icon else "tag"

    # به‌روزرسانی مشخصات دسته
    cat.title = clean_title
    cat.type = clean_type
    cat.color = clean_color
    cat.icon = clean_icon
    cat.description = description.strip() if description else None

    # همگام‌سازی عنوان رشته‌ای در تمام تراکنش‌های متصل برای حفظ یکپارچگی تاریخی
    db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.category_id == cat_id
    ).update({Transaction.category: clean_title}, synchronize_session=False)

    db.commit()
    return RedirectResponse(url="/categories?msg=دسته‌بندی_با_موفقیت_ویرایش_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{cat_id}/delete")
def delete_category(
    cat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cat = (
        db.query(Category)
        .filter(Category.id == cat_id, Category.user_id == current_user.id)
        .first()
    )
    if not cat:
        return RedirectResponse(url="/categories?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # برای تراکنش‌های متصل، category_id نال می‌شود اما متن category حفظ می‌شود تا هیچ دیتایی از بین نرود
    db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.category_id == cat_id
    ).update({Transaction.category_id: None}, synchronize_session=False)

    db.delete(cat)
    db.commit()
    return RedirectResponse(url="/categories?msg=دسته‌بندی_با_موفقیت_حذف_شد", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/list")
def api_list_categories(
    type: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Category).filter(Category.user_id == current_user.id)
    if type and type in ("INCOME", "EXPENSE"):
        query = query.filter((Category.type == type) | (Category.type == "BOTH"))
    cats = query.order_by(Category.title.asc()).all()

    return JSONResponse(content=[
        {
            "id": c.id,
            "title": c.title,
            "type": c.type,
            "color": c.color,
            "icon": c.icon
        }
        for c in cats
    ])
