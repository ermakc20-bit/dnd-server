from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.database import SessionLocal
from app.models import User
from app.core.security import hash_password, create_session, get_current_user
from sqlalchemy import or_

router = APIRouter()

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
async def login_page(request: Request):
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Вход в D&D</title>
    <style>
    body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
    .box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 320px; }
    input, button { width: 100%; padding: 10px; margin: 8px 0; border: none; border-radius: 6px; font-size: 14px; }
    input { background: #3a3a4e; color: #fff; }
    button { background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }
    a { color: #c7a252; text-decoration: none; }
    .error { color: #ff6b6b; text-align: center; margin-top: 10px; }
    </style>
    </head>
    <body>
    <div class="box">
    <h2>Вход в D&D</h2>
    <form method="post" action="/login">
    <input type="text" name="login_or_email" placeholder="Логин или Email" required>
    <input type="password" name="password" placeholder="Пароль" required>
    <button type="submit">Войти</button>
    </form>
    <p style="text-align: center; margin-top: 10px;">Нет аккаунта? <a href="/register">Зарегистрироваться</a></p>
    </div>
    </body>
    </html>
    """)

@router.post("/login")
async def login(request: Request, login_or_email: str = Form(...), password: str = Form(...)):
    user = get_user_by_login_or_email(login_or_email)
    if not user or user.password_hash != hash_password(password):
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><title>Ошибка входа</title>
        <style>
        body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 300px; text-align: center; }
        a { color: #c7a252; text-decoration: none; }
        </style>
        </head>
        <body>
        <div class="box">
        <h2 style="color: #ff6b6b;">❌ Неверный логин/email или пароль</h2>
        <a href="/login">Вернуться</a>
        </div>
        </body>
        </html>
        """, status_code=400)
    session_token = create_session(user.id)
    response = RedirectResponse(url=f"/gm_dashboard/{user.id}" if user.role == 'gm' else f"/player_dashboard/{user.id}/victorian_vampire", status_code=303)
    response.set_cookie(key="session", value=session_token, httponly=True, max_age=604800)
    return response

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Регистрация</title>
    <style>
    body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
    .box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 340px; }
    input, select, button { width: 100%; padding: 10px; margin: 8px 0; border: none; border-radius: 6px; font-size: 14px; }
    input, select { background: #3a3a4e; color: #fff; }
    button { background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }
    a { color: #c7a252; text-decoration: none; }
    .error { color: #ff6b6b; font-size: 12px; margin-top: 5px; text-align: center; }
    </style>
    <script>
    function validateForm() {
        var password = document.getElementById('password').value;
        var confirm = document.getElementById('password_confirm').value;
        var errorDiv = document.getElementById('passwordError');
        if (password.length < 8) {
            errorDiv.textContent = '❌ Пароль должен быть не менее 8 символов';
            errorDiv.style.display = 'block';
            return false;
        }
        if (!/[A-Za-z]/.test(password) || !/\\d/.test(password)) {
            errorDiv.textContent = '❌ Пароль должен содержать буквы и цифры';
            errorDiv.style.display = 'block';
            return false;
        }
        if (password !== confirm) {
            errorDiv.textContent = '❌ Пароли не совпадают';
            errorDiv.style.display = 'block';
            return false;
        }
        errorDiv.style.display = 'none';
        return true;
    }
    </script>
    </head>
    <body>
    <div class="box">
    <h2>Регистрация</h2>
    <form method="post" action="/register" onsubmit="return validateForm()">
    <input type="text" name="login" placeholder="Логин" required>
    <input type="email" name="email" placeholder="Email" required>
    <input type="password" name="password" id="password" placeholder="Пароль (мин. 8 символов, буквы+цифры)" required>
    <input type="password" name="password_confirm" id="password_confirm" placeholder="Подтвердите пароль" required>
    <select name="role">
    <option value="unassigned">Неназначен</option>
    <option value="player">Игрок</option>
    <option value="gm">Мастер (GM)</option>
    </select>
    <button type="submit">Зарегистрироваться</button>
    <div id="passwordError" class="error"></div>
    </form>
    <p style="text-align: center; margin-top: 10px;">Уже есть аккаунт? <a href="/login">Войти</a></p>
    </div>
    </body>
    </html>
    """)

@router.post("/register")
async def register(request: Request, login: str = Form(...), email: str = Form(...), password: str = Form(...), password_confirm: str = Form(...), role: str = Form("unassigned")):
    if password != password_confirm:
        return HTMLResponse(content="<h2>Ошибка: Пароли не совпадают</h2><a href='/register'>Назад</a>", status_code=400)
    if len(password) < 8:
        return HTMLResponse(content="<h2>Ошибка: Пароль должен быть не менее 8 символов</h2><a href='/register'>Назад</a>", status_code=400)
    db = SessionLocal()
    if db.query(User).filter_by(login=login).first():
        db.close()
        return HTMLResponse(content="<h2>Ошибка: Логин уже занят</h2><a href='/register'>Назад</a>", status_code=400)
    if db.query(User).filter_by(email=email).first():
        db.close()
        return HTMLResponse(content="<h2>Ошибка: Email уже зарегистрирован</h2><a href='/register'>Назад</a>", status_code=400)
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

@router.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == 'gm':
            return RedirectResponse(url=f"/gm_dashboard/{user.id}", status_code=303)
        else:
            return RedirectResponse(url=f"/player_dashboard/{user.id}/victorian_vampire", status_code=303)
    return RedirectResponse(url="/login", status_code=303)
