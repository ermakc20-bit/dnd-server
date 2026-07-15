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

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    theme = Column(String)
    background_image = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.now)

class Template(Base):
    __tablename__ = 'templates'
    id = Column(Integer, primary_key=True)
    setting_id = Column(Integer, ForeignKey('settings.id'))
    name = Column(String)
    type = Column(String)
    race = Column(String)
    class_name = Column(String)
    level = Column(Integer)
    avatar_url = Column(String)
    stats_json = Column(String)
    abilities_json = Column(String)
    equipment_json = Column(String)
    setting = relationship("Settings")

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

Base.metadata.create_all(engine)

# -------- НАСТРОЙКА СЕРВЕРА --------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# -------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------
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
            "description": "Туманный Лондон 1888 года. Город погружён во тьму, по улицам бродят вампиры.",
            "background_image": "https://images.unsplash.com/photo-1544058634-5a1b7b1c64c2?w=1200&auto=format"
        },
        {
            "name": "Опричники: Тени Прошлого",
            "theme": "oprichniki_witcher",
            "description": "Русь, наполненная магией и древними существами. Опричники — элитные охотники на нечисть.",
            "background_image": "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=1200&auto=format"
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

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Регистрация</title>
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
<p style="text-align: center; margin-top: 10px;">Уже есть аккаунт? <a href="/login">Войти</a></p>
</div>
</body>
</html>""")

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...), role: str = Form("player")):
    existing = get_user_by_username(username)
    if existing:
        return HTMLResponse(content="<h2>Ошибка: Имя уже занято</h2><a href='/register'>Назад</a>", status_code=400)
    user = create_user(username, password, role)
    return RedirectResponse(url=f"/dashboard/{user.id}", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Вход в D&D</title>
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
<p style="text-align: center; margin-top: 10px;">Нет аккаунта? <a href="/register">Зарегистрироваться</a></p>
</div>
</body>
</html>""")

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user or user.password_hash != hash_password(password):
        return HTMLResponse(content="<h2>Ошибка: Неверное имя или пароль</h2><a href='/login'>Назад</a>", status_code=400)
    return RedirectResponse(url=f"/dashboard/{user.id}", status_code=303)

@app.get("/dashboard/{user_id}", response_class=HTMLResponse)
async def dashboard(user_id: int):
    campaigns = get_campaigns_for_user(user_id)
    html = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Главное меню</title>
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
<h3>Мои кампании</h3>"""
    if campaigns:
        for c in campaigns:
            html += f"""
<div class="campaign">
<div><strong>{c.name}</strong> - {c.description}</div>
<a href="/game/{c.id}">Войти</a>
</div>"""
    else:
        html += '<p>Нет кампаний</p>'
    html += """</div>
