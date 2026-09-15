from fastapi import APIRouter, Request, Form, Depends, responses, status
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.auth import create_session_token, COOKIE_NAME

router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_action(
        request: Request,
        username: str = Form(...),
        password: str = Form(...)
):
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        token = create_session_token(username)
        response = responses.RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=86400 * 30,
            samesite="lax"
        )
        return response

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "نام کاربری یا کلمه عبور نادرست است."}
    )


@router.get("/logout")
def logout_action():
    response = responses.RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(COOKIE_NAME)
    return response
