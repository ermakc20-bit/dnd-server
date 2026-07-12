from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import random
import hashlib

# -------- НАСТРОЙКА БАЗЫ ДАННЫХ --------
Base = declarative_base()
engine = create_engine('sqlite:///dnd_game.db', connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    role = Column(String, default='player')
    created_at = Column(DateTime, default=datetime.datetime.now)

class Campaign(Base):
    __tablename__ = 'campaigns'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String, default='')
    gm_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.datetime.now)
    is_active = Column(Boolean, default=True)
    gm = relationship("User")

class Player(Base):
    __tablename__ = 'players'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    hp = Column(Integer, default=20)
    max_hp = Column(Integer, default=20)
    ac = Column(Integer, default=12)
    level = Column(Integer, default=1)
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    user = relationship("User")
    campaign = relationship("Campaign")

Base.metadata.create_all(engine)

# -------- НАСТРОЙКА СЕРВЕРА --------
app = FastAPI()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_by_username(username):
    session = Session()
    user = session.query(User).filter_by(username=username).first()
    session.close()
    return user

def create_user(username, password, role='player'):
    session = Session()
    user = User(username=username, password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    session.close()
    return user

def get_campaigns_for_user(user_id):
    session = Session()
    campaigns = session.query(Campaign).filter_by(gm_id=user_id).all()
    session.close()
    return campaigns

def create_campaign(name, gm_id, description=''):
    session = Session()
    campaign = Campaign(name=name, gm_id=gm_id, description=description)
    session.add(campaign)
    session.commit()
    session.close()
    return campaign

# -------- СТРАНИЦЫ (HTML как строки) --------
@app.get("/", response_class=HTMLResponse)
async def home():
    return RedirectResponse(url="/login")

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Регистрация</title>
        <style>
            body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 300px; }
            input, select, button { width: 100%; padding: 10px; margin: 8px 0; border: none; border-radius: 6px; font-size: 14px; }
            input, select { background: #3a3a4e; color: #fff; }
            button { background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }
            .error { color: #ff6b6b; }
            a { color: #c7a252; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Регистрация</h2>
            <form method="post" action="/register">
                <input type="text" name="username" placeholder="Имя пользователя" required>
                <input type="password" name="password" placeholder="Пароль" required>
                <select name="role">
                    <option value="player">Игрок</option>
                    <option value="gm">Мастер (GM)</option>
                </select>
                <button type="submit">Зарегистрироваться</button>
            </form>
            <p style="text-align: center; margin-top: 10px;">
                Уже есть аккаунт? <a href="/login">Войти</a>
            </p>
        </div>
    </body>
    </html>
    """)

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...), role: str = Form("player")):
    existing = get_user_by_username(username)
    if existing:
        return HTMLResponse(content="<h2>Ошибка: Имя уже занято</h2><a href='/register'>Назад</a>", status_code=400)
    user = create_user(username, password, role)
    return RedirectResponse(url=f"/dashboard/{user.id}", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Вход в D&D</title>
        <style>
            body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 300px; }
            input, button { width: 100%; padding: 10px; margin: 8px 0; border: none; border-radius: 6px; font-size: 14px; }
            input { background: #3a3a4e; color: #fff; }
            button { background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }
            .error { color: #ff6b6b; }
            a { color: #c7a252; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Вход в D&D</h2>
            <form method="post" action="/login">
                <input type="text" name="username" placeholder="Имя пользователя" required>
                <input type="password" name="password" placeholder="Пароль" required>
                <button type="submit">Войти</button>
            </form>
            <p style="text-align: center; margin-top: 10px;">
                Нет аккаунта? <a href="/register">Зарегистрироваться</a>
            </p>
        </div>
    </body>
    </html>
    """)

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user or user.password_hash != hash_password(password):
        return HTMLResponse(content="<h2>Ошибка: Неверное имя или пароль</h2><a href='/login'>Назад</a>", status_code=400)
    return RedirectResponse(url=f"/dashboard/{user.id}", status_code=303)

@app.get("/dashboard/{user_id}", response_class=HTMLResponse)
async def dashboard(user_id: int):
    campaigns = get_campaigns_for_user(user_id)
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Главное меню</title>
        <style>
            body { background: #1a1a2e; color: #eee; font-family: Arial; max-width: 800px; margin: 40px auto; padding: 20px; }
            .card { background: #2a2a3e; padding: 20px; border-radius: 12px; margin-bottom: 20px; }
            input, textarea, button { width: 100%; padding: 10px; margin: 8px 0; border: none; border-radius: 6px; font-size: 14px; }
            input, textarea { background: #3a3a4e; color: #fff; }
            button { background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }
            .campaign { background: #3a3a4e; padding: 15px; border-radius: 8px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
            .campaign a { color: #c7a252; text-decoration: none; font-weight: bold; }
            .flex { display: flex; gap: 10px; align-items: center; }
        </style>
    </head>
    <body>
        <h2>Главное меню</h2>
        <div class="card">
            <h3>Создать новую кампанию</h3>
            <form method="post" action="/create_campaign">
                <input type="hidden" name="gm_id" value=""" + str(user_id) + """>
                <input type="text" name="name" placeholder="Название кампании" required>
                <textarea name="description" placeholder="Описание (необязательно)"></textarea>
                <button type="submit">Создать</button>
            </form>
        </div>
        <div class="card">
            <h3>Мои кампании</h3>
    """
    if campaigns:
        for c in campaigns:
            html += f"""
                <div class="campaign">
                    <div>
                        <strong>{c.name}</strong>
                        <div style="font-size: 12px; color: #aaa;">{c.description}</div>
                    </div>
                    <div class="flex">
                        <a href="/game/{c.id}">Войти</a>
                    </div>
                </div>
            """
    else:
        html += '<p style="color: #aaa;">У вас пока нет кампаний. Создайте первую!</p>'
    
    html += """
        </div>
        <div style="margin-top: 20px;">
            <a href="/login" style="color: #ff6b6b;">Выйти</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/create_campaign")
async def create_campaign_endpoint(name: str = Form(...), gm_id: int = Form(...), description: str = Form("")):
    campaign = create_campaign(name, gm_id, description)
    return RedirectResponse(url=f"/dashboard/{gm_id}", status_code=303)

# -------- ИГРОВОЙ ВЕБСОКЕТ (ДЛЯ ТЕСТА) --------
@app.websocket("/ws/{campaign_id}/{player_name}")
async def game_websocket(websocket: WebSocket, campaign_id: int, player_name: str):
    await websocket.accept()
    await websocket.send_text(f"Добро пожаловать в кампанию {campaign_id}, {player_name}!")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Эхо: {data}")
    except WebSocketDisconnect:
        pass