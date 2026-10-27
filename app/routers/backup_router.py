# app/routers/backup_router.py
import io
import json
import os
import httpx
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.models.person import Person
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.debt import Debt
from app.models.cheque import Cheque
from app.utils.jalali import format_rial, to_jalali_str

router = APIRouter(prefix="/backups", tags=["Backup"])
templates = Jinja2Templates(directory="app/templates")

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = to_jalali_str


def get_httpx_client(**kwargs) -> httpx.AsyncClient:
    """ساخت نمونه AsyncClient با پشتیبانی از پروکسی برای اتصال به تلگرام"""
    proxy = getattr(settings, "HTTPS_PROXY", None) or getattr(settings, "HTTP_PROXY", None) or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        return httpx.AsyncClient(proxy=proxy, **kwargs)
    return httpx.AsyncClient(**kwargs)


# --- توابع کمکی برای تبدیل امن تاریخ‌ها ---
def parse_date(date_val):
    if not date_val:
        return None
    if isinstance(date_val, (date, datetime)):
        return date_val if isinstance(date_val, date) else date_val.date()
    try:
        return datetime.fromisoformat(str(date_val)).date()
    except Exception:
        return None


# --- تابع استخراج داده‌های کاربر با حفظ پیوندهای رابطه‌ای ---
def export_user_data(user: User, db: Session) -> dict:
    user_id = user.id

    persons = db.query(Person).filter(Person.user_id == user_id).all()
    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    categories = db.query(Category).filter(Category.user_id == user_id).all()
    debts = db.query(Debt).filter(Debt.user_id == user_id).all()
    cheques = db.query(Cheque).filter(Cheque.user_id == user_id).all()
    transactions = db.query(Transaction).filter(Transaction.user_id == user_id).all()

    person_map = {p.id: p.full_name for p in persons}
    account_map = {a.id: a.title for a in accounts}
    category_map = {c.id: c.title for c in categories}

    return {
        "version": "2.2",
        "exported_at": datetime.now().isoformat(),
        "user": {
            "username": user.username,
            "full_name": user.full_name
        },
        "categories": [
            {
                "id": c.id,
                "title": c.title,
                "type": c.type,
                "color": c.color,
                "icon": c.icon,
                "description": c.description
            }
            for c in categories
        ],
        "persons": [
            {
                "id": p.id,
                "full_name": p.full_name,
                "phone": p.phone,
                "sheba": p.sheba,
                "card_number": p.card_number,
                "bank_name": p.bank_name,
                "notes": p.notes
            }
            for p in persons
        ],
        "accounts": [
            {
                "id": a.id,
                "title": a.title,
                "bank_name": a.bank_name,
                "account_number": a.account_number,
                "sheba": a.sheba,
                "balance": int(a.balance or 0)
            }
            for a in accounts
        ],
        "debts": [
            {
                "ref_id": d.id,
                "type": d.type,
                "amount": int(d.amount),
                "paid_amount": int(d.paid_amount or 0),
                "due_date": d.due_date.isoformat() if d.due_date else None,
                "status": d.status,
                "description": d.description,
                "person_name": person_map.get(d.person_id)
            }
            for d in debts
        ],
        "cheques": [
            {
                "ref_id": c.id,
                "type": c.type,
                "cheque_number": c.cheque_number,
                "sayad_number": c.sayad_number,
                "bank_name": c.bank_name,
                "amount": int(c.amount),
                "issue_date": c.issue_date.isoformat() if c.issue_date else None,
                "due_date": c.due_date.isoformat() if c.due_date else None,
                "cleared_date": c.cleared_date.isoformat() if c.cleared_date else None,
                "status": c.status,
                "description": c.description,
                "person_name": person_map.get(c.person_id),
                "account_title": account_map.get(c.account_id)
            }
            for c in cheques
        ],
        "transactions": [
            {
                "type": t.type,
                "category": t.category,
                "category_title": category_map.get(t.category_id, t.category),
                "category_id": t.category_id,
                "amount": int(t.amount),
                "trans_date": t.trans_date.isoformat() if t.trans_date else None,
                "description": t.description,
                "account_title": account_map.get(t.account_id),
                "destination_account_title": account_map.get(t.destination_account_id),
                "person_name": person_map.get(t.person_id),
                "debt_ref_id": t.debt_id,
                "cheque_ref_id": t.cheque_id
            }
            for t in transactions
        ]
    }


