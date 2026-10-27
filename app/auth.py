from datetime import datetime
from fastapi import Request, HTTPException, status, Depends
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db

try:
    from app.models.user import User
except ImportError:
    from app.models import User

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
COOKIE_NAME = "session_token"
SESSION_MAX_AGE = 86400 * 30  # ۳۰ روز

def create_session_token(user_id: int, username: str) -> str:
    """ساخت توکن امن حاوی شناسه و نام کاربری"""
    return serializer.dumps({"user_id": user_id, "username": username})

def verify_session_token(token: str) -> dict | None:
    """اعتبارسنجی توکن (اعتبار ۳۰ روزه)"""
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data
    except (BadSignature, SignatureExpired):
        return None

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    وابستگی (Dependency) اصلی برای احراز هویت:
    آبجکت کامل کاربر جاری را برمی‌گرداند.
    در صورت عدم لاگین، کاربر را به /login هدایت می‌کند.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )

    data = verify_session_token(token)
    if not data or "user_id" not in data:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )

    user = db.query(User).filter(User.id == data["user_id"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )

    # به‌روزرسانی زمان آخرین بازدید (حداکثر هر ۵ دقیقه یک‌بار برای بهینگی)
    now = datetime.now()
    if not user.last_seen or (now - user.last_seen).total_seconds() > 300:
        user.last_seen = now
        try:
            db.commit()
        except Exception:
            db.rollback()

    return user

def is_admin_user(user: User) -> bool:
    """تشخیص اکانت اصلی: کاربر اول سیستم، پرچم is_admin، یا منطبق با تنظیمات env"""
    admin_user = getattr(settings, "ADMIN_USERNAME", "admin")
    return bool(getattr(user, 'is_admin', False) or user.id == 1 or user.username == admin_user)
