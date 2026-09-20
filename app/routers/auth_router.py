import hashlib
import secrets
from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.auth import create_session_token, verify_session_token, get_current_user, COOKIE_NAME

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

# --- صفحه لاگین ---
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token and verify_session_token(token):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request,name="login.html",context= {"error": None})

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
        if username_clean == admin_u and password == admin_p:
            user = User(
                username=admin_u,
                password_hash=get_password_hash(admin_p)
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request,name="login.html",context=
            {"error": "نام کاربری یا رمز عبور اشتباه است."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # ساخت توکن با user_id و username
    token = create_session_token(user_id=user.id, username=user.username)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400 * 30,
        samesite="lax"
    )
    return response

# --- خروج از حساب ---
@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=COOKIE_NAME)
    return response

# --- صفحه تغییر رمز عبور ---
@router.get("/change-password", response_class=HTMLResponse)
def change_password_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        request=request,
        name="change_password.html",
        context={
            "user": current_user,
            "error": None,
            "success": None
        }
    )

@router.post("/change-password")
def change_password_post(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    new_username: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    def render_error(msg: str):
        return templates.TemplateResponse(
            request=request,
            name="change_password.html",
            context={
                "user": current_user,
                "error": msg,
                "success": None
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if not verify_password(current_password, current_user.password_hash):
        return render_error("رمز عبور فعلی نادرست است.")

    if new_password != confirm_password:
        return render_error("رمز عبور جدید با تکرار آن مطابقت ندارد.")

    if len(new_password) < 4:
        return render_error("رمز عبور جدید باید حداقل ۴ کاراکتر باشد.")

    # تغییر نام کاربری در صورت ارسال
    target_username = current_user.username
    if new_username and new_username.strip():
        u_clean = new_username.strip()
        if u_clean != current_user.username:
            existing = db.query(User).filter(User.username == u_clean).first()
            if existing:
                return render_error("این نام کاربری قبلاً انتخاب شده است.")
            current_user.username = u_clean
            target_username = u_clean

    current_user.password_hash = get_password_hash(new_password)
    db.commit()
    db.refresh(current_user)

    # به‌روزرسانی کوکی با توکن جدید
    token = create_session_token(user_id=current_user.id, username=target_username)
    response = templates.TemplateResponse(
        request=request,
        name="change_password.html",
        context={
            "user": current_user,
            "error": None,
            "success": "اطلاعات با موفقیت به‌روزرسانی شد."
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
