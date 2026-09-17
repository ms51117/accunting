from fastapi import APIRouter, Request, Form, Depends, responses, status
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.auth import create_session_token, COOKIE_NAME, get_current_user

# ایمپورت مدل User (پشتیبانی از هر دو حالت قرارگیری مدل)
try:
    from app.models import User
except ImportError:
    from app.models.user import User

try:
    import bcrypt

    def get_password_hash(password: str) -> str:
        # bcrypt محدودیت ۷۲ بایتی دارد؛ برش دستی برای جلوگیری از خطای طول
        pw_bytes = password.encode('utf-8')[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            pw_bytes = plain_password.encode('utf-8')[:72]
            h_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(pw_bytes, h_bytes)
        except Exception:
            return False

except ImportError:
    import hashlib
    import secrets

    def get_password_hash(password: str) -> str:
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return f"{salt}${h}"

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        if "$" not in hashed_password:
            return plain_password == hashed_password
        salt, h = hashed_password.split("$", 1)
        return hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest() == h


router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")

# فیلترهای قالب Jinja2
def format_rial(value):
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)

def format_jalali(value):
    return str(value)

templates.env.filters["rial"] = format_rial
templates.env.filters["jalali"] = format_jalali


# ==========================================
# ورود (Login)
# ==========================================

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "error": None}
    )


@router.post("/login")
def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # جستجوی کاربر در دیتابیس
    user = db.query(User).filter(User.username == username.strip()).first()

    # ایجاد خودکار اولین کاربر از تنظیمات در صورت خالی بودن دیتابیس
    if not user and db.query(User).count() == 0:
        if username.strip() == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
            user = User(
                username=settings.ADMIN_USERNAME,
                password_hash=get_password_hash(settings.ADMIN_PASSWORD)
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    # بررسی صحت اعتبارنامه
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "error": "نام کاربری یا رمز عبور اشتباه است."
            }
        )

    # ساخت توکن سشن و ذخیره در کوکی
    token = create_session_token(user.username)
    response = responses.RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400 * 30,
        samesite="lax"
    )
    return response


# ==========================================
# خروج (Logout)
# ==========================================

@router.get("/logout")
def logout():
    response = responses.RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(COOKIE_NAME)
    return response


# ==========================================
# تغییر مشخصات و رمز عبور (Change Password)
# ==========================================

@router.get("/change-password")
def change_password_page(
    request: Request,
    current_user = Depends(get_current_user)
):
    return templates.TemplateResponse(
        request=request,
        name="change_password.html",
        context={
            "request": request,
            "current_user": current_user,
            "error": None,
            "success": None
        }
    )


@router.post("/change-password")
def change_password_action(
    request: Request,
    old_password: str = Form(...),
    new_username: str = Form(None),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # دریافت نام کاربری کاربر جاری
    current_username = getattr(current_user, "username", str(current_user))
    user = db.query(User).filter(User.username == current_username).first()

    if not user:
        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "request": request,
                "current_user": current_user,
                "error": "حساب کاربری یافت نشد!",
                "success": None
            }
        )

    # ۱. اعتبارسنجی رمز عبور فعلی
    if not verify_password(old_password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "request": request,
                "current_user": current_user,
                "error": "رمز عبور فعلی وارد شده نادرست است.",
                "success": None
            }
        )

    # ۲. بررسی تطابق رمز جدید و تکرار آن
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "request": request,
                "current_user": current_user,
                "error": "رمز عبور جدید و تکرار آن همخوانی ندارند.",
                "success": None
            }
        )

    # ۳. حداقل طول مجاز رمز عبور
    if len(new_password) < 4:
        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "request": request,
                "current_user": current_user,
                "error": "رمز عبور جدید باید حداقل ۴ کاراکتر باشد.",
                "success": None
            }
        )

    # ۴. تغییر نام کاربری (در صورت ارسال و تغییر)
    if new_username and new_username.strip() and new_username.strip() != user.username:
        clean_user = new_username.strip()
        existing = db.query(User).filter(User.username == clean_user, User.id != user.id).first()
        if existing:
            return templates.TemplateResponse(
                request=request,
                name="change_password.html",
                context={
                    "request": request,
                    "current_user": current_user,
                    "error": "این نام کاربری از قبل در سیستم وجود دارد.",
                    "success": None
                }
            )
        user.username = clean_user

    # ۵. هش کردن و به‌روزرسانی رمز در دیتابیس
    user.password_hash = get_password_hash(new_password)
    db.commit()
    db.refresh(user)

    # ساخت توکن جدید متناسب با نام کاربری نهایی
    token = create_session_token(user.username)
    response = templates.TemplateResponse(
        request=request,
        name="change_password.html",
        context={
            "request": request,
            "current_user": user,
            "error": None,
            "success": "اطلاعات امنیتی با موفقیت به‌روزرسانی شد."
        }
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400 * 30,
        samesite="lax"
    )
    return response
