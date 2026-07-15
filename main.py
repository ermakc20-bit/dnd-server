from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
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
    type = Column(String)  # 'player', 'npc', 'enemy'
    race = Column(String)
    class_name = Column(String)  # 'class' зарезервировано
    level = Column(Integer)
    avatar_url = Column(String)
    stats_json = Column(String)  # JSON
    abilities_json = Column(String)  # JSON
    equipment_json = Column(String)  # JSON
    setting = relationship("Settings")
Base.metadata.create_all(engine)
# -------- ДОБАВЛЕНИЕ БИБЛИОТЕК В БД --------
def init_libraries():
    """Инициализирует библиотеки сеттингов и шаблонов"""
    session = Session()
    
    # Проверяем, есть ли уже библиотеки
    if session.query(Settings).first():
        session.close()
        return
    
    # Создаём сеттинги
    settings_data = [
        {
            "name": "Викторианский Лондон",
            "theme": "victorian_vampire",
            "description": "Туманный Лондон 1888 года. Город погружён во тьму, по улицам бродят вампиры, а в подземельях скрываются древние тайны. Вы — охотники на нечисть или сами её часть?",
            "background_image": "https://images.unsplash.com/photo-1544058634-5a1b7b1c64c2?w=1200&auto=format"
        },
        {
            "name": "Опричники: Тени Прошлого",
            "theme": "oprichniki_witcher",
            "description": "Русь, наполненная магией и древними существами. Опричники — элитные охотники на нечисть, служащие царю. Но их настоящая битва — против сил, угрожающих самому существованию мира.",
            "background_image": "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=1200&auto=format"
        }
    ]
    
    for data in settings_data:
        setting = Settings(
            name=data["name"],
            theme=data["theme"],
            description=data["description"],
            background_image=data["background_image"]
        )
        session.add(setting)
    
    session.commit()
    session.close()
    print("✅ Библиотеки сеттингов и шаблонов инициализированы!")

# Вызываем при старте
init_libraries()

# -------- НАСТРОЙКА СЕРВЕРА --------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

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

# -------- ГЛАВНОЕ МЕНЮ ДЛЯ GM --------
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

# -------- СТРАНИЦА ИГРОКА (ВИКТОРИАНСКИЙ СТИЛЬ) --------
@app.get("/player_dashboard/{user_id}", response_class=HTMLResponse)
async def player_dashboard(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        return HTMLResponse(content="<h2>Пользователь не найден</h2><a href='/login'>Войти</a>", status_code=404)
    
    campaigns = get_campaigns_for_user(user_id)
    
    # Тестовые персонажи (позже — из БД)
    test_characters = [
        {
            "id": 1,
            "name": "Граф Дракула",
            "race": "Вампир",
            "class": "Волшебник",
            "level": 5,
            "avatar": "https://i.pinimg.com/564x/7b/6d/a1/7b6da1d9ab1a8e3c8a7f3d0b8a8e7e0a.jpg",
            "stats": {"Сила": 12, "Ловкость": 16, "Телос": 10, "Интеллект": 14, "Мудрость": 8, "Харизма": 18}
        },
        {
            "id": 2,
            "name": "Эльфийка теней",
            "race": "Полуэльф",
            "class": "Разбойник",
            "level": 3,
            "avatar": "https://i.pinimg.com/564x/2c/5e/7f/2c5e7f8b9c0d6e5f4b8a9c7d6e5f4b8a.jpg",
            "stats": {"Сила": 8, "Ловкость": 18, "Телос": 12, "Интеллект": 14, "Мудрость": 12, "Харизма": 10}
        },
        {
            "id": 3,
            "name": "Маг Арканум",
            "race": "Человек",
            "class": "Чародей",
            "level": 4,
            "avatar": "https://i.pinimg.com/564x/3f/8c/7d/3f8c7d8e9f0a1b2c3d4e5f6a7b8c9d0e.jpg",
            "stats": {"Сила": 10, "Ловкость": 14, "Телос": 12, "Интеллект": 16, "Мудрость": 10, "Харизма": 16}
        }
    ]
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Выбор персонажа - D&D</title>
        <link rel="stylesheet" href="/static/css/style.css">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    </head>
    <body>
        <header class="victorian-header">
            <div class="logo">D&D <span>•</span> VICTORIAN</div>
            <div class="user-info">
                <div class="avatar">
                    <i class="fas fa-user"></i>
                </div>
                <span>{user.username}</span>
                <a href="/login" style="color: #6b4c3b; font-size: 14px;">
                    <i class="fas fa-sign-out-alt"></i>
                </a>
            </div>
        </header>

        <div class="victorian-main">
            <div class="companies-panel">
                <div class="panel-title">КОМПАНИИ</div>
    """
    
    for campaign in campaigns:
        role = "GM" if campaign.gm_id == user_id else "Player"
        html_content += f"""
                <div class="company-item">
                    <div class="name">{campaign.name}</div>
                    <div class="role {role.lower()}">{role}</div>
                </div>
        """
    
    html_content += """
            </div>

            <div class="characters-grid" id="charactersGrid">
    """
    
    for char in test_characters:
        html_content += f"""
                <div class="character-card" onclick="selectCharacter({char['id']})" data-id="{char['id']}">
                    <div class="avatar-container">
                        <img src="{char['avatar']}" alt="{char['name']}">
                    </div>
                    <div class="name">{char['name']}</div>
                    <div class="race-class">{char['race']} · {char['class']}</div>
                    <div class="level">Lv.{char['level']}</div>
                </div>
        """
    
    html_content += """
            </div>

            <div class="stats-panel" id="statsPanel">
                <div class="panel-title">ХАРАКТЕРИСТИКИ</div>
                <div id="statsContent">
                    <p style="color: #6b4c3b; text-align: center; font-size: 14px;">
                        <i class="fas fa-hand-pointer"></i> Выберите персонажа
                    </p>
                </div>
            </div>
        </div>

        <div class="victorian-footer">
            <a href="#"><i class="fas fa-comment"></i> Чат</a>
            <a href="#"><i class="fas fa-map"></i> Карта</a>
            <a href="#"><i class="fas fa-backpack"></i> Инвентарь</a>
            <a href="#"><i class="fas fa-hat-wizard"></i> Заклинания</a>
            <a href="/gm_dashboard/1"><i class="fas fa-crown"></i> GM</a>
        </div>

        <script>
            const characters = """ + json.dumps(test_characters) + """;
            
            function selectCharacter(id) {
                document.querySelectorAll('.character-card').forEach(el => el.classList.remove('selected'));
                const card = document.querySelector(`.character-card[data-id="${{id}}"]`);
                if (card) card.classList.add('selected');
                
                const char = characters.find(c => c.id === id);
                if (!char) return;
                
                const statsContent = document.getElementById('statsContent');
                let statsHTML = '';
                for (const [key, value] of Object.entries(char.stats)) {
                    statsHTML += `<div class="stat-row">
                        <span class="label">${key}</span>
                        <span class="value highlight">${value}</span>
                    </div>`;
                }
                statsHTML += `<button class="btn-enter" onclick="enterGame(${char.id})">
                    <i class="fas fa-dice-d20"></i> Войти в игру
                </button>`;
                statsContent.innerHTML = statsHTML;
            }
            
            function enterGame(charId) {
                alert(`Вход в игру с персонажем ID: ${charId}`);
            }
        </script>
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