# ۱. صفحه اصلی مدیریت بک‌آپ
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def backup_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        request=request,
        name="backup.html",
        context={
            "current_user": current_user,
            "user": current_user,
            "has_telegram": bool(current_user.telegram_chat_id)
        }
    )


# ۲. دانلود مستقیم فایل بک‌آپ
@router.get("/download")
def download_backup(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    data = export_user_data(current_user, db)
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    stream = io.BytesIO(json_str.encode('utf-8'))

    filename = f"backup_{current_user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return StreamingResponse(
        stream,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ۳. ارسال بک‌آپ از طریق تلگرام با پروکسی
@router.post("/send-telegram")
async def send_backup_telegram(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not bot_token:
        raise HTTPException(status_code=500, detail="توکن بات تلگرام در تنظیمات سیستم تعریف نشده است.")

    chat_id = current_user.telegram_chat_id
    if not chat_id:
        raise HTTPException(status_code=400, detail="شناسه تلگرام در پروفایل شما ثبت نشده است.")

    data = export_user_data(current_user, db)
    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    filename = f"backup_{current_user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    try:
        async with get_httpx_client(timeout=35.0) as client:
            files = {"document": (filename, json_bytes, "application/json")}
            form_data = {
                "chat_id": chat_id,
                "caption": f"📦 فایل پشتیبان اطلاعات مالی: {current_user.full_name or current_user.username}\n📅 تاریخ: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
            }
            resp = await client.post(url, data=form_data, files=files)

            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"خطا در ارسال به تلگرام: {resp.text}")

        return {"status": "success", "message": "فایل پشتیبان با موفقیت به تلگرام شما ارسال شد."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در ارتباط با سرور تلگرام: {str(e)}")


# ۴. بازیابی (Restore) امن و کامل اطلاعات
@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="فرمت فایل نامعتبر است. فقط فایل‌های JSON پذیرفته می‌شوند.")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم فایل بیش از حد مجاز است (حداکثر ۱۰ مگابایت).")

    try:
        data = json.loads(content.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="محتوای فایل JSON معتبر نیست یا فایل آسیب دیده است.")

    if not isinstance(data, dict) or "accounts" not in data:
        raise HTTPException(status_code=400, detail="ساختار فایل بک‌آپ استاندارد نیست.")

    user_id = current_user.id

    try:
        # حذف داده‌های قبلی کاربر برای بازنشانی تمیز
        db.query(Transaction).filter(Transaction.user_id == user_id).delete()
        db.query(Cheque).filter(Cheque.user_id == user_id).delete()
        db.query(Debt).filter(Debt.user_id == user_id).delete()
        db.query(Account).filter(Account.user_id == user_id).delete()
        db.query(Person).filter(Person.user_id == user_id).delete()
        db.query(Category).filter(Category.user_id == user_id).delete()
        db.flush()

        # ۰. بازیابی دسته‌بندی‌ها
        category_map = {}
        for c in data.get("categories", []):
            cat_title = (c.get("title") or "").strip()
            if cat_title:
                new_cat = Category(
                    user_id=user_id,
                    title=cat_title,
                    type=c.get("type") or "BOTH",
                    color=c.get("color") or "#3b82f6",
                    icon=c.get("icon") or "tag",
                    description=c.get("description")
                )
                db.add(new_cat)
                db.flush()
                category_map[cat_title] = new_cat.id
                if "id" in c:
                    category_map[str(c["id"])] = new_cat.id

        # ۱. بازیابی اشخاص
        person_map = {}
        for p in data.get("persons", []):
            name = p.get("full_name") or p.get("name") or "نامشخص"
            new_person = Person(
                user_id=user_id,
                full_name=name,
                phone=p.get("phone"),
                sheba=p.get("sheba"),
                card_number=p.get("card_number"),
                bank_name=p.get("bank_name"),
                notes=p.get("notes") or p.get("description")
            )
            db.add(new_person)
            db.flush()
            person_map[name] = new_person.id
            if "id" in p:
                person_map[str(p["id"])] = new_person.id

        # ۲. بازیابی حساب‌ها
        account_map = {}
        for a in data.get("accounts", []):
            title = a.get("title") or "حساب اصلی"
            new_acc = Account(
                user_id=user_id,
                title=title,
                bank_name=a.get("bank_name"),
                account_number=a.get("account_number"),
                sheba=a.get("sheba"),
                balance=int(a.get("balance", 0))
            )
            db.add(new_acc)
            db.flush()
            account_map[title] = new_acc.id
            if "id" in a:
                account_map[str(a["id"])] = new_acc.id

        # ۳. بازیابی بدهی‌ها و مطالبات
        debt_ref_map = {}
        for d in data.get("debts", []):
            p_name = d.get("person_name")
            p_id = person_map.get(p_name)

            if not p_id and p_name:
                auto_person = Person(user_id=user_id, full_name=p_name)
                db.add(auto_person)
                db.flush()
                p_id = auto_person.id
                person_map[p_name] = p_id

            if p_id:
                new_debt = Debt(
                    user_id=user_id,
                    type=d.get("type") or d.get("debt_type") or "RECEIVABLE",
                    person_id=p_id,
                    amount=int(d.get("amount", 0)),
                    paid_amount=int(d.get("paid_amount", 0)),
                    due_date=parse_date(d.get("due_date")),
                    status=d.get("status") or "ACTIVE",
                    description=d.get("description")
                )
                db.add(new_debt)
                db.flush()
                if "ref_id" in d:
                    debt_ref_map[d["ref_id"]] = new_debt.id

        # ۴. بازیابی چک‌ها
        cheque_ref_map = {}
        for c in data.get("cheques", []):
            p_name = c.get("person_name")
            p_id = person_map.get(p_name)
            if not p_id and p_name:
                auto_person = Person(user_id=user_id, full_name=p_name)
                db.add(auto_person)
                db.flush()
                p_id = auto_person.id
                person_map[p_name] = p_id

            acc_id = account_map.get(c.get("account_title"))
            issue_d = parse_date(c.get("issue_date")) or date.today()
            due_d = parse_date(c.get("due_date")) or date.today()

            if p_id:
                new_cheque = Cheque(
                    user_id=user_id,
                    type=c.get("type") or c.get("cheque_type") or "RECEIVABLE",
                    cheque_number=c.get("cheque_number"),
                    sayad_number=c.get("sayad_number"),
                    bank_name=c.get("bank_name"),
                    amount=int(c.get("amount", 0)),
                    issue_date=issue_d,
                    due_date=due_d,
                    cleared_date=parse_date(c.get("cleared_date")),
                    status=c.get("status") or "PENDING",
                    person_id=p_id,
                    account_id=acc_id,
                    description=c.get("description")
                )
                db.add(new_cheque)
                db.flush()
                if "ref_id" in c:
                    cheque_ref_map[c["ref_id"]] = new_cheque.id

        # ۵. بازیابی تراکنش‌ها با اتصال به چک‌ها و بدهی‌ها
        for t in data.get("transactions", []):
            acc_id = account_map.get(t.get("account_title"))
            dest_acc_id = account_map.get(t.get("destination_account_title"))
            p_id = person_map.get(t.get("person_name"))

            if not acc_id and account_map:
                acc_id = next(iter(account_map.values()))

            if acc_id:
                trans_d = parse_date(t.get("trans_date") or t.get("date")) or date.today()
                cat_title = (t.get("category_title") or t.get("category") or "سایر").strip()
                if not cat_title:
                    cat_title = "سایر"

                # ساخت خودکار دسته‌بندی در صورتی که در فایل موجود نباشد (بک‌آپ قدیمی)
                if cat_title not in category_map:
                    auto_cat = Category(
                        user_id=user_id,
                        title=cat_title,
                        type=t.get("type") or "BOTH",
                        color="#3b82f6",
                        icon="tag",
                        description="بازیابی خودکار از فایل پشتیبان"
                    )
                    db.add(auto_cat)
                    db.flush()
                    category_map[cat_title] = auto_cat.id

                assigned_cat_id = category_map.get(cat_title) or (category_map.get(str(t.get("category_id"))) if t.get("category_id") else None)

                new_trx = Transaction(
                    user_id=user_id,
                    account_id=acc_id,
                    destination_account_id=dest_acc_id,
                    person_id=p_id,
                    type=t.get("type") or t.get("transaction_type") or "EXPENSE",
                    category=cat_title,
                    category_id=assigned_cat_id,
                    amount=int(t.get("amount", 0)),
                    trans_date=trans_d,
                    description=t.get("description"),
                    debt_id=debt_ref_map.get(t.get("debt_ref_id")),
                    cheque_id=cheque_ref_map.get(t.get("cheque_ref_id"))
                )
                db.add(new_trx)

        db.commit()
        return {"status": "success", "message": "اطلاعات با موفقیت و حفظ روابط مالی به‌طور کامل بازگردانی شد."}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"خطا در بازیابی اطلاعات: {str(e)}")
