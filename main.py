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
import secrets
import re

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

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    theme = Column(String)
    background_image = Column(String)

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

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    player_id = Column(Integer, ForeignKey('users.id'), nullable=True)
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
    setting = relationship("Settings")

Base.metadata.create_all(engine)

# -------- НАСТРОЙКА СЕРВЕРА --------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# -------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

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

def get_current_user(request):
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None
    try:
        from itsdangerous import URLSafeTimedSerializer
        serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
        data = serializer.loads(session_cookie, max_age=60 * 60 * 24 * 7)
        user_id = data.get("user_id")
        if user_id:
            return get_user_by_id(user_id)
    except:
        return None
    return None

def generate_table_link():
    return secrets.token_urlsafe(8)

# -------- ИНИЦИАЛИЗАЦИЯ БИБЛИОТЕК --------
def init_libraries():
    session = Session()
    if session.query(Settings).first():
        session.close()
        return
    settings_data = [
        {"name": "Викторианский Лондон", "theme": "victorian_vampire", "description": "Туманный Лондон 1888 года.", "background_image": "/static/images/london_street.jpg"},
        {"name": "Опричники", "theme": "oprichniki_witcher", "description": "Русь, магия, охота на нечисть.", "background_image": "/static/images/campfire.jpg"},
        {"name": "Кастомный сценарий", "theme": "custom", "description": "Своя вселенная.", "background_image": "/static/images/custom_default.jpg"}
    ]
    for data in settings_data:
        setting = Settings(**data)
        session.add(setting)
    session.commit()
    session.close()
    print("✅ Библиотеки инициализированы!")

init_libraries()

