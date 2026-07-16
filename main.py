from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import random
import hashlib
import json
import re
import secrets

# -------- НАСТРОЙКА БАЗЫ ДАННЫХ --------
Base = declarative_base()
engine = create_engine('sqlite:///dnd_game.db', connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    login = Column(String, unique=True)
    email = Column(String, unique=True)
    password_hash = Column(String)
    role = Column(String, default='unassigned')
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

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    theme = Column(String)
    background_image = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now)

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    player_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=True)
    setting_id = Column(Integer, ForeignKey('settings.id'))
    
    name = Column(String)
    gender = Column(String)
    class_name = Column(String, default='Воин')
    description = Column(String, default='')
    avatar_url = Column(String, default='')
    
    level = Column(Integer, default=1)
    strength = Column(Integer, default=10)
    dexterity = Column(Integer, default=10)
    constitution = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    wisdom = Column(Integer, default=10)
    charisma = Column(Integer, default=10)
    
    hp = Column(Integer, default=20)
    max_hp = Column(Integer, default=20)
    ac = Column(Integer, default=12)
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    
    is_npc = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    
    user = relationship("User", foreign_keys=[user_id])
    player = relationship("User", foreign_keys=[player_id])
    campaign = relationship("Campaign")
    setting = relationship("Settings")

class InventoryItem(Base):
    __tablename__ = 'inventory_items'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    name = Column(String)
    description = Column(String, default='')
    icon_url = Column(String, default='')
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.datetime.now)
    character = relationship("Character", backref="inventory")

class Skill(Base):
    __tablename__ = 'skills'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    name = Column(String)
    description = Column(String, default='')
    damage_formula = Column(String, default='')
    range = Column(Integer, default=1)
    type = Column(String, default='attack')
    animation_url = Column(String, default='')
    icon_url = Column(String, default='')
    created_at = Column(DateTime, default=datetime.datetime.now)
    character = relationship("Character", backref="skills")

class GameTable(Base):
    __tablename__ = 'game_tables'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    gm_id = Column(Integer, ForeignKey('users.id'))
    setting_id = Column(Integer, ForeignKey('settings.id'))
    link = Column(String, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    gm = relationship("User")
    setting = relationship("Settings")

Base.metadata.create_all(engine)

# -------- НАСТРОЙКА СЕРВЕРА --------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# -------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_table_link():
    return secrets.token_urlsafe(8)

def get_user_by_login_or_email(login_or_email):
    session = Session()
    user = session.query(User).filter(
        (User.login == login_or_email) | (User.email == login_or_email)
    ).first()
    session.close()
    return user

def get_user_by_id(user_id):
    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
    session.close()
    return user

def create_user(login, email, password, role='unassigned'):
    session = Session()
    user = User(login=login, email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id

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

# -------- ИНИЦИАЛИЗАЦИЯ БИБЛИОТЕК (СЕТТИНГОВ) --------
def init_libraries():
    session = Session()
    if session.query(Settings).first():
        session.close()
        return
    
    settings_data = [
        {
            "name": "Викторианский Лондон",
            "theme": "victorian_vampire",
            "description": "Туманный Лондон 1888 года.",
            "background_image": "/static/images/london_street.jpg"
        },
        {
            "name": "Опричники",
            "theme": "oprichniki_witcher",
            "description": "Русь, магия, охота на нечисть.",
            "background_image": "/static/images/campfire.jpg"
        },
        {
            "name": "Кастомный сценарий",
            "theme": "custom",
            "description": "Своя вселенная.",
            "background_image": "/static/images/custom_default.jpg"
        }
    ]
    
    for data in settings_data:
        setting = Settings(**data)
        session.add(setting)
    
    session.commit()
    session.close()
    print("✅ Библиотеки инициализированы!")

init_libraries()

# -------- СТРАНИЦЫ ВХОДА И РЕГИСТРАЦИИ --------
@app.get("/", response_class=HTMLResponse)
async def home():
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Вход в D&D</title>
<style>
body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 320px; }
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
<input type="text" name="login_or_email" placeholder="Логин или Email" required>
<input type="password" name="password" placeholder="Пароль" required>
<button type="submit">Войти</button>
</form>
<p style="text-align: center; margin-top: 10px;">Нет аккаунта? <a href="/register">Зарегистрироваться</a></p>
</div>
</body>
</html>""")

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Регистрация</title>
<style>
body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 340px; }
input, select, button { width: 100%; padding: 10px; margin: 8px 0; border: none; border-radius: 6px; font-size: 14px; }
input, select { background: #3a3a4e; color: #fff; }
button { background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }
a { color: #c7a252; text-decoration: none; }
.error { color: #ff6b6b; font-size: 12px; margin-top: 5px; display: none; text-align: center; }
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
</html>""")

