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

def get_user_by_id(user_id):
    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
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

# -------- СТРАНИЦЫ --------
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
        </style>
    </head>
    <body>
        <h2>Главное меню</h2>
        <div class="card">
            <h3>Создать новую кампанию</h3>
            <form method="post" action="/create_campaign">
                <input type="hidden" name="gm_id" value=\"""" + str(user_id) + """\">
                <input type="text" name="name" placeholder="Название кампании" required>
                <textarea name="description" placeholder="Описание"></textarea>
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
                    <div><strong>{c.name}</strong> - {c.description}</div>
                    <a href="/game/{c.id}">Войти</a>
                </div>
            """
    else:
        html += '<p>Нет кампаний</p>'
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

# -------- НОВОЕ: ГЛАВНОЕ МЕНЮ ДЛЯ GM --------
@app.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        return HTMLResponse(content="<h2>Пользователь не найден</h2><a href='/login'>Войти</a>", status_code=404)
    
    campaigns = get_campaigns_for_user(user_id)
    games_count = len(campaigns)
    game_icons = ["fa-dice-d20", "fa-dragon", "fa-hat-wizard", "fa-skull", "fa-scroll"]
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>GM Панель</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                background: #1a1a2e; 
                color: #eee; 
                font-family: 'Segoe UI', Arial, sans-serif;
                min-height: 100vh;
                padding-bottom: 70px;
            }}
            .header {{
                background: #2a2a3e;
                padding: 15px 25px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 2px solid #c7a252;
            }}
            .user-info {{
                display: flex;
                align-items: center;
                gap: 15px;
            }}
            .avatar {{
                width: 50px;
                height: 50px;
                border-radius: 50%;
                background: #3a3a4e;
                border: 2px solid #c7a252;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                color: #c7a252;
            }}
            .username {{
                font-weight: bold;
                font-size: 18px;
            }}
            .role-badge {{
                background: #c7a252;
                color: #1a1a2e;
                padding: 4px 14px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
            }}
            .stats {{
                display: flex;
                gap: 30px;
                padding: 15px 25px;
                background: #16162a;
                border-bottom: 1px solid #2a2a3e;
            }}
            .stat-item {{
                display: flex;
                align-items: center;
                gap: 8px;
                color: #aaa;
                font-size: 14px;
            }}
            .stat-value {{
                color: #fff;
                font-weight: bold;
            }}
            .games-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 20px;
                padding: 25px;
            }}
            .game-card {{
                background: #2a2a3e;
                border-radius: 16px;
                padding: 25px 15px;
                text-align: center;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
                border: 1px solid #3a3a4e;
            }}
            .game-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.5);
                border-color: #c7a252;
            }}
            .game-icon {{
                font-size: 40px;
                color: #c7a252;
                margin-bottom: 10px;
            }}
            .game-name {{
                font-weight: bold;
                font-size: 14px;
                margin-bottom: 5px;
            }}
            .game-status {{
                font-size: 12px;
                color: #888;
            }}
            .create-card {{
                border: 2px dashed #3a3a4e;
                background: transparent;
            }}
            .create-card:hover {{
                border-color: #c7a252;
                background: #1e1e32;
            }}
            .footer-menu {{
                background: #2a2a3e;
                padding: 12px 25px;
                display: flex;
                justify-content: space-around;
                border-top: 1px solid #3a3a4e;
                position: fixed;
                bottom: 0;
                width: 100%;
            }}
            .footer-menu a {{
                color: #888;
                text-decoration: none;
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 14px;
                transition: color 0.2s;
            }}
            .footer-menu a:hover {{
                color: #c7a252;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="user-info">
                <div class="avatar">
                    <i class="fas fa-user"></i>
                </div>
                <span class="username">{user.username}</span>
                <span class="role-badge"><i class="fas fa-crown"></i> GM</span>
            </div>
            <div>
                <a href="#" style="color: #aaa;">
                    <i class="fas fa-cog fa-lg"></i>
                </a>
            </div>
        </div>

        <div class="stats">
            <div class="stat-item">
                <i class="fas fa-gamepad"></i>
                <span>Игр: <span class="stat-value">{games_count}</span></span>
            </div>
            <div class="stat-item">
                <i class="fas fa-users"></i>
                <span>Игроков: <span class="stat-value">0</span></span>
            </div>
            <div class="stat-item">
                <i class="fas fa-hdd"></i>
                <span>Свободно: <span class="stat-value">2.4 ГБ</span></span>
            </div>
        </div>

        <div class="games-grid">
            <div class="game-card create-card" onclick="alert('Форма создания игры будет здесь!')">
                <div class="game-icon">
                    <i class="fas fa-plus-circle"></i>
                </div>
                <div class="game-name">Создать игру</div>
                <div class="game-status">Новая кампания</div>
            </div>
    """
    
    for i, campaign in enumerate(campaigns):
        icon = game_icons[i % len(game_icons)]
        html_content += f"""
            <div class="game-card" onclick="alert('Переход в игру: {campaign.name}')">
                <div class="game-icon">
                    <i class="fas {icon}"></i>
                </div>
                <div class="game-name">{campaign.name}</div>
                <div class="game-status">0/6 игроков</div>
            </div>
        """
    
    html_content += """
        </div>
        <div class="footer-menu">
            <a href="#">
                <i class="fas fa-home"></i> Главная
            </a>
            <a href="#">
                <i class="fas fa-users"></i> Персонажи
            </a>
            <a href="#">
                <i class="fas fa-chart-bar"></i> Статистика
            </a>
            <a href="/login" style="color: #ff6b6b;">
                <i class="fas fa-sign-out-alt"></i> Выйти
            </a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# -------- ИГРОВОЙ ВЕБСОКЕТ --------
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