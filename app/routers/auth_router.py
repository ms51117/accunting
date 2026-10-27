import hashlib
import secrets
import os

from fastapi import APIRouter, Request, Depends, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.auth import (
    create_session_token,
    verify_session_token,
    get_current_user,
    COOKIE_NAME,
    SESSION_MAX_AGE,
    is_admin_user
)
from app.models.account import Account

try:
    from app.models.user import User
except ImportError:
    from app.models import User

# استفاده از bcrypt در صورت نصب بودن، با fallback به sha256_salt
try:
    import bcrypt
    def get_password_hash(password: str) -> str:
        pwd_bytes = password.encode('utf-8')[:72]
        return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode('utf-8')

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            pwd_bytes = plain_password.encode('utf-8')[:72]
            return bcrypt.checkpw(pwd_bytes, hashed_password.encode('utf-8'))
        except Exception:
            return False
except ImportError:
    def get_password_hash(password: str) -> str:
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
        return f"{salt}${h}"

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            if "$" not in hashed_password:
                return False
            salt, h = hashed_password.split("$", 1)
            expected = hashlib.sha256((salt + plain_password).encode('utf-8')).hexdigest()
            return secrets.compare_digest(h, expected)
        except Exception:
            return False

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

def get_admin_users_data(db: Session) -> list:
    """محاسبه لیست کاربران و مجموع موجودی حساب‌های هر کاربر برای پنل مدیر"""
    all_users = db.query(User).order_by(User.id.asc()).all()
    users_data = []
    for u in all_users:
        total_balance = db.query(func.coalesce(func.sum(Account.balance), 0))\
                          .filter(Account.user_id == u.id).scalar()
        users_data.append({
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name or "---",
            "total_balance": total_balance or 0,
            "last_seen": u.last_seen
        })
    return users_data

# --- صفحه لاگین ---
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token and verify_session_token(token):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@router.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    username_clean = username.strip()
    user = db.query(User).filter(User.username == username_clean).first()

    # ایجاد خودکار اولین کاربر از روی .env در صورت خالی بودن دیتابیس
    if not user and db.query(User).count() == 0:
        admin_u = getattr(settings, "ADMIN_USERNAME", "admin")
        admin_p = getattr(settings, "ADMIN_PASSWORD", "admin")
        admin_c = getattr(settings, "ADMIN_CHAT_ID", None)
        if username_clean == admin_u and password == admin_p:
            user = User(
                username=admin_u,
                password_hash=get_password_hash(admin_p),
                is_admin=True,
                telegram_chat_id=admin_c
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "نام کاربری یا رمز عبور اشتباه است."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # ساخت توکن با user_id و username
    token = create_session_token(user_id=user.id, username=user.username)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_MAX_AGE,
        samesite="lax"
    )
    return response

# --- خروج از حساب ---
@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=COOKIE_NAME)
    return response


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    admin_status = is_admin_user(current_user)
    users_data = get_admin_users_data(db) if admin_status else []

    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "user": current_user,
            "is_admin": admin_status,
            "current_user": current_user,
            "users_data": users_data,
            "error": None,
            "success": None
        }
    )

@router.post("/profile/update-info", response_class=HTMLResponse)
def update_profile_info(
    request: Request,
    full_name: str = Form(...),
    new_username: str = Form(None),
    telegram_chat_id: str = Form(None),
    current_password: str = Form(...),
    new_password: str = Form(None),
    confirm_password: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    admin_status = is_admin_user(current_user)

    def render_view(error=None, success=None, status_code=200):
        users_data = get_admin_users_data(db) if admin_status else []
        return templates.TemplateResponse(
            request=request,
            name="profile.html",
            context={
                "user": current_user,
                "current_user": current_user,
                "is_admin": admin_status,
                "users_data": users_data,
                "error": error,
                "success": success
            },
            status_code=status_code
        )

    # تایید رمز فعلی جهت اعمال هرگونه تغییر
    if not verify_password(current_password, current_user.password_hash):
        return render_view(error="کلمه عبور فعلی نادرست است.", status_code=400)

    # ۱. ویرایش نام و نام خانوادگی
    current_user.full_name = full_name.strip()

    if telegram_chat_id is not None:
        clean_chat_id = telegram_chat_id.strip()
        current_user.telegram_chat_id = clean_chat_id if clean_chat_id else None

    # ۲. ویرایش نام کاربری
    if new_username:
        clean_user = new_username.strip()
        if clean_user and clean_user != current_user.username:
            exists = db.query(User).filter(User.username == clean_user).first()
            if exists:
                return render_view(error="این نام کاربری قبلاً استفاده شده است.", status_code=400)
            current_user.username = clean_user

    # ۳. تغییر کلمه عبور در صورت ارسال
    if new_password:
        if new_password != confirm_password:
            return render_view(error="کلمه عبور جدید با تکرار آن یکسان نیست.", status_code=400)
        if len(new_password) < 4:
            return render_view(error="کلمه عبور جدید باید حداقل ۴ کاراکتر باشد.", status_code=400)
        current_user.password_hash = get_password_hash(new_password)

    db.commit()
    db.refresh(current_user)

    token = create_session_token(user_id=current_user.id, username=current_user.username)
    response = render_view(success="اطلاعات پروفایل شما با موفقیت به‌روزرسانی شد.")
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_MAX_AGE,
        samesite="lax"
    )
    return response

@router.post("/profile/create-user", response_class=HTMLResponse)
def create_new_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(None),
    password: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    admin_status = is_admin_user(current_user)
    if not admin_status:
        raise HTTPException(status_code=403, detail="شما دسترسی ایجاد کاربر جدید را ندارید.")

    clean_username = username.strip()

    def render_admin_view(error=None, success=None, status_code=200):
        users_data = get_admin_users_data(db)
        return templates.TemplateResponse(
            request=request,
            name="profile.html",
            context={
                "user": current_user,
                "current_user": current_user,
                "is_admin": admin_status,
                "users_data": users_data,
                "error": error,
                "success": success
            },
            status_code=status_code
        )

    if not clean_username or not password:
        return render_admin_view(error="نام کاربری و رمز عبور الزامی است.", status_code=400)

    if len(password) < 4:
        return render_admin_view(error="کلمه عبور باید حداقل ۴ کاراکتر باشد.", status_code=400)

    exists = db.query(User).filter(User.username == clean_username).first()
    if exists:
        return render_admin_view(error="این نام کاربری قبلاً ثبت شده است.", status_code=400)

    new_u = User(
        username=clean_username,
        full_name=full_name.strip() if full_name else None,
        password_hash=get_password_hash(password),
        is_admin=False
    )
    db.add(new_u)
    db.commit()

    return render_admin_view(success=f"کاربر «{clean_username}» با موفقیت ایجاد شد.")