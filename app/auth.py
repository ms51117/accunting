from fastapi import Request, HTTPException, status, Depends
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
# مدل User را وارد کنید (مسیر را با ساختار پروژه‌تان تطبیق دهید)
try:
    from app.models.user import User
except ImportError:
    from app.models import User

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
COOKIE_NAME = "session_token"

def create_session_token(user_id: int, username: str) -> str:
    """ساخت توکن امن حاوی شناسه و نام کاربری"""
    return serializer.dumps({"user_id": user_id, "username": username})

def verify_session_token(token: str) -> dict | None:
    """اعتبارسنجی توکن (اعتبار ۳۰ روزه)"""
    try:
        data = serializer.loads(token, max_age=86400 * 30)
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

    return user