# Функция для красивого вывода ошибок регистрации
def registration_error(message):
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Ошибка регистрации</title>
    <style>
    body {{ background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .box {{ background: #2a2a3e; padding: 40px; border-radius: 12px; width: 400px; text-align: center; }}
    h2 {{ color: #ff6b6b; }}
    a {{ color: #c7a252; text-decoration: none; }}
    </style>
    </head>
    <body>
    <div class="box">
    <h2>❌ Ошибка</h2>
    <p>{message}</p>
    <a href="/register">Вернуться</a>
    </div>
    </body>
    </html>
    """, status_code=400)

@app.post("/register")
async def register(
    login: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    role: str = Form("unassigned")
):
    if len(password) < 8:
        return registration_error("Пароль должен быть не менее 8 символов")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return registration_error("Пароль должен содержать буквы и цифры")
    if password != password_confirm:
        return registration_error("Пароли не совпадают")
    
    session = Session()
    
    existing_login = session.query(User).filter_by(login=login).first()
    if existing_login:
        session.close()
        return registration_error(f"Логин '{login}' уже занят")
    
    existing_email = session.query(User).filter_by(email=email).first()
    if existing_email:
        session.close()
        return registration_error(f"Email '{email}' уже зарегистрирован")
    
    user_id = create_user(login, email, password, role)
    session.close()
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Успешная регистрация</title>
    <style>
    body {{ background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .box {{ background: #2a2a3e; padding: 40px; border-radius: 12px; width: 400px; text-align: center; }}
    h2 {{ color: #4caf50; }}
    a {{ color: #c7a252; text-decoration: none; }}
    </style>
    </head>
    <body>
    <div class="box">
    <h2>✅ Пользователь создан!</h2>
    <p>Логин: {login}</p>
    <p style="color: #aaa; font-size: 14px;">Теперь вы можете войти в систему</p>
    <a href="/login">Перейти ко входу</a>
    </div>
    </body>
    </html>
    """)

@app.post("/login")
async def login(login_or_email: str = Form(...), password: str = Form(...)):
    user = get_user_by_login_or_email(login_or_email)
    if not user or user.password_hash != hash_password(password):
        return HTMLResponse(content="""<!DOCTYPE html>
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
</html>""", status_code=400)
    
    if user.role == 'gm':
        return RedirectResponse(url=f"/gm_dashboard/{user.id}", status_code=303)
    else:
        return RedirectResponse(url=f"/player_dashboard/{user.id}/victorian_vampire", status_code=303)

@app.post("/create_campaign")
async def create_campaign_endpoint(name: str = Form(...), gm_id: int = Form(...), description: str = Form("")):
    campaign = create_campaign(name, gm_id, description)
    return RedirectResponse(url=f"/gm_dashboard/{gm_id}", status_code=303)

# -------- ГЛАВНОЕ МЕНЮ ДЛЯ GM --------
@app.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        return HTMLResponse(content="<h2>Пользователь не найден</h2><a href='/login'>Войти</a>", status_code=404)
    
    campaigns = get_campaigns_for_user(user_id)
    games_count = len(campaigns)
    game_icons = ["fa-dice-d20", "fa-dragon", "fa-hat-wizard", "fa-skull", "fa-scroll"]
    
    session = Session()
    settings = session.query(Settings).all()
    session.close()
    
    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>GM Панель</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #1a1a2e; color: #eee; font-family: 'Segoe UI', Arial, sans-serif; min-height: 100vh; padding-bottom: 70px; }}
.header {{ background: #2a2a3e; padding: 15px 25px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #c7a252; }}
.user-info {{ display: flex; align-items: center; gap: 15px; position: relative; }}
.avatar {{ width: 50px; height: 50px; border-radius: 50%; background: #3a3a4e; border: 2px solid #c7a252; display: flex; align-items: center; justify-content: center; font-size: 24px; color: #c7a252; cursor: pointer; transition: all 0.3s; }}
.avatar:hover {{ transform: scale(1.05); border-color: #f0d5a0; }}
.username {{ font-weight: bold; font-size: 18px; }}
.role-badge {{ background: #c7a252; color: #1a1a2e; padding: 4px 14px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
.user-menu {{ display: none; position: absolute; top: 60px; right: 0; background: #2a2a3e; border-radius: 12px; padding: 8px 0; min-width: 200px; box-shadow: 0 8px 30px rgba(0,0,0,0.8); border: 1px solid #3a3a4e; z-index: 1000; }}
.user-menu a {{ display: block; padding: 10px 20px; color: #eee; text-decoration: none; transition: all 0.2s; border-bottom: 1px solid #3a3a4e; }}
.user-menu a:hover {{ background: #3a3a4e; color: #c9a87c; }}
.user-menu a:last-child {{ border-bottom: none; color: #ff6b6b; }}
.user-menu a:last-child:hover {{ background: #3a3a4e; color: #ff4444; }}
.stats {{ display: flex; gap: 30px; padding: 15px 25px; background: #16162a; border-bottom: 1px solid #2a2a3e; }}
.stat-item {{ display: flex; align-items: center; gap: 8px; color: #aaa; font-size: 14px; }}
.stat-value {{ color: #fff; font-weight: bold; }}
.action-panel {{ display: flex; gap: 15px; padding: 15px 25px; background: #1e1e32; border-bottom: 1px solid #2a2a3e; flex-wrap: wrap; align-items: center; }}
.action-btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 8px; font-family: 'Segoe UI', sans-serif; font-size: 14px; font-weight: bold; cursor: pointer; text-decoration: none; transition: all 0.2s; }}
.action-btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.4); }}
.action-btn.primary {{ background: #c7a252; color: #1a1a2e; }}
.action-btn.secondary {{ background: #3a3a4e; color: #eee; }}
.action-btn.green {{ background: #2a7a3a; color: #fff; }}
.action-btn.table {{ background: #6c7a89; color: #fff; }}
.setting-select {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #3a3a4e; background: #2a2a3e; color: #eee; font-size: 14px; }}
.games-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 20px; padding: 25px; }}
.game-card {{ background: #2a2a3e; border-radius: 16px; padding: 25px 15px; text-align: center; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; border: 1px solid #3a3a4e; }}
.game-card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,0,0,0.5); border-color: #c7a252; }}
.game-icon {{ font-size: 40px; color: #c7a252; margin-bottom: 10px; }}
.game-name {{ font-weight: bold; font-size: 14px; margin-bottom: 5px; }}
.game-status {{ font-size: 12px; color: #888; }}
.create-card {{ border: 2px dashed #3a3a4e; background: transparent; }}
.create-card:hover {{ border-color: #c7a252; background: #1e1e32; }}
.footer-menu {{ background: #2a2a3e; padding: 12px 25px; display: flex; justify-content: space-around; border-top: 1px solid #3a3a4e; position: fixed; bottom: 0; width: 100%; }}
.footer-menu a {{ color: #888; text-decoration: none; display: flex; align-items: center; gap: 8px; font-size: 14px; transition: color 0.2s; }}
.footer-menu a:hover {{ color: #c7a252; }}
</style>
</head>
<body>
<div class="header">
<div class="user-info">
    <div class="avatar" onclick="toggleMenu()">
        <i class="fas fa-user"></i>
    </div>
    <span class="username">{user.login}</span>
    <span class="role-badge"><i class="fas fa-crown"></i> GM</span>
    <div class="user-menu" id="userMenu">
        <a href="/gm_dashboard/{user_id}"><i class="fas fa-home"></i> GM-панель</a>
        <a href="/gm_characters/{user_id}/victorian_vampire"><i class="fas fa-users"></i> Управление персонажами</a>
        <a href="/player_dashboard/{user_id}/victorian_vampire"><i class="fas fa-user"></i> Мои персонажи</a>
        <a href="/login"><i class="fas fa-sign-out-alt"></i> Выйти</a>
    </div>
</div>
<div><a href="#" style="color: #aaa;"><i class="fas fa-cog fa-lg"></i></a></div>
</div>
<div class="stats">
<div class="stat-item"><i class="fas fa-gamepad"></i> <span>Игр: <span class="stat-value">{games_count}</span></span></div>
<div class="stat-item"><i class="fas fa-users"></i> <span>Игроков: <span class="stat-value">0</span></span></div>
<div class="stat-item"><i class="fas fa-hdd"></i> <span>Свободно: <span class="stat-value">2.4 ГБ</span></span></div>
</div>
<div class="action-panel">
<div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
    <select id="gmThemeSelect" class="setting-select" onchange="updateCharactersBtn()">
        <option value="">-- Выберите сеттинг --</option>"""
    for s in settings:
        html_content += f'<option value="{s.theme}">{s.name}</option>'
    html_content += f"""
    </select>
    <a href="/gm_characters/{user_id}/victorian_vampire" class="action-btn primary" id="gmCharactersBtn">
        <i class="fas fa-users"></i> Управление персонажами
    </a>
</div>
<div style="display: flex; align-items: center; gap: 8px;">
    <select id="settingSelect" class="setting-select"><option value="">-- Выберите сеттинг --</option>"""
    for s in settings:
        html_content += f'<option value="{s.theme}">{s.name}</option>'
    html_content += f"""
    </select>
    <button onclick="createCharacter()" class="action-btn green"><i class="fas fa-user-plus"></i> Создать персонажа</button>
</div>
<button onclick="createTable()" class="action-btn table"><i class="fas fa-table"></i> Создать стол</button>
<a href="/gm_dashboard/{user_id}" class="action-btn secondary"><i class="fas fa-plus-circle"></i> Создать кампанию</a>
</div>
<div class="games-grid">
<div class="game-card create-card" onclick="location.href='/gm_dashboard/{user_id}'">
<div class="game-icon"><i class="fas fa-plus-circle"></i></div>
<div class="game-name">Создать игру</div>
<div class="game-status">Новая кампания</div>
</div>"""
    for i, campaign in enumerate(campaigns):
        icon = game_icons[i % len(game_icons)]
        html_content += f"""
<div class="game-card" onclick="alert('Переход в игру: {campaign.name}')">
<div class="game-icon"><i class="fas {icon}"></i></div>
<div class="game-name">{campaign.name}</div>
<div class="game-status">0/6 игроков</div>
</div>"""
    html_content += f"""
</div>
<div class="footer-menu">
<a href="#"><i class="fas fa-home"></i> Главная</a>
<a href="/gm_characters/{user_id}/victorian_vampire"><i class="fas fa-users"></i> Персонажи</a>
<a href="#"><i class="fas fa-chart-bar"></i> Статистика</a>
<a href="/login" style="color: #ff6b6b;"><i class="fas fa-sign-out-alt"></i> Выйти</a>
</div>
<script>
function toggleMenu() {{
    var menu = document.getElementById('userMenu');
    menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}}
document.addEventListener('click', function(e) {{
    var menu = document.getElementById('userMenu');
    var avatar = document.querySelector('.avatar');
    if (menu && avatar) {{
        if (!avatar.contains(e.target) && !menu.contains(e.target)) {{
            menu.style.display = 'none';
        }}
    }}
}});
function updateCharactersBtn() {{
    var select = document.getElementById('gmThemeSelect');
    var btn = document.getElementById('gmCharactersBtn');
    if (select.value) {{
        btn.href = '/gm_characters/{user_id}/' + select.value;
    }} else {{
        btn.href = '/gm_characters/{user_id}/victorian_vampire';
    }}
}}
function createCharacter() {{
    const theme = document.getElementById('settingSelect').value;
    if (!theme) {{
        alert('Пожалуйста, выберите сеттинг для персонажа');
        return;
    }}
    location.href = `/create_character/{user_id}/${{theme}}`;
}}
function createTable() {{
    const name = prompt('Введите название стола:');
    if (!name) return;
    const setting = document.getElementById('settingSelect').value;
    if (!setting) {{
        alert('Сначала выберите сеттинг!');
        return;
    }}
    fetch('/api/table/create', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ name: name, setting_id: parseInt(setting), gm_id: {user_id} }})
    }})
    .then(r => r.json())
    .then(data => {{
        if (data.success) {{
            alert(`✅ Стол "${{name}}" создан!\\nСсылка для игроков:\\n/join/${{data.link}}`);
        }} else {{
            alert('❌ Ошибка: ' + data.message);
        }}
    }})
    .catch(e => alert('❌ Ошибка сети: ' + e.message));
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

# -------- API: СОЗДАНИЕ СТОЛА --------
@app.post("/api/table/create")
async def create_table(data: dict):
    session = Session()
    try:
        link = generate_table_link()
        table = GameTable(
            name=data['name'],
            gm_id=data['gm_id'],
            setting_id=data['setting_id'],
            link=link
        )
        session.add(table)
        session.commit()
        return {"success": True, "link": link}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# -------- СТРАНИЦА ПРИСОЕДИНЕНИЯ К СТОЛУ --------
@app.get("/join/{link}", response_class=HTMLResponse)
async def join_table(link: str, request: Request):
    session = Session()
    table = session.query(GameTable).filter_by(link=link, is_active=True).first()
    if not table:
        session.close()
        return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Стол не найден</title>
<style>
body { background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.box { background: #2a2a3e; padding: 40px; border-radius: 12px; width: 400px; text-align: center; }
h2 { color: #ff6b6b; }
a { color: #c7a252; text-decoration: none; }
</style>
</head>
<body>
<div class="box">
<h2>❌ Стол не найден</h2>
<p>Возможно, он уже закрыт или ссылка неверна.</p>
<a href="/">На главную</a>
</div>
</body>
</html>""", status_code=404)
    
    setting = session.query(Settings).filter_by(id=table.setting_id).first()
    gm = session.query(User).filter_by(id=table.gm_id).first()
    session.close()
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Присоединение к столу</title>
    <style>
    body {{ background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .box {{ background: #2a2a3e; padding: 40px; border-radius: 12px; width: 420px; text-align: center; }}
    h2 {{ color: #c9a87c; }}
    .info {{ color: #aaa; margin: 10px 0; }}
    .btn {{ background: #c7a252; color: #1a1a2e; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; }}
    .btn:hover {{ background: #f0d5a0; }}
    </style>
    </head>
    <body>
    <div class="box">
        <h2>🎲 Присоединение к столу</h2>
        <div class="info"><strong>Стол:</strong> {table.name}</div>
        <div class="info"><strong>Мастер:</strong> {gm.login}</div>
        <div class="info"><strong>Сеттинг:</strong> {setting.name}</div>
        <hr>
        <p style="color: #aaa; font-size: 14px;">Войдите в аккаунт, чтобы выбрать персонажа</p>
        <a href="/login" class="btn">Войти</a>
    </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# -------- GM: УПРАВЛЕНИЕ ПЕРСОНАЖАМИ --------
@app.get("/gm_characters/{user_id}/{theme}", response_class=HTMLResponse)
async def gm_characters(user_id: int, theme: str):
    user = get_user_by_id(user_id)
    if not user or user.role != 'gm':
        return HTMLResponse(content="<h2>Доступ только для GM</h2>", status_code=403)
    
    session = Session()
    setting = session.query(Settings).filter_by(theme=theme).first()
    if not setting:
        session.close()
        return HTMLResponse(content="<h2>Сеттинг не найден</h2>", status_code=404)
    
    characters = session.query(Character).filter_by(setting_id=setting.id).all()
    players = session.query(User).filter_by(role='player').all()
    unassigned = session.query(User).filter_by(role='unassigned').all()
    session.close()
    
    is_victorian = theme == "victorian_vampire"
    css_file = "style.css" if is_victorian else "style_oprichniki.css"
    header_class = "victorian-header" if is_victorian else "rus-header"
    main_class = "victorian-main" if is_victorian else "rus-main"
    
    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>GM: {setting.name}</title>
<link rel="stylesheet" href="/static/css/{css_file}">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
.gm-container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.gm-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
.gm-header h2 {{ color: #c9a87c; font-family: 'Cinzel', serif; }}
.char-table {{ width: 100%; border-collapse: collapse; }}
.char-table th {{ background: #2a1a10; color: #c9a87c; padding: 10px; text-align: left; }}
.char-table td {{ padding: 10px; border-bottom: 1px solid #3a2a1a; vertical-align: middle; }}
.char-table tr:hover {{ background: rgba(201, 168, 124, 0.05); }}
.avatar-cell {{ width: 60px; }}
.avatar-cell img {{ width: 45px; height: 45px; border-radius: 50%; object-fit: cover; border: 2px solid #4a3528; }}
.badge {{ padding: 2px 10px; border-radius: 12px; font-size: 12px; }}
.badge-player {{ background: #2a6a3a; color: #fff; }}
.badge-npc {{ background: #6a2a2a; color: #fff; }}
.badge-unassigned {{ background: #6c7a89; color: #fff; }}
.badge-gm {{ background: #c7a252; color: #1a1a2e; }}
.btn-small {{ padding: 4px 12px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; font-size: 12px; }}
.btn-assign {{ background: #c7a252; color: #1a1a2e; }}
.btn-assign:hover {{ background: #f0d5a0; }}
.btn-create {{ background: #4caf50; color: #fff; }}
.btn-back {{ background: #6c7a89; color: #fff; }}
.btn-delete {{ background: #ff6b6b; color: #fff; }}
.btn-delete:hover {{ background: #ff4444; }}
.btn-unassign {{ background: #6c7a89; color: #fff; }}
.btn-unassign:hover {{ background: #5a6a7a; }}
</style>
</head>
<body>
<header class="{header_class}">
<div class="logo">GM <span>•</span> {setting.name}</div>
<div class="user-info">
    <div class="avatar" onclick="toggleMenu()" style="width: 40px; height: 40px; border-radius: 50%; background: #3a3a4e; border: 2px solid #c7a252; display: flex; align-items: center; justify-content: center; font-size: 18px; color: #c7a252; cursor: pointer;">
        <i class="fas fa-user"></i>
    </div>
    <span>{user.login}</span>
    <div class="user-menu" id="userMenu" style="display: none; position: absolute; top: 60px; right: 20px; background: #2a2a3e; border-radius: 12px; padding: 8px 0; min-width: 200px; box-shadow: 0 8px 30px rgba(0,0,0,0.8); border: 1px solid #3a3a4e; z-index: 1000;">
        <a href="/gm_dashboard/{user_id}" style="display: block; padding: 10px 20px; color: #eee; text-decoration: none; border-bottom: 1px solid #3a3a4e;"><i class="fas fa-home"></i> GM-панель</a>
        <a href="/gm_characters/{user_id}/victorian_vampire" style="display: block; padding: 10px 20px; color: #eee; text-decoration: none; border-bottom: 1px solid #3a3a4e;"><i class="fas fa-users"></i> Персонажи</a>
        <a href="/player_dashboard/{user_id}/victorian_vampire" style="display: block; padding: 10px 20px; color: #eee; text-decoration: none; border-bottom: 1px solid #3a3a4e;"><i class="fas fa-user"></i> Мои персонажи</a>
        <a href="/login" style="display: block; padding: 10px 20px; color: #ff6b6b; text-decoration: none;"><i class="fas fa-sign-out-alt"></i> Выйти</a>
    </div>
</div>
</header>
<div class="{main_class}">
<div class="gm-container">
<div class="gm-header">
<h2><i class="fas fa-users"></i> Управление персонажами</h2>
<div>
<a href="/create_character/{user_id}/{theme}" class="btn-small btn-create" style="padding: 8px 16px;"><i class="fas fa-plus"></i> Создать</a>
<a href="/gm_dashboard/{user_id}" class="btn-small btn-back" style="padding: 8px 16px;"><i class="fas fa-arrow-left"></i> Назад</a>
</div>
</div>
<table class="char-table">
<thead><tr>
<th>Аватар</th>
<th>Имя</th>
<th>Класс</th>
<th>Уровень</th>
<th>Тип</th>
<th>Игрок</th>
<th>Действия</th>
</tr></thead>
<tbody>"""
    for char in characters:
        badge_class = "badge-npc" if char.is_npc else "badge-player"
        badge_text = "NPC" if char.is_npc else "Игрок"
        
        if char.player_id:
            session2 = Session()
            player = session2.query(User).filter_by(id=char.player_id).first()
            if player:
                player_name = player.login
            else:
                player_name = "Не назначен"
            session2.close()
        else:
            player_name = "Не назначен (GM)"
        
        avatar = char.avatar_url if char.avatar_url and char.avatar_url.strip() else 'https://i.pinimg.com/564x/7b/6d/a1/7b6da1d9ab1a8e3c8a7f3d0b8a8e7e0a.jpg'
        html_content += f"""
<tr>
<td class="avatar-cell"><img src="{avatar}" alt="{char.name}"></td>
<td>{char.name}</td>
<td>{char.class_name}</td>
<td>Lv.{char.level}</td>
<td><span class="badge {badge_class}">{badge_text}</span></td>
<td>
<select onchange="assignPlayer({char.id}, this.value)" style="padding: 4px; border-radius: 4px;">
<option value="">Назначить</option>"""
        for p in players:
            selected = "selected" if char.player_id == p.id else ""
            html_content += f'<option value="{p.id}" {selected}>{p.login} (Игрок)</option>'
        for u in unassigned:
            selected = "selected" if char.player_id == u.id else ""
            html_content += f'<option value="{u.id}" {selected}>{u.login} (Неназначен)</option>'
        html_content += f"""
</select>
</td>
<td>
<div style="display: flex; gap: 5px; align-items: center; flex-wrap: wrap;">
    <button onclick="unassignPlayer({char.id})" class="btn-small btn-unassign" title="Отвязать от игрока"><i class="fas fa-times"></i> Отвязать</button>
    <button onclick="deleteCharacter({char.id})" class="btn-small btn-delete"><i class="fas fa-trash"></i></button>
</div>
</td>
</tr>"""
    html_content += """
</tbody></table>
</div>
</div>
<script>
function toggleMenu() {
    var menu = document.getElementById('userMenu');
    menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}
document.addEventListener('click', function(e) {
    var menu = document.getElementById('userMenu');
    var avatar = document.querySelector('.avatar');
    if (menu && avatar) {
        if (!avatar.contains(e.target) && !menu.contains(e.target)) {
            menu.style.display = 'none';
        }
    }
});
function assignPlayer(charId, playerId) {
    if (!playerId) return;
    fetch('/api/character/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: charId, player_id: parseInt(playerId) })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            alert('✅ ' + data.message);
            location.reload();
        } else {
            alert('❌ Ошибка: ' + data.message);
        }
    })
    .catch(e => alert('❌ Ошибка сети: ' + e.message));
}
function unassignPlayer(charId) {
    if (!confirm('Отвязать персонажа от игрока? Он станет свободным (доступен только GM).')) return;
    fetch('/api/character/unassign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: charId })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            alert('✅ ' + data.message);
            location.reload();
        } else {
            alert('❌ Ошибка: ' + data.message);
        }
    })
    .catch(e => alert('❌ Ошибка сети: ' + e.message));
}
function deleteCharacter(charId) {
    if (!confirm('Удалить персонажа?')) return;
    fetch('/api/character/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: charId })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            alert('✅ ' + data.message);
            location.reload();
        } else {
            alert('❌ Ошибка: ' + data.message);
        }
    })
    .catch(e => alert('❌ Ошибка сети: ' + e.message));
}
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

# -------- СТРАНИЦА ИГРОКА --------
@app.get("/player_dashboard/{user_id}/{theme}", response_class=HTMLResponse)
async def player_dashboard_with_theme(user_id: int, theme: str):
    user = get_user_by_id(user_id)
    if not user:
        return HTMLResponse(content="<h2>Пользователь не найден</h2><a href='/login'>Войти</a>", status_code=404)
    
    is_gm = user.role == 'gm'
    
    if not is_gm and user_id != user.id:
        return HTMLResponse(content="<h2>Доступ запрещён</h2><a href='/player_dashboard/{user.id}/victorian_vampire'>Вернуться на свою страницу</a>", status_code=403)
    
    session = Session()
    settings = session.query(Settings).all()
    selected_setting = None
    for s in settings:
        if s.theme == theme:
            selected_setting = s
            break
    if not selected_setting:
        session.close()
        return HTMLResponse(content="<h2>Библиотека не найдена</h2><a href='/player_dashboard/1'>Назад</a>", status_code=404)
    
    characters = session.query(Character).filter_by(setting_id=selected_setting.id, player_id=user_id, is_npc=False).all()
    session.close()
    
    is_victorian = theme == "victorian_vampire"
    css_file = "style.css" if is_victorian else "style_oprichniki.css"
    header_class = "victorian-header" if is_victorian else "rus-header"
    main_class = "victorian-main" if is_victorian else "rus-main"
    panel_class = "companies-panel" if is_victorian else "rus-panel"
    grid_class = "characters-grid" if is_victorian else "rus-grid"
    card_class = "character-card" if is_victorian else "rus-card"
    footer_class = "victorian-footer" if is_victorian else "rus-footer"
    logo_text = f"D&D <span>•</span> {selected_setting.name}" if is_victorian else f"ᛟ {selected_setting.name} ᛟ"
    
    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{selected_setting.name} - D&D</title>
<link rel="stylesheet" href="/static/css/{css_file}">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
.character-card {{
    position: relative;
    cursor: pointer;
    transition: all 0.3s;
}}
.character-card.selected {{
    border: 3px solid #4caf50;
    box-shadow: 0 0 20px rgba(76, 175, 80, 0.3);
    transform: scale(1.02);
}}
.character-card .checkbox {{
    position: absolute;
    top: 10px;
    right: 10px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid #4a3528;
    background: #1a0f0a;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s;
    z-index: 5;
}}
.character-card.selected .checkbox {{
    background: #4caf50;
    border-color: #4caf50;
}}
.character-card.selected .checkbox::after {{
    content: '✓';
    color: #fff;
    font-size: 16px;
    font-weight: bold;
}}
.btn-play {{
    display: none;
    width: 100%;
    max-width: 300px;
    padding: 14px;
    margin: 20px auto;
    background: #4caf50;
    border: none;
    border-radius: 8px;
    color: #fff;
    font-family: 'Cinzel', serif;
    font-size: 18px;
    cursor: pointer;
    transition: all 0.3s;
    letter-spacing: 2px;
}}
.btn-play.show {{
    display: block;
}}
.btn-play:hover {{
    background: #45a049;
    box-shadow: 0 0 30px rgba(76, 175, 80, 0.3);
}}
.gm-badge {{
    background: #c7a252;
    color: #1a1a2e;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: bold;
    margin-left: 10px;
}}
.user-info {{ display: flex; align-items: center; gap: 15px; position: relative; }}
.avatar {{ width: 40px; height: 40px; border-radius: 50%; background: #3a3a4e; border: 2px solid #c7a252; display: flex; align-items: center; justify-content: center; font-size: 18px; color: #c7a252; cursor: pointer; }}
.user-menu {{ display: none; position: absolute; top: 50px; right: 0; background: #2a2a3e; border-radius: 12px; padding: 8px 0; min-width: 200px; box-shadow: 0 8px 30px rgba(0,0,0,0.8); border: 1px solid #3a3a4e; z-index: 1000; }}
.user-menu a {{ display: block; padding: 10px 20px; color: #eee; text-decoration: none; border-bottom: 1px solid #3a3a4e; }}
.user-menu a:hover {{ background: #3a3a4e; color: #c9a87c; }}
.user-menu a:last-child {{ border-bottom: none; color: #ff6b6b; }}
.user-menu a:last-child:hover {{ background: #3a3a4e; color: #ff4444; }}
</style>
</head>
<body>"""
    
    if is_gm:
        html_content += f"""
<div style="position: absolute; top: 80px; left: 20px; z-index: 100;">
    <a href="/gm_dashboard/{user_id}" style="display: inline-block; background: #c7a252; color: #1a1a2e; padding: 8px 16px; border-radius: 8px; text-decoration: none; font-weight: bold;">
        <i class="fas fa-crown"></i> GM-панель
    </a>
    <span class="gm-badge">GM</span>
</div>"""
    
    html_content += f"""
<header class="{header_class}">
<div class="logo">{logo_text}</div>
<div class="user-info">
    <div class="avatar" onclick="toggleMenu()">
        <i class="fas fa-user"></i>
    </div>
    <span>{user.login}</span>
    <div class="user-menu" id="userMenu">
        <a href="/player_dashboard/{user_id}/victorian_vampire"><i class="fas fa-user"></i> Мои персонажи</a>"""
    
    if is_gm:
        html_content += f"""
        <a href="/gm_dashboard/{user_id}"><i class="fas fa-crown"></i> GM-панель</a>"""
    
    html_content += f"""
        <a href="/login"><i class="fas fa-sign-out-alt"></i> Выйти</a>
    </div>
</div>
</header>
<div class="{main_class}">
<div class="{panel_class}">
<div class="panel-title">БИБЛИОТЕКИ</div>"""
    
    for s in settings:
        active = "active" if s.theme == theme else ""
        html_content += f"""
<div class="company-item {active}" onclick="location.href='/player_dashboard/{user_id}/{s.theme}'">
<div class="name">{s.name}</div>
<div class="role">{s.theme.replace('_', ' ').title()}</div>
</div>"""
    
    html_content += f"""
</div>
<div class="{grid_class}" id="charactersGrid">"""
    
    if characters:
        for character in characters:
            avatar = character.avatar_url if character.avatar_url and character.avatar_url.strip() else 'https://i.pinimg.com/564x/7b/6d/a1/7b6da1d9ab1a8e3c8a7f3d0b8a8e7e0a.jpg'
            html_content += f"""
<div class="{card_class}" onclick="selectCharacter({character.id})" data-id="{character.id}">
<div class="checkbox"></div>
<div class="avatar-container"><img src="{avatar}" alt="{character.name}"></div>
<div class="name">{character.name}</div>
<div class="race-class">{character.class_name}</div>
<div class="level">Lv.{character.level}</div>
</div>"""
    else:
        html_content += '<p style="color: #6b4c3b; text-align: center; width: 100%;">Нет персонажей. Обратитесь к Мастеру.</p>'
    
    html_content += f"""
</div>
</div>
<button id="playBtn" class="btn-play" onclick="enterGame()">
    <i class="fas fa-dice-d20"></i> Войти в игру
</button>
<div class="{footer_class}">
<a href="#"><i class="fas fa-comment"></i> Чат</a>
<a href="#"><i class="fas fa-map"></i> Карта</a>
<a href="#"><i class="fas fa-backpack"></i> Инвентарь</a>
<a href="#"><i class="fas fa-hat-wizard"></i> Заклинания</a>
<a href="/gm_dashboard/1"><i class="fas fa-crown"></i> GM</a>
</div>
<script>
function toggleMenu() {{
    var menu = document.getElementById('userMenu');
    menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}}
document.addEventListener('click', function(e) {{
    var menu = document.getElementById('userMenu');
    var avatar = document.querySelector('.avatar');
    if (menu && avatar) {{
        if (!avatar.contains(e.target) && !menu.contains(e.target)) {{
            menu.style.display = 'none';
        }}
    }}
}});
let selectedCharacterId = null;
function selectCharacter(id) {{
    document.querySelectorAll('.{card_class}').forEach(el => el.classList.remove('selected'));
    const card = document.querySelector(`.{card_class}[data-id="${{id}}"]`);
    if (card) {{
        card.classList.add('selected');
        selectedCharacterId = id;
        document.getElementById('playBtn').classList.add('show');
    }}
}}
function enterGame() {{
    if (!selectedCharacterId) {{
        alert('Пожалуйста, выберите персонажа');
        return;
    }}
    alert(`Вход в игру с персонажем ID: ${{selectedCharacterId}}`);
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

# -------- СОЗДАНИЕ ПЕРСОНАЖА (СТРАНИЦА) --------
# ... (здесь весь код create_character_form, он огромный, мы его уже включили в предыдущий main) ...
# Я добавлю его в финальный файл, но в этом сообщении сокращаю для экономии места.
# В финальном файле он будет полностью.

# -------- API ДЛЯ ПЕРСОНАЖЕЙ --------
# ... (здесь весь код API, он у нас уже есть) ...

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