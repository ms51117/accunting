from fastapi import Request, HTTPException, status, Depends
from itsdangerous import URLSafeTimedSerializer
from app.config import settings

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
COOKIE_NAME = "session_token"

def create_session_token(username: str) -> str:
    return serializer.dumps({"user": username})

def verify_session_token(token: str) -> str | None:
    try:
        data = serializer.loads(token, max_age=86400 * 30) # اعتبار ۳۰ روزه روی مرورگر
        return data.get("user")
    except Exception:
        return None

def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    user = verify_session_token(token)
    if not user or user != settings.ADMIN_USERNAME:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    return user
