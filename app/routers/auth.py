from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.database import SessionLocal
from app.models import User
from app.core.security import hash_password, create_session
from sqlalchemy import or_

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_user_by_login_or_email(login_or_email: str):
    db = SessionLocal()
    user = db.query(User).filter(or_(User.login == login_or_email, User.email == login_or_email)).first()
    db.close()
    return user

def create_user(login: str, email: str, password: str, role: str = 'unassigned'):
    db = SessionLocal()
    user = User(login=login, email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    user_id = user.id
    db.close()
    return user_id

@router.get("/login", response_class=HTMLResponse)
async def login_page():
    return templates.TemplateResponse("login.html", {"request": {}})

@router.post("/login")
async def login(request: Request, login_or_email: str = Form(...), password: str = Form(...)):
    user = get_user_by_login_or_email(login_or_email)
    if not user or user.password_hash != hash_password(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный логин/email или пароль"})
    session_token = create_session(user.id)
    response = RedirectResponse(url=f"/gm_dashboard/{user.id}" if user.role == 'gm' else f"/player_dashboard/{user.id}/victorian_vampire", status_code=303)
    response.set_cookie(key="session", value=session_token, httponly=True, max_age=604800)
    return response

@router.get("/register", response_class=HTMLResponse)
async def register_page():
    return templates.TemplateResponse("register.html", {"request": {}})

@router.post("/register")
async def register(request: Request, login: str = Form(...), email: str = Form(...), password: str = Form(...), password_confirm: str = Form(...), role: str = Form("unassigned")):
    if password != password_confirm:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Пароли не совпадают"})
    if len(password) < 8:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Пароль должен быть не менее 8 символов"})
    db = SessionLocal()
    if db.query(User).filter_by(login=login).first():
        db.close()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Логин уже занят"})
    if db.query(User).filter_by(email=email).first():
        db.close()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email уже зарегистрирован"})
    db.close()
    user_id = create_user(login, email, password, role)
    session_token = create_session(user_id)
    response = RedirectResponse(url=f"/gm_dashboard/{user_id}" if role == 'gm' else f"/player_dashboard/{user_id}/victorian_vampire", status_code=303)
    response.set_cookie(key="session", value=session_token, httponly=True, max_age=604800)
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response