# -------- СТРАНИЦЫ ВХОДА И РЕГИСТРАЦИИ --------
@app.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == 'gm':
            return RedirectResponse(url=f"/gm_dashboard/{user.id}", status_code=303)
        else:
            return RedirectResponse(url=f"/player_dashboard/{user.id}/victorian_vampire", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

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

@app.post("/login")
async def login(request: Request, login_or_email: str = Form(...), password: str = Form(...)):
    from itsdangerous import URLSafeTimedSerializer
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
    serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
    session_token = serializer.dumps({"user_id": user.id})
    response = RedirectResponse(url=f"/gm_dashboard/{user.id}" if user.role == 'gm' else f"/player_dashboard/{user.id}/victorian_vampire", status_code=303)
    response.set_cookie(key="session", value=session_token, httponly=True, max_age=604800)
    return response

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
</style>
<script>
function validateForm() {
    var password = document.getElementById('password').value;
    var confirm = document.getElementById('password_confirm').value;
    var errorDiv = document.getElementById('passwordError');
    if (password.length < 8) { errorDiv.textContent = '❌ Пароль должен быть не менее 8 символов'; errorDiv.style.display = 'block'; return false; }
    if (!/[A-Za-z]/.test(password) || !/\\d/.test(password)) { errorDiv.textContent = '❌ Пароль должен содержать буквы и цифры'; errorDiv.style.display = 'block'; return false; }
    if (password !== confirm) { errorDiv.textContent = '❌ Пароли не совпадают'; errorDiv.style.display = 'block'; return false; }
    errorDiv.style.display = 'none'; return true;
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
<div id="passwordError" style="color: #ff6b6b; font-size: 12px; margin-top: 5px; display: none; text-align: center;"></div>
</form>
<p style="text-align: center; margin-top: 10px;">Уже есть аккаунт? <a href="/login">Войти</a></p>
</div>
</body>
</html>""")

@app.post("/register")
async def register(request: Request, login: str = Form(...), email: str = Form(...), password: str = Form(...), password_confirm: str = Form(...), role: str = Form("unassigned")):
    from itsdangerous import URLSafeTimedSerializer
    if password != password_confirm:
        return HTMLResponse(content="<h2>Ошибка: Пароли не совпадают</h2><a href='/register'>Назад</a>", status_code=400)
    if len(password) < 8:
        return HTMLResponse(content="<h2>Ошибка: Пароль должен быть не менее 8 символов</h2><a href='/register'>Назад</a>", status_code=400)
    session = Session()
    if session.query(User).filter_by(login=login).first():
        session.close()
        return HTMLResponse(content="<h2>Ошибка: Логин уже занят</h2><a href='/register'>Назад</a>", status_code=400)
    if session.query(User).filter_by(email=email).first():
        session.close()
        return HTMLResponse(content="<h2>Ошибка: Email уже зарегистрирован</h2><a href='/register'>Назад</a>", status_code=400)
    session.close()
    user_id = create_user(login, email, password, role)
    serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
    session_token = serializer.dumps({"user_id": user_id})
    response = RedirectResponse(url=f"/gm_dashboard/{user_id}" if role == 'gm' else f"/player_dashboard/{user_id}/victorian_vampire", status_code=303)
    response.set_cookie(key="session", value=session_token, httponly=True, max_age=604800)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response

# -------- GM-ПАНЕЛЬ --------
@app.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user.id != user_id or user.role != 'gm':
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    settings = session.query(Settings).all()
    session.close()
    settings_options = ""
    for s in settings:
        settings_options += f'<option value="{s.id}">{s.name}</option>'
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>GM Панель</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #1a1a2e; color: #eee; font-family: Arial, sans-serif; min-height: 100vh; }}
    .header {{ background: #2a2a3e; padding: 15px 25px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #c7a252; }}
    .user-info {{ display: flex; align-items: center; gap: 15px; }}
    .avatar {{ width: 40px; height: 40px; border-radius: 50%; background: #c7a252; color: #1a1a2e; display: flex; align-items: center; justify-content: center; font-weight: bold; }}
    .username {{ font-weight: bold; font-size: 18px; }}
    .role-badge {{ background: #c7a252; color: #1a1a2e; padding: 2px 10px; border-radius: 12px; font-size: 12px; }}
    .action-panel {{ padding: 20px; display: flex; gap: 15px; flex-wrap: wrap; }}
    .btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; text-decoration: none; transition: all 0.2s; }}
    .btn-primary {{ background: #c7a252; color: #1a1a2e; }}
    .btn-primary:hover {{ background: #f0d5a0; }}
    .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); }}
    .modal-content {{ background: #2a2a3e; margin: 10% auto; padding: 30px; width: 400px; border-radius: 12px; }}
    .close {{ float: right; font-size: 28px; cursor: pointer; color: #aaa; }}
    .close:hover {{ color: #fff; }}
    input, select {{ width: 100%; padding: 10px; margin: 10px 0; border: none; border-radius: 6px; font-size: 14px; background: #3a3a4e; color: #fff; }}
    .logout-btn {{ color: #ff6b6b; text-decoration: none; }}
    </style>
    </head>
    <body>
    <div class="header">
    <div class="user-info">
    <div class="avatar">{user.login[0].upper()}</div>
    <span class="username">{user.login}</span>
    <span class="role-badge">GM</span>
    </div>
    <a href="/logout" class="logout-btn">Выйти</a>
    </div>
    <div class="action-panel">
    <button onclick="openModal()" class="btn btn-primary"><i class="fas fa-plus"></i> Создать игру</button>
    </div>
    <div id="createModal" class="modal">
    <div class="modal-content">
    <span class="close" onclick="closeModal()">&times;</span>
    <h3>Новая игра</h3>
    <input type="text" id="gameName" placeholder="Название игры">
    <select id="gameSetting">
    <option value="">-- Выберите сеттинг --</option>
    {settings_options}
    </select>
    <button onclick="createGame()" class="btn btn-primary" style="width: 100%;">Создать</button>
    </div>
    </div>
    <script>
    function openModal() {{ document.getElementById('createModal').style.display = 'block'; }}
    function closeModal() {{ document.getElementById('createModal').style.display = 'none'; }}
    function createGame() {{
        var name = document.getElementById('gameName').value.trim();
        var settingId = document.getElementById('gameSetting').value;
        if (!name) {{ alert('Введите название'); return; }}
        if (!settingId) {{ alert('Выберите сеттинг'); return; }}
        fetch('/api/table/create', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ name: name, setting_id: parseInt(settingId), gm_id: {user.id} }})
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                alert('✅ Игра создана! Ссылка: /join/' + data.link);
                closeModal();
                location.reload();
            }} else {{
                alert('❌ Ошибка: ' + data.message);
            }}
        }})
        .catch(e => alert('Ошибка: ' + e.message));
    }}
    </script>
    </body>
    </html>
    """)

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

# -------- ПРИСОЕДИНЕНИЕ К СТОЛУ --------
@app.get("/join/{link}", response_class=HTMLResponse)
async def join_table(request: Request, link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/join/{link}", status_code=303)
    session = Session()
    table = session.query(GameTable).filter_by(link=link, is_active=True).first()
    if not table:
        session.close()
        return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
    setting = session.query(Settings).filter_by(id=table.setting_id).first()
    gm = session.query(User).filter_by(id=table.gm_id).first()
    characters = session.query(Character).filter_by(setting_id=table.setting_id, player_id=user.id, is_npc=False).all()
    session.close()
    characters_html = ""
    for char in characters:
        avatar = char.avatar_url if char.avatar_url else '/static/images/default_avatar.png'
        characters_html += f'''
        <div class="char-card" onclick="selectCharacter({char.id})" data-charid="{char.id}">
            <img src="{avatar}" alt="{char.name}">
            <div class="name">{char.name}</div>
            <div class="class">Lv.{char.level} {char.class_name}</div>
        </div>
        '''
    if characters:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><title>Присоединение к столу</title>
        <style>
        body {{ background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }}
        .box {{ background: #2a2a3e; padding: 40px; border-radius: 12px; width: 500px; text-align: center; }}
        h2 {{ color: #c9a87c; }}
        .info {{ color: #aaa; margin: 10px 0; }}
        .char-grid {{ display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; margin: 20px 0; }}
        .char-card {{ background: #1a1a2e; border-radius: 8px; padding: 15px; width: 120px; cursor: pointer; border: 2px solid transparent; transition: all 0.3s; }}
        .char-card:hover {{ border-color: #c7a252; transform: scale(1.05); }}
        .char-card img {{ width: 80px; height: 80px; border-radius: 50%; object-fit: cover; }}
        .char-card .name {{ font-weight: bold; margin-top: 8px; }}
        .btn {{ background: #c7a252; color: #1a1a2e; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; margin-top: 20px; }}
        .btn:hover {{ background: #f0d5a0; }}
        .btn-secondary {{ background: #6c7a89; color: #fff; }}
        .btn-secondary:hover {{ background: #5a6a7a; }}
        </style>
        </head>
        <body>
        <div class="box">
        <h2>🎲 Присоединение к столу</h2>
        <div class="info"><strong>Стол:</strong> {table.name}</div>
        <div class="info"><strong>Мастер:</strong> {gm.login}</div>
        <div class="info"><strong>Сеттинг:</strong> {setting.name}</div>
        <hr>
        <p>Выберите персонажа:</p>
        <div class="char-grid">{characters_html}</div>
        <button id="joinBtn" class="btn" onclick="joinGame()" disabled>Войти в игру</button>
        <a href="/player_dashboard/{user.id}/{setting.theme}" class="btn btn-secondary">Создать персонажа</a>
        <script>
        let selectedCharId = null;
        function selectCharacter(id) {{
            document.querySelectorAll('.char-card').forEach(el => el.style.borderColor = 'transparent');
            const card = document.querySelector(`.char-card[data-charid="${{id}}"]`);
            if (card) {{
                card.style.borderColor = '#4caf50';
                selectedCharId = id;
                document.getElementById('joinBtn').disabled = false;
            }}
        }}
        function joinGame() {{
            if (!selectedCharId) return;
            alert('✅ Вход в игру с персонажем ID: ' + selectedCharId + '\\n(Здесь будет игровая комната)');
        }}
        </script>
        </body>
        </html>
        """)
    else:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"><title>Присоединение к столу</title>
        <style>
        body {{ background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }}
        .box {{ background: #2a2a3e; padding: 40px; border-radius: 12px; width: 500px; text-align: center; }}
        h2 {{ color: #c9a87c; }}
        .info {{ color: #aaa; margin: 10px 0; }}
        .error-text {{ color: #ff6b6b; }}
        .btn {{ background: #c7a252; color: #1a1a2e; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; margin-top: 20px; }}
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
        <p class="error-text">У вас нет персонажей в этом сеттинге.</p>
        <a href="/player_dashboard/{user.id}/{setting.theme}" class="btn">Создать персонажа</a>
        </div>
        </body>
        </html>
        """)

# -------- ИГРОВАЯ КОМНАТА --------
@app.get("/game/{table_link}", response_class=HTMLResponse)
async def game_room(request: Request, table_link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    table = session.query(GameTable).filter_by(link=table_link, is_active=True).first()
    if not table:
        session.close()
        return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
    character = session.query(Character).filter_by(player_id=user.id, setting_id=table.setting_id).first()
    session.close()
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Игровая комната</title>
    <style>
    body {{ background: #1a1a2e; color: #eee; font-family: Arial; min-height: 100vh; margin: 0; padding: 20px; }}
    .game-container {{ max-width: 1200px; margin: 0 auto; }}
    .game-header {{ display: flex; justify-content: space-between; align-items: center; padding: 15px 25px; border-bottom: 2px solid #c7a252; }}
    .game-body {{ display: flex; gap: 20px; margin-top: 20px; }}
    .game-map {{ flex: 3; }}
    .game-chat {{ flex: 1; min-width: 250px; }}
    canvas {{ border: 2px solid #4a3528; background: #1a1a2e; width: 100%; }}
    #chatMessages {{ height: 300px; overflow-y: auto; border: 1px solid #4a3528; padding: 10px; background: #0a0a1a; }}
    input {{ width: 100%; padding: 8px; margin-top: 8px; border: none; border-radius: 4px; background: #3a3a4e; color: #fff; }}
    button {{ width: 100%; padding: 8px; margin-top: 5px; border: none; border-radius: 4px; background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }}
    .logout-btn {{ color: #ff6b6b; text-decoration: none; }}
    </style>
    </head>
    <body>
    <div class="game-container">
    <div class="game-header">
    <h2>🎲 {table.name}</h2>
    <div>Игрок: {user.login} | Персонаж: {character.name if character else 'Не выбран'}</div>
    <a href="/logout" class="logout-btn">Выйти</a>
    </div>
    <div class="game-body">
    <div class="game-map"><canvas id="gameCanvas" width="800" height="600"></canvas></div>
    <div class="game-chat">
    <div id="chatMessages"></div>
    <input type="text" id="chatInput" placeholder="Введите сообщение...">
    <button onclick="sendMessage()">Отправить</button>
    </div>
    </div>
    </div>
    <script>
    function sendMessage() {{
        const input = document.getElementById('chatInput');
        const messages = document.getElementById('chatMessages');
        if (input.value.trim()) {{
            messages.innerHTML += `<div><strong>Вы:</strong> ${{input.value}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
        }}
    }}
    </script>
    </body>
    </html>
    """)
# -------- ИГРОВАЯ КОМНАТА (НОВЫЙ СТОЛ) --------
@app.get("/game/{table_link}", response_class=HTMLResponse)
async def game_room(request: Request, table_link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    table = session.query(GameTable).filter_by(link=table_link, is_active=True).first()
    if not table:
        session.close()
        return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
    
    # Пока берём первого попавшегося персонажа игрока в этом сеттинге
    character = session.query(Character).filter_by(player_id=user.id, setting_id=table.setting_id).first()
    
    # Получаем всех персонажей (токены) для этого стола
    tokens = session.query(Character).filter_by(setting_id=table.setting_id, is_npc=False).all()
    session.close()
    
    # Формируем HTML для токенов
    tokens_html = ""
    for t in tokens:
        avatar = t.avatar_url if t.avatar_url else '/static/images/default_avatar.png'
        tokens_html += f'''
        <div class="token" id="token-{t.id}" style="position: absolute; left: {t.x * 60 + 20}px; top: {t.y * 60 + 20}px; cursor: grab; user-select: none;" onmousedown="startDrag(event, {t.id})">
            <img src="{avatar}" style="width: 50px; height: 50px; border-radius: 50%; border: 2px solid #c7a252; box-shadow: 0 0 10px rgba(0,0,0,0.5);" title="{t.name}">
            <div style="text-align: center; font-size: 10px; color: #c9a87c; margin-top: -5px;">{t.name}</div>
        </div>
        '''
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Игровая комната</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ background: #1a1a2e; color: #eee; font-family: 'Segoe UI', Arial, sans-serif; height: 100vh; overflow: hidden; }}
            .game-container {{ display: flex; flex-direction: column; height: 100vh; }}
            .header {{ background: #2a2a3e; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #c7a252; flex-shrink: 0; }}
            .header h2 {{ color: #c9a87c; font-size: 20px; }}
            .header .info {{ font-size: 14px; color: #aaa; }}
            .header .info span {{ color: #c9a87c; }}
            .body {{ display: flex; flex: 1; overflow: hidden; }}
            .map-container {{ flex: 1; position: relative; background: #0a0a1a; overflow: auto; }}
            #mapCanvas {{ display: block; width: 100%; height: 100%; background: #1a1a2e; }}
            .tokens-layer {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; }}
            .tokens-layer .token {{ pointer-events: auto; position: absolute; }}
            .chat-container {{ width: 280px; background: #16162a; border-left: 1px solid #2a2a3e; display: flex; flex-direction: column; flex-shrink: 0; }}
            .chat-header {{ padding: 10px; border-bottom: 1px solid #2a2a3e; font-weight: bold; color: #c9a87c; text-align: center; }}
            #chatMessages {{ flex: 1; overflow-y: auto; padding: 10px; font-size: 14px; }}
            #chatMessages div {{ margin-bottom: 5px; padding: 4px 8px; background: #1a1a2e; border-radius: 4px; }}
            #chatMessages .system {{ color: #6c7a89; font-style: italic; }}
            #chatMessages .player {{ color: #c9a87c; }}
            .chat-input {{ display: flex; padding: 10px; border-top: 1px solid #2a2a3e; flex-shrink: 0; }}
            #chatInput {{ flex: 1; padding: 8px; border: none; border-radius: 4px; background: #2a2a3e; color: #fff; }}
            #chatSendBtn {{ padding: 8px 16px; margin-left: 8px; border: none; border-radius: 4px; background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }}
            #chatSendBtn:hover {{ background: #f0d5a0; }}
            .logout-btn {{ color: #ff6b6b; text-decoration: none; font-size: 14px; }}
            .logout-btn:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="game-container">
            <div class="header">
                <h2>🎲 {table.name}</h2>
                <div class="info">
                    Игрок: <span>{user.login}</span> | Персонаж: <span>{character.name if character else 'Не выбран'}</span>
                </div>
                <a href="/logout" class="logout-btn">Выйти</a>
            </div>
            <div class="body">
                <div class="map-container" id="mapContainer">
                    <canvas id="mapCanvas"></canvas>
                    <div class="tokens-layer" id="tokensLayer">
                        {tokens_html}
                    </div>
                </div>
                <div class="chat-container">
                    <div class="chat-header">💬 Чат</div>
                    <div id="chatMessages"></div>
                    <div class="chat-input">
                        <input type="text" id="chatInput" placeholder="Введите сообщение...">
                        <button id="chatSendBtn">Отправить</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            // -------- КАНВАС (КАРТА) --------
            const canvas = document.getElementById('mapCanvas');
            const ctx = canvas.getContext('2d');
            const container = document.getElementById('mapContainer');
            
            function resizeCanvas() {{
                canvas.width = container.clientWidth;
                canvas.height = container.clientHeight;
                drawGrid();
            }}
            
            function drawGrid() {{
                const w = canvas.width, h = canvas.height;
                const cellSize = 60;
                ctx.clearRect(0, 0, w, h);
                ctx.strokeStyle = '#2a2a3e';
                ctx.lineWidth = 1;
                for (let x = 0; x <= w; x += cellSize) {{
                    ctx.beginPath();
                    ctx.moveTo(x, 0);
                    ctx.lineTo(x, h);
                    ctx.stroke();
                }}
                for (let y = 0; y <= h; y += cellSize) {{
                    ctx.beginPath();
                    ctx.moveTo(0, y);
                    ctx.lineTo(w, y);
                    ctx.stroke();
                }}
                // Координаты
                ctx.fillStyle = '#4a4a5e';
                ctx.font = '12px Arial';
                ctx.textAlign = 'center';
                for (let x = 0; x < w; x += cellSize) {{
                    ctx.fillText(x/cellSize, x + 30, 15);
                }}
                for (let y = 0; y < h; y += cellSize) {{
                    ctx.fillText(y/cellSize, 15, y + 30);
                }}
            }}
            
            window.addEventListener('resize', resizeCanvas);
            resizeCanvas();

            // -------- ПЕРЕТАСКИВАНИЕ ТОКЕНОВ --------
            let dragData = null;

            function startDrag(e, tokenId) {{
                e.preventDefault();
                const token = document.getElementById(`token-${{tokenId}}`);
                if (!token) return;
                
                const rect = token.getBoundingClientRect();
                const offsetX = e.clientX - rect.left;
                const offsetY = e.clientY - rect.top;
                
                dragData = {{
                    tokenId: tokenId,
                    offsetX: offsetX,
                    offsetY: offsetY,
                    startX: rect.left,
                    startY: rect.top
                }};
                
                document.addEventListener('mousemove', onDrag);
                document.addEventListener('mouseup', stopDrag);
                token.style.cursor = 'grabbing';
            }}
            
            function onDrag(e) {{
                if (!dragData) return;
                const token = document.getElementById(`token-${{dragData.tokenId}}`);
                if (!token) return;
                
                const container = document.getElementById('mapContainer');
                const rect = container.getBoundingClientRect();
                
                let x = e.clientX - rect.left - dragData.offsetX;
                let y = e.clientY - rect.top - dragData.offsetY;
                
                // Ограничиваем, чтобы токен не выходил за пределы
                x = Math.max(0, Math.min(x, container.clientWidth - 60));
                y = Math.max(0, Math.min(y, container.clientHeight - 60));
                
                token.style.left = x + 'px';
                token.style.top = y + 'px';
            }}
            
            function stopDrag(e) {{
                if (dragData) {{
                    const token = document.getElementById(`token-${{dragData.tokenId}}`);
                    if (token) token.style.cursor = 'grab';
                    dragData = null;
                    document.removeEventListener('mousemove', onDrag);
                    document.removeEventListener('mouseup', stopDrag);
                    
                    // ОТПРАВЛЯЕМ НОВЫЕ КООРДИНАТЫ НА СЕРВЕР (через WebSocket)
                    // ПОКА ПРОСТО ЗАГЛУШКА
                    console.log('Токен перемещён');
                }}
            }}

            // -------- ЧАТ (WebSocket) --------
            const ws = new WebSocket(`ws://${{window.location.host}}/ws/${{window.location.pathname.split('/')[2]}}/${{{user.id}}}`);
            
            ws.onopen = function() {{
                console.log('WebSocket подключён');
                addMessage('Система', 'Подключено к игровому столу', 'system');
            }};
            
            ws.onmessage = function(event) {{
                const data = event.data;
                if (data.startsWith('💬')) {{
                    const parts = data.split(': ');
                    if (parts.length >= 2) {{
                        addMessage(parts[0].replace('💬 ', ''), parts[1], 'player');
                    }}
                }} else {{
                    addMessage('Система', data, 'system');
                }}
            }};
            
            ws.onclose = function() {{
                addMessage('Система', 'Отключено от сервера', 'system');
            }};
            
            function addMessage(sender, text, type) {{
                const messages = document.getElementById('chatMessages');
                const div = document.createElement('div');
                if (type === 'system') {{
                    div.className = 'system';
                    div.textContent = `⚙ ${{text}}`;
                }} else {{
                    div.className = 'player';
                    div.textContent = `${{sender}}: ${{text}}`;
                }}
                messages.appendChild(div);
                messages.scrollTop = messages.scrollHeight;
            }}
            
            function sendMessage() {{
                const input = document.getElementById('chatInput');
                const text = input.value.trim();
                if (text && ws.readyState === WebSocket.OPEN) {{
                    ws.send(text);
                    input.value = '';
                }}
            }}
            
            document.getElementById('chatSendBtn').addEventListener('click', sendMessage);
            document.getElementById('chatInput').addEventListener('keydown', function(e) {{
                if (e.key === 'Enter') sendMessage();
            }});
            
            // ПРИМЕР: Обновление позиции токена через WebSocket (пока заглушка)
            function updateTokenPosition(tokenId, x, y) {{
                // Отправляем на сервер
                ws.send(`/move ${{tokenId}} ${{x}} ${{y}}`);
            }}
            
            console.log('🚀 Игровая комната загружена!');
        </script>
    </body>
    </html>
    """)
@app.post("/api/table/delete")
async def delete_table(data: dict):
    session = Session()
    try:
        table = session.query(GameTable).filter_by(id=data['table_id']).first()
        if not table:
            return {"success": False, "message": "Стол не найден"}
        table.is_active = False
        session.commit()
        return {"success": True, "message": "Стол удалён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# -------- ИГРОВОЙ ВЕБСОКЕТ --------
@app.websocket("/ws/{table_link}/{player_name}")
async def websocket_endpoint(websocket: WebSocket, table_link: str, player_name: str):
    await websocket.accept()
    await websocket.send_text(f"Добро пожаловать в игру {table_link}, {player_name}!")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Эхо: {data}")
    except WebSocketDisconnect:
        pass