<div style="margin-top: 20px;"><a href="/login" style="color: #ff6b6b;">Выйти</a></div>
</body>
</html>"""
    return HTMLResponse(content=html)

@app.post("/create_campaign")
async def create_campaign_endpoint(name: str = Form(...), gm_id: int = Form(...), description: str = Form("")):
    campaign = create_campaign(name, gm_id, description)
    return RedirectResponse(url=f"/dashboard/{gm_id}", status_code=303)
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
.user-info {{ display: flex; align-items: center; gap: 15px; }}
.avatar {{ width: 50px; height: 50px; border-radius: 50%; background: #3a3a4e; border: 2px solid #c7a252; display: flex; align-items: center; justify-content: center; font-size: 24px; color: #c7a252; }}
.username {{ font-weight: bold; font-size: 18px; }}
.role-badge {{ background: #c7a252; color: #1a1a2e; padding: 4px 14px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
.stats {{ display: flex; gap: 30px; padding: 15px 25px; background: #16162a; border-bottom: 1px solid #2a2a3e; }}
.stat-item {{ display: flex; align-items: center; gap: 8px; color: #aaa; font-size: 14px; }}
.stat-value {{ color: #fff; font-weight: bold; }}
.action-panel {{ display: flex; gap: 15px; padding: 15px 25px; background: #1e1e32; border-bottom: 1px solid #2a2a3e; flex-wrap: wrap; }}
.action-btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 8px; font-family: 'Segoe UI', sans-serif; font-size: 14px; font-weight: bold; cursor: pointer; text-decoration: none; transition: all 0.2s; }}
.action-btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.4); }}
.action-btn.primary {{ background: #c7a252; color: #1a1a2e; }}
.action-btn.secondary {{ background: #3a3a4e; color: #eee; }}
.action-btn.green {{ background: #2a7a3a; color: #fff; }}
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
<div class="avatar"><i class="fas fa-user"></i></div>
<span class="username">{user.username}</span>
<span class="role-badge"><i class="fas fa-crown"></i> GM</span>
</div>
<div><a href="#" style="color: #aaa;"><i class="fas fa-cog fa-lg"></i></a></div>
</div>
<div class="stats">
<div class="stat-item"><i class="fas fa-gamepad"></i> <span>Игр: <span class="stat-value">{games_count}</span></span></div>
<div class="stat-item"><i class="fas fa-users"></i> <span>Игроков: <span class="stat-value">0</span></span></div>
<div class="stat-item"><i class="fas fa-hdd"></i> <span>Свободно: <span class="stat-value">2.4 ГБ</span></span></div>
</div>
<div class="action-panel">
<a href="/gm_characters/{user_id}/victorian_vampire" class="action-btn primary"><i class="fas fa-users"></i> Управление персонажами</a>
<div style="display: flex; align-items: center; gap: 8px;">
<select id="settingSelect" class="setting-select"><option value="">-- Выберите сеттинг --</option>"""
    for s in settings:
        html_content += f'<option value="{s.theme}">{s.name}</option>'
    html_content += f"""
</select>
<button onclick="createCharacter()" class="action-btn green"><i class="fas fa-user-plus"></i> Создать персонажа</button>
</div>
<a href="/dashboard/{user_id}" class="action-btn secondary"><i class="fas fa-plus-circle"></i> Создать кампанию</a>
</div>
<div class="games-grid">
<div class="game-card create-card" onclick="location.href='/dashboard/{user_id}'">
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
function createCharacter() {{
    const theme = document.getElementById('settingSelect').value;
    if (!theme) {{
        alert('Пожалуйста, выберите сеттинг для персонажа');
        return;
    }}
    location.href = `/create_character/{user_id}/${{theme}}`;
}}
</script>
</body>
</html>"""
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
.char-table td {{ padding: 10px; border-bottom: 1px solid #3a2a1a; }}
.char-table tr:hover {{ background: rgba(201, 168, 124, 0.05); }}
.badge {{ padding: 2px 10px; border-radius: 12px; font-size: 12px; }}
.badge-player {{ background: #2a6a3a; color: #fff; }}
.badge-npc {{ background: #6a2a2a; color: #fff; }}
.btn-small {{ padding: 4px 12px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; }}
.btn-assign {{ background: #c7a252; color: #1a1a2e; }}
.btn-assign:hover {{ background: #f0d5a0; }}
.btn-create {{ background: #4caf50; color: #fff; }}
.btn-back {{ background: #6c7a89; color: #fff; }}
</style>
</head>
<body>
<header class="{header_class}">
<div class="logo">GM <span>•</span> {setting.name}</div>
<div class="user-info">
<div class="avatar"><i class="fas fa-user"></i></div>
<span>{user.username}</span>
<a href="/login" style="color: #6b4c3b; font-size: 14px;"><i class="fas fa-sign-out-alt"></i></a>
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
<thead><tr><th>Имя</th><th>Класс</th><th>Уровень</th><th>Тип</th><th>Игрок</th><th>Действие</th></tr></thead>
<tbody>"""
    for char in characters:
        badge_class = "badge-npc" if char.is_npc else "badge-player"
        badge_text = "NPC" if char.is_npc else "Игрок"
        player_name = "Не назначен"
        if char.player_id:
            session = Session()
            player = session.query(User).filter_by(id=char.player_id).first()
            if player:
                player_name = player.username
            session.close()
        html_content += f"""
<tr>
<td>{char.name}</td>
<td>{char.class_name}</td>
<td>Lv.{char.level}</td>
<td><span class="badge {badge_class}">{badge_text}</span></td>
<td>{player_name}</td>
<td>
<select onchange="assignPlayer({char.id}, this.value)" style="padding: 4px; border-radius: 4px;">
<option value="">Назначить</option>"""
        for p in players:
            selected = "selected" if char.player_id == p.id else ""
            html_content += f'<option value="{p.id}" {selected}>{p.username}</option>'
        html_content += f"""
</select>
</td>
</tr>"""
    html_content += """
</tbody></table>
</div>
</div>
<script>
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
    stats_class = "stats-panel" if is_victorian else "rus-stats"
    footer_class = "victorian-footer" if is_victorian else "rus-footer"
    btn_class = "btn-enter" if is_victorian else "btn-rus-enter"
    logo_text = f"D&D <span>•</span> {selected_setting.name}" if is_victorian else f"ᛟ {selected_setting.name} ᛟ"
    
    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{selected_setting.name} - D&D</title>
<link rel="stylesheet" href="/static/css/{css_file}">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
</head>
<body>
<header class="{header_class}">
<div class="logo">{logo_text}</div>
<div class="user-info">
<div class="avatar"><i class="fas fa-user"></i></div>
<span>{user.username}</span>
<a href="/login" style="color: #6b4c3b; font-size: 14px;"><i class="fas fa-sign-out-alt"></i></a>
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
            stats = json.loads(character.stats_json) if character.stats_json else {}
            html_content += f"""
<div class="{card_class}" onclick="selectCharacter({character.id})" data-id="{character.id}">
<div class="avatar-container"><img src="{character.avatar_url}" alt="{character.name}"></div>
<div class="name">{character.name}</div>
<div class="race-class">{character.class_name}</div>
<div class="level">Lv.{character.level}</div>
</div>"""
    else:
        html_content += '<p style="color: #6b4c3b; text-align: center; width: 100%;">Нет персонажей. Обратитесь к Мастеру.</p>'
    html_content += f"""
</div>
<div class="{stats_class}" id="statsPanel">
<div class="panel-title">ХАРАКТЕРИСТИКИ</div>
<div id="statsContent">
<p style="color: #6b4c3b; text-align: center; font-size: 14px;"><i class="fas fa-hand-pointer"></i> Выберите персонажа</p>
</div>
</div>
</div>
<div class="{footer_class}">
<a href="#"><i class="fas fa-comment"></i> Чат</a>
<a href="#"><i class="fas fa-map"></i> Карта</a>
<a href="#"><i class="fas fa-backpack"></i> Инвентарь</a>
<a href="#"><i class="fas fa-hat-wizard"></i> Заклинания</a>
<a href="/gm_dashboard/1"><i class="fas fa-crown"></i> GM</a>
</div>
<script>
const characters = {json.dumps([{"id": c.id, "stats": json.loads(c.stats_json) if c.stats_json else {}} for c in characters])};
function selectCharacter(id) {{
document.querySelectorAll('.{card_class}').forEach(el => el.classList.remove('selected'));
const card = document.querySelector(`.{card_class}[data-id="${{id}}"]`);
if (card) card.classList.add('selected');
const char = characters.find(c => c.id === id);
if (!char) return;
const statsContent = document.getElementById('statsContent');
let statsHTML = '';
for (const [key, value] of Object.entries(char.stats)) {{
statsHTML += `<div class="stat-row"><span class="label">${{key}}</span><span class="value highlight">${{value}}</span></div>`;
}}
statsHTML += `<button class="{btn_class}" onclick="enterGame(${{char.id}})"><i class="fas fa-dice-d20"></i> Войти в игру</button>`;
statsContent.innerHTML = statsHTML;
}}
function enterGame(charId) {{
alert(`Вход в игру с персонажем ID: ${{charId}}`);
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
# -------- СОЗДАНИЕ ПЕРСОНАЖА (СТРАНИЦА) --------
@app.get("/create_character/{user_id}/{setting_theme}", response_class=HTMLResponse)
async def create_character_form(user_id: int, setting_theme: str):
    user = get_user_by_id(user_id)
    if not user:
        return HTMLResponse(content="<h2>Пользователь не найден</h2>", status_code=404)
    if user.role != 'gm':
        return HTMLResponse(content="<h2>⛔ Доступ только для Мастера</h2>", status_code=403)
    
    session = Session()
    setting = session.query(Settings).filter_by(theme=setting_theme).first()
    players = session.query(User).filter_by(role='player').all()
    session.close()
    
    if not setting:
        return HTMLResponse(content="<h2>Сеттинг не найден</h2>", status_code=404)
    
    is_victorian = setting_theme == "victorian_vampire"
    css_file = "style.css" if is_victorian else "style_oprichniki.css"
    header_class = "victorian-header" if is_victorian else "rus-header"
    main_class = "victorian-main" if is_victorian else "rus-main"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Создание персонажа - {setting.name}</title>
        <link rel="stylesheet" href="/static/css/{css_file}">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <style>
            .form-container {{
                background: rgba(10, 8, 8, 0.9);
                padding: 30px;
                border-radius: 16px;
                max-width: 800px;
                margin: 0 auto;
                backdrop-filter: blur(10px);
                border: 1px solid #4a3528;
            }}
            .form-group {{ margin-bottom: 20px; }}
            .form-group label {{ display: block; font-family: 'Cinzel', serif; color: #c9a87c; margin-bottom: 8px; font-size: 14px; letter-spacing: 1px; }}
            .form-group input, .form-group textarea, .form-group select {{ width: 100%; padding: 10px; border: 1px solid #4a3528; border-radius: 8px; background: rgba(20, 15, 12, 0.8); color: #d4c5a9; font-size: 14px; }}
            .form-group textarea {{ min-height: 100px; resize: vertical; }}
            .form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            .btn-submit {{ background: #c7a252; color: #1a1a2e; padding: 14px 30px; border: none; border-radius: 8px; font-family: 'Cinzel', serif; font-size: 16px; cursor: pointer; transition: all 0.3s; width: 100%; font-weight: bold; letter-spacing: 2px; }}
            .btn-submit:hover {{ background: #f0d5a0; box-shadow: 0 0 30px rgba(201, 168, 124, 0.3); }}
            .avatar-upload {{ display: flex; gap: 20px; align-items: center; }}
            .avatar-preview {{ width: 100px; height: 100px; border-radius: 50%; border: 2px solid #4a3528; overflow: hidden; background: #1a0f0a; display: flex; align-items: center; justify-content: center; font-size: 40px; color: #6b4c3b; }}
            .avatar-preview img {{ width: 100%; height: 100%; object-fit: cover; }}
            .inventory-item {{ background: rgba(20, 15, 12, 0.8); padding: 10px; border-radius: 8px; border: 1px solid #4a3528; display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
            .inventory-item input {{ flex: 1; }}
            .skill-item {{ background: rgba(20, 15, 12, 0.8); padding: 15px; border-radius: 8px; border: 1px solid #4a3528; margin-bottom: 8px; }}
            .stat-row {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }}
            .stat-row .stat-item {{ text-align: center; }}
            .stat-row .stat-item label {{ display: block; font-size: 12px; color: #8a7a6a; }}
            .stat-row .stat-item input {{ width: 100%; text-align: center; padding: 5px; }}
            .btn-add {{ background: none; border: 1px dashed #4a3528; color: #c9a87c; padding: 8px; border-radius: 8px; cursor: pointer; width: 100%; margin-top: 8px; }}
            .btn-add:hover {{ border-color: #c9a87c; background: rgba(201, 168, 124, 0.05); }}
            .btn-remove {{ background: none; border: none; color: #ff6b6b; cursor: pointer; padding: 4px 8px; }}
            .btn-remove:hover {{ color: #ff4444; }}
            .result {{ margin-top: 20px; text-align: center; padding: 20px; border-radius: 8px; }}
            .result.success {{ background: rgba(76, 175, 80, 0.15); border: 1px solid #4caf50; }}
            .result.error {{ background: rgba(255, 107, 107, 0.15); border: 1px solid #ff6b6b; }}
        </style>
    </head>
    <body>
        <header class="{header_class}">
            <div class="logo">D&D <span>•</span> {setting.name}</div>
            <div class="user-info">
                <div class="avatar"><i class="fas fa-user"></i></div>
                <span>{user.username}</span>
                <a href="/login" style="color: #6b4c3b; font-size: 14px;"><i class="fas fa-sign-out-alt"></i></a>
            </div>
        </header>
        <div class="{main_class}">
            <div class="form-container">
                <h2 style="text-align: center; color: #c9a87c; font-family: 'Cinzel', serif; margin-bottom: 30px;">
                    <i class="fas fa-user-plus"></i> Создание персонажа
                </h2>
                <form id="characterForm" onsubmit="return false;">
                    <input type="hidden" name="user_id" value="{user_id}">
                    <input type="hidden" name="setting_id" value="{setting.id}">
                    
                    <div class="form-row">
                        <div class="form-group">
                            <label><i class="fas fa-user"></i> Имя</label>
                            <input type="text" name="name" placeholder="Имя персонажа" required>
                        </div>
                        <div class="form-group">
                            <label><i class="fas fa-venus-mars"></i> Пол</label>
                            <select name="gender">
                                <option value="Мужской">Мужской</option>
                                <option value="Женский">Женский</option>
                                <option value="Другой">Другой</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-shield-alt"></i> Класс</label>
                        <input type="text" name="class_name" placeholder="Например: Воин, Маг" value="Воин">
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-image"></i> Аватар</label>
                        <div class="avatar-upload">
                            <div class="avatar-preview" id="avatarPreview"><i class="fas fa-user"></i></div>
                            <div style="flex: 1;">
                                <input type="text" name="avatar_url" placeholder="URL аватара" id="avatarUrlInput" style="width: 100%; margin-bottom: 8px;">
                                <input type="file" accept="image/*" id="avatarFileInput" style="width: 100%;">
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-user-tag"></i> Назначить игроку</label>
                        <select name="player_id">
                            <option value="">-- Без игрока --</option>
    """
    for p in players:
        html_content += f'<option value="{p.id}">{p.username}</option>'
    html_content += """
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-robot"></i> Тип персонажа</label>
                        <div style="display: flex; gap: 20px;">
                            <label><input type="radio" name="is_npc" value="0" checked> Игрок</label>
                            <label><input type="radio" name="is_npc" value="1"> NPC</label>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-align-left"></i> Описание</label>
                        <textarea name="description" placeholder="История, характер, внешность..."></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-chart-bar"></i> Уровень</label>
                        <input type="number" name="level" value="1" min="1" max="20">
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-dice"></i> Характеристики</label>
                        <div class="stat-row">
                            <div class="stat-item"><label>Сила</label><input type="number" name="strength" value="10" min="1" max="30"></div>
                            <div class="stat-item"><label>Ловкость</label><input type="number" name="dexterity" value="10" min="1" max="30"></div>
                            <div class="stat-item"><label>Телосложение</label><input type="number" name="constitution" value="10" min="1" max="30"></div>
                            <div class="stat-item"><label>Интеллект</label><input type="number" name="intelligence" value="10" min="1" max="30"></div>
                            <div class="stat-item"><label>Мудрость</label><input type="number" name="wisdom" value="10" min="1" max="30"></div>
                            <div class="stat-item"><label>Харизма</label><input type="number" name="charisma" value="10" min="1" max="30"></div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-box"></i> Инвентарь</label>
                        <div id="inventoryContainer">
                            <div class="inventory-item">
                                <input type="text" placeholder="Название">
                                <input type="text" placeholder="Описание">
                                <input type="number" placeholder="Кол-во" value="1" style="width: 80px;">
                                <button type="button" class="btn-remove" onclick="removeItem(this, 'inventory')"><i class="fas fa-times"></i></button>
                            </div>
                        </div>
                        <button type="button" class="btn-add" onclick="addItem('inventory')"><i class="fas fa-plus"></i> Добавить предмет</button>
                    </div>
                    
                    <div class="form-group">
                        <label><i class="fas fa-bolt"></i> Скилы</label>
                        <div id="skillsContainer">
                            <div class="skill-item">
                                <input type="text" placeholder="Название" style="width: 100%; margin-bottom: 8px;">
                                <textarea placeholder="Описание" style="width: 100%; min-height: 60px;"></textarea>
                                <button type="button" class="btn-remove" onclick="removeItem(this, 'skill')"><i class="fas fa-times"></i> Удалить</button>
                            </div>
                        </div>
                        <button type="button" class="btn-add" onclick="addItem('skill')"><i class="fas fa-plus"></i> Добавить скил</button>
                    </div>
                    
                    <button type="submit" class="btn-submit"><i class="fas fa-check"></i> Создать</button>
                </form>
                <div id="result" class="result"></div>
            </div>
        </div>
        
       <script>
    // Загрузка аватара по URL
    document.getElementById('avatarUrlInput').addEventListener('input', function() {
        var preview = document.getElementById('avatarPreview');
        var url = this.value.trim();
        if (url) {
            preview.innerHTML = '<img src="' + url + '" alt="Avatar">';
        } else {
            preview.innerHTML = '<i class="fas fa-user"></i>';
        }
    });
    
    // Загрузка аватара через файл
    document.getElementById('avatarFileInput').addEventListener('change', function() {
        var file = this.files[0];
        if (file) {
            var reader = new FileReader();
            reader.onload = function(e) {
                document.getElementById('avatarPreview').innerHTML = '<img src="' + e.target.result + '" alt="Avatar">';
                document.getElementById('avatarUrlInput').value = e.target.result;
            };
            reader.readAsDataURL(file);
        }
    });
    
    // Добавление предметов и скилов
    function addItem(type) {
        var container = document.getElementById(type === 'inventory' ? 'inventoryContainer' : 'skillsContainer');
        if (type === 'inventory') {
            var html = '<div class="inventory-item">' +
                '<input type="text" placeholder="Название">' +
                '<input type="text" placeholder="Описание">' +
                '<input type="number" placeholder="Кол-во" value="1" style="width: 80px;">' +
                '<button type="button" class="btn-remove" onclick="removeItem(this)"><i class="fas fa-times"></i></button>' +
                '</div>';
        } else {
            var html = '<div class="skill-item">' +
                '<input type="text" placeholder="Название" style="width: 100%; margin-bottom: 8px;">' +
                '<textarea placeholder="Описание" style="width: 100%; min-height: 60px;"></textarea>' +
                '<button type="button" class="btn-remove" onclick="removeItem(this)"><i class="fas fa-times"></i> Удалить</button>' +
                '</div>';
        }
        container.insertAdjacentHTML('beforeend', html);
    }
    
    function removeItem(btn) {
        var item = btn.closest('.inventory-item, .skill-item');
        if (item && item.parentElement.children.length > 1) {
            item.remove();
        } else {
            alert('Должен быть хотя бы один элемент');
        }
    }
    
    // Обработчик отправки формы
    document.getElementById('characterForm').addEventListener('submit', function(e) {
        e.preventDefault();
        
        var form = this;
        var formData = new FormData(form);
        
        // Собираем инвентарь
        var inventory = [];
        document.querySelectorAll('#inventoryContainer .inventory-item').forEach(function(item) {
            var inputs = item.querySelectorAll('input');
            inventory.push({
                name: inputs[0].value || 'Безымянный',
                description: inputs[1].value || '',
                quantity: parseInt(inputs[2].value) || 1
            });
        });
        
        // Собираем скилы
        var skills = [];
        document.querySelectorAll('#skillsContainer .skill-item').forEach(function(item) {
            var inputs = item.querySelectorAll('input, textarea');
            skills.push({
                name: inputs[0].value || 'Безымянный',
                description: inputs[1].value || ''
            });
        });
        
        // Формируем JSON
        var data = {
            user_id: parseInt(formData.get('user_id')),
            setting_id: parseInt(formData.get('setting_id')),
            player_id: formData.get('player_id') ? parseInt(formData.get('player_id')) : null,
            name: formData.get('name'),
            gender: formData.get('gender'),
            class_name: formData.get('class_name') || 'Воин',
            avatar_url: formData.get('avatar_url') || '',
            description: formData.get('description') || '',
            level: parseInt(formData.get('level')) || 1,
            strength: parseInt(formData.get('strength')) || 10,
            dexterity: parseInt(formData.get('dexterity')) || 10,
            constitution: parseInt(formData.get('constitution')) || 10,
            intelligence: parseInt(formData.get('intelligence')) || 10,
            wisdom: parseInt(formData.get('wisdom')) || 10,
            charisma: parseInt(formData.get('charisma')) || 10,
            is_npc: parseInt(formData.get('is_npc')) === 1,
            inventory: inventory,
            skills: skills
        };
        
        // Отправляем на сервер
        fetch('/api/character/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(result) {
            var resultDiv = document.getElementById('result');
            if (result.success) {
                resultDiv.className = 'result success';
                resultDiv.innerHTML = '<i class="fas fa-check-circle" style="font-size: 48px;"></i>' +
                    '<p style="margin-top: 10px; font-size: 18px;">' + result.message + '</p>' +
                    '<a href="/gm_characters/' + data.user_id + '/victorian_vampire" style="color: #c9a87c; display: inline-block; margin-top: 15px;">' +
                    '<i class="fas fa-arrow-left"></i> К списку персонажей</a>';
            } else {
                resultDiv.className = 'result error';
                resultDiv.innerHTML = '<i class="fas fa-exclamation-circle" style="font-size: 48px;"></i>' +
                    '<p style="margin-top: 10px;">Ошибка: ' + result.message + '</p>';
            }
        })
        .catch(function(error) {
            document.getElementById('result').className = 'result error';
            document.getElementById('result').innerHTML = '<i class="fas fa-exclamation-circle" style="font-size: 48px;"></i>' +
                '<p style="margin-top: 10px;">Ошибка сети: ' + error.message + '</p>';
        });
    });
</script>
        
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
# -------- API: СОЗДАНИЕ И НАЗНАЧЕНИЕ ПЕРСОНАЖА --------
from pydantic import BaseModel
from typing import List, Optional

class InventoryItemModel(BaseModel):
    name: str
    description: Optional[str] = ""
    quantity: int = 1

class SkillModel(BaseModel):
    name: str
    description: Optional[str] = ""

class CharacterCreateModel(BaseModel):
    user_id: int
    setting_id: int
    player_id: Optional[int] = None
    name: str
    gender: str
    class_name: str = "Воин"
    avatar_url: Optional[str] = ""
    description: Optional[str] = ""
    level: int = 1
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    is_npc: bool = False
    inventory: List[InventoryItemModel] = []
    skills: List[SkillModel] = []

@app.post("/api/character/create")
async def create_character(data: CharacterCreateModel):
    session = Session()
    try:
        character = Character(
            user_id=data.user_id,
            player_id=data.player_id,
            setting_id=data.setting_id,
            name=data.name,
            gender=data.gender,
            class_name=data.class_name,
            avatar_url=data.avatar_url,
            description=data.description,
            level=data.level,
            strength=data.strength,
            dexterity=data.dexterity,
            constitution=data.constitution,
            intelligence=data.intelligence,
            wisdom=data.wisdom,
            charisma=data.charisma,
            is_npc=data.is_npc,
            hp=20 + (data.constitution - 10) * 2,
            max_hp=20 + (data.constitution - 10) * 2,
            ac=12 + (data.dexterity - 10) // 2,
            created_at=datetime.datetime.now()
        )
        session.add(character)
        session.flush()
        for item_data in data.inventory:
            if item_data.name:
                item = InventoryItem(
                    character_id=character.id,
                    name=item_data.name,
                    description=item_data.description,
                    quantity=item_data.quantity
                )
                session.add(item)
        for skill_data in data.skills:
            if skill_data.name:
                skill = Skill(
                    character_id=character.id,
                    name=skill_data.name,
                    description=skill_data.description
                )
                session.add(skill)
        session.commit()
        return {"success": True, "message": f"Персонаж {character.name} создан!", "character_id": character.id}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

class AssignCharacterModel(BaseModel):
    character_id: int
    player_id: int

@app.post("/api/character/assign")
async def assign_character(data: AssignCharacterModel):
    session = Session()
    try:
        char = session.query(Character).filter_by(id=data.character_id).first()
        if not char:
            return {"success": False, "message": "Персонаж не найден"}
        player = session.query(User).filter_by(id=data.player_id).first()
        if not player:
            return {"success": False, "message": "Игрок не найден"}
        char.player_id = data.player_id
        session.commit()
        return {"success": True, "message": f"Персонаж {char.name} назначен игроку {player.username}"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

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