from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, joinedload
from datetime import datetime
import hashlib
import json
import secrets
import os
import uuid
import random
import math
import re
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# 1. БАЗА ДАННЫХ — НОВАЯ ФИЛОСОФИЯ ПЕРСОНАЖЕЙ
# ============================================================

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
    created_at = Column(DateTime, default=datetime.now)

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    theme = Column(String)
    background_image = Column(String)

# ============================================================
# 2. УНИВЕРСАЛЬНЫЙ ПЕРСОНАЖ (БЕЗ ЖЁСТКИХ ПОЛЕЙ)
# ============================================================

class Character(Base):
    """
    Универсальный персонаж для ЛЮБОГО сеттинга.
    Никакой привязки к D&D или конкретной системе.
    """
    __tablename__ = 'characters'
    
    # === БАЗОВАЯ ИДЕНТИФИКАЦИЯ ===
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), default='')
    nickname = Column(String(100), default='')
    
    # === ВНЕШНИЙ ВИД ===
    portrait = Column(String(255), default='')
    token = Column(String(255), default='')
    description = Column(Text, default='')
    biography = Column(Text, default='')
    
    # === ГИБКИЕ ПОЛЯ (ПРОСТО СТРОКИ) ===
    class_name = Column(String(100), default='')  # Любой класс: Воин, Репортёр, Инквизитор
    race = Column(String(100), default='')        # Любая раса: Человек, Вампир, Киборг
    background = Column(String(100), default='')  # Любой бэкграунд
    alignment = Column(String(50), default='')    # Любое мировоззрение
    
    # === БАЗОВЫЕ БОЕВЫЕ ПАРАМЕТРЫ (ОПЦИОНАЛЬНО) ===
    armor_class = Column(Integer, default=10)
    speed = Column(Integer, default=30)
    max_hp = Column(Integer, default=20)
    current_hp = Column(Integer, default=20)
    temporary_hp = Column(Integer, default=0)
    
    # === ВАЛЮТА (ГИБКАЯ) ===
    currency = Column(JSON, default='{}')  # {"gold": 100, "credits": 50, "pounds": 10}
    
    # === ДИНАМИЧЕСКИЕ ХАРАКТЕРИСТИКИ ===
    stats = Column(JSON, default='{}')
    # {"strength": 10, "dexterity": 14, "constitution": 12,
    #  "influence": 8, "fear": 5, "will": 10}
    
    # === ДИНАМИЧЕСКИЕ НАВЫКИ ===
    skills = Column(JSON, default='[]')
    # [{"id": "skill_1", "name": "Взлом", "value": 12},
    #  {"id": "skill_2", "name": "Убеждение", "value": 8}]
    
    # === ИНВЕНТАРЬ (ПОЛНОСТЬЮ РУЧНОЙ) ===
    inventory = Column(JSON, default='[]')
    # [{"id": "item_1", "name": "Меч", "quantity": 1, "description": "Ржавый меч"},
    #  {"id": "item_2", "name": "Улика", "quantity": 1, "description": "Кровавый отпечаток"}]
    
    # === ЭКИПИРОВКА ===
    equipment = Column(JSON, default='{}')
    # {"main_hand": null, "off_hand": null, "armor": null}
    
    # === ЭФФЕКТЫ ===
    effects = Column(JSON, default='[]')
    
    # === МЕТАДАННЫЕ ===
    player_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'), nullable=True)
    is_npc = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey('users.id'))
    
    # === СВЯЗИ ===
    owner = relationship("User", foreign_keys=[created_by])
    player = relationship("User", foreign_keys=[player_id])
    
    def to_dict(self) -> dict:
        """Преобразует персонажа в словарь для API."""
        return {
            'id': self.id,
            'name': self.name,
            'surname': self.surname,
            'nickname': self.nickname,
            'portrait': self.portrait,
            'token': self.token,
            'description': self.description,
            'biography': self.biography,
            'class': self.class_name,
            'race': self.race,
            'background': self.background,
            'alignment': self.alignment,
            'armor_class': self.armor_class,
            'speed': self.speed,
            'max_hp': self.max_hp,
            'current_hp': self.current_hp,
            'temporary_hp': self.temporary_hp,
            'currency': json.loads(self.currency) if self.currency else {},
            'stats': json.loads(self.stats) if self.stats else {},
            'skills': json.loads(self.skills) if self.skills else [],
            'inventory': json.loads(self.inventory) if self.inventory else [],
            'equipment': json.loads(self.equipment) if self.equipment else {},
            'effects': json.loads(self.effects) if self.effects else [],
            'is_npc': self.is_npc,
            'player_id': self.player_id,
            'room_id': self.room_id
        }
    
    def get_stat(self, stat_name: str) -> int:
        """Получает значение характеристики по имени."""
        stats = json.loads(self.stats) if self.stats else {}
        return stats.get(stat_name, 10)
    
    def set_stat(self, stat_name: str, value: int):
        """Устанавливает значение характеристики."""
        stats = json.loads(self.stats) if self.stats else {}
        stats[stat_name] = value
        self.stats = json.dumps(stats)
    
    def get_skill(self, skill_name: str) -> Optional[dict]:
        """Получает навык по имени."""
        skills = json.loads(self.skills) if self.skills else []
        for skill in skills:
            if skill.get('name') == skill_name:
                return skill
        return None
    
    def add_skill(self, skill_data: dict):
        """Добавляет навык."""
        skills = json.loads(self.skills) if self.skills else []
        skills.append(skill_data)
        self.skills = json.dumps(skills)
    
    def remove_skill(self, skill_id: str):
        """Удаляет навык."""
        skills = json.loads(self.skills) if self.skills else []
        skills = [s for s in skills if s.get('id') != skill_id]
        self.skills = json.dumps(skills)
    
    def add_item(self, item_data: dict):
        """Добавляет предмет в инвентарь."""
        inventory = json.loads(self.inventory) if self.inventory else []
        inventory.append(item_data)
        self.inventory = json.dumps(inventory)
    
    def remove_item(self, item_id: str):
        """Удаляет предмет из инвентаря."""
        inventory = json.loads(self.inventory) if self.inventory else []
        inventory = [i for i in inventory if i.get('id') != item_id]
        self.inventory = json.dumps(inventory)
    
    def get_currency(self, currency_type: str) -> int:
        """Получает количество валюты определённого типа."""
        currency = json.loads(self.currency) if self.currency else {}
        return currency.get(currency_type, 0)
    
    def set_currency(self, currency_type: str, amount: int):
        """Устанавливает количество валюты."""
        currency = json.loads(self.currency) if self.currency else {}
        currency[currency_type] = amount
        self.currency = json.dumps(currency)
    
    def add_currency(self, currency_type: str, amount: int):
        """Добавляет валюту."""
        current = self.get_currency(currency_type)
        self.set_currency(currency_type, current + amount)
    
    def remove_currency(self, currency_type: str, amount: int) -> bool:
        """Удаляет валюту. Возвращает True, если достаточно."""
        current = self.get_currency(currency_type)
        if current < amount:
            return False
        self.set_currency(currency_type, current - amount)
        return True
    
    def add_effect(self, effect_data: dict):
        """Добавляет эффект."""
        effects = json.loads(self.effects) if self.effects else []
        effects.append(effect_data)
        self.effects = json.dumps(effects)
    
    def remove_effect(self, effect_id: str):
        """Удаляет эффект."""
        effects = json.loads(self.effects) if self.effects else []
        effects = [e for e in effects if e.get('id') != effect_id]
        self.effects = json.dumps(effects)

# ============================================================
# 3. КАСТОМНЫЕ НАВЫКИ (СОЗДАЮТСЯ ГМ)
# ============================================================

class CustomSkill(Base):
    """Навык, созданный ГМ. Не привязан к системе."""
    __tablename__ = 'custom_skills'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(255), default='')
    description = Column(Text, default='')
    
    # Механики навыка
    dice_formula = Column(String(50), default='1d20')  # Например: 1d20, 2d6, 1d100
    damage_formula = Column(String(50), default='')    # Например: 1d8+3
    saving_throw = Column(String(50), default='')      # Например: dex, con, will
    target_type = Column(String(50), default='single') # single, area, self
    
    # Стоимость и перезарядка
    cost_type = Column(String(50), default='action')   # action, bonus, reaction, free
    cost_value = Column(Integer, default=1)
    cooldown = Column(Integer, default=0)
    
    # Эффекты
    effects = Column(JSON, default='[]')
    
    # Визуал
    animation = Column(String(100), default='')
    
    # Метаданные
    created_by = Column(Integer, ForeignKey('users.id'))
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    created_at = Column(DateTime, default=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'description': self.description,
            'dice_formula': self.dice_formula,
            'damage_formula': self.damage_formula,
            'saving_throw': self.saving_throw,
            'target_type': self.target_type,
            'cost_type': self.cost_type,
            'cost_value': self.cost_value,
            'cooldown': self.cooldown,
            'effects': json.loads(self.effects) if self.effects else [],
            'animation': self.animation
        }

# ============================================================
# 4. ИГРОВЫЕ КОМНАТЫ
# ============================================================

class GameRoom(Base):
    __tablename__ = 'game_rooms'
    id = Column(Integer, primary_key=True)
    room_id = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    gm_id = Column(Integer, ForeignKey('users.id'))
    password_hash = Column(String, nullable=True)
    state = Column(String(20), default='lobby')
    max_players = Column(Integer, default=6)
    is_private = Column(Boolean, default=False)
    current_map = Column(String(255), default='')
    current_scene = Column(String(100), default='')
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    gm = relationship("User", foreign_keys=[gm_id])
    tokens = relationship("GameToken", backref="room")
    players = relationship("RoomPlayer", backref="room", cascade="all, delete-orphan")
    custom_skills = relationship("CustomSkill", backref="room", cascade="all, delete-orphan")

class RoomPlayer(Base):
    __tablename__ = 'room_players'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    role = Column(String(20), default='player')
    is_ready = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.now)
    user = relationship("User", foreign_keys=[user_id])
    character = relationship("Character", foreign_keys=[character_id])

class GameToken(Base):
    __tablename__ = 'game_tokens'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    name = Column(String, default='')
    avatar_url = Column(String, default='')
    role = Column(String, default='NPC')
    owner_id = Column(Integer, nullable=True)
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    x = Column(Float, default=0)
    y = Column(Float, default=0)
    is_visible = Column(Boolean, default=True)
    layer = Column(String, default='common')
    description = Column(String, default='')
    created_at = Column(DateTime, default=datetime.now)
    character = relationship("Character", foreign_keys=[character_id])

class ActionLog(Base):
    __tablename__ = 'action_logs'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    timestamp = Column(DateTime, default=datetime.now)
    action_type = Column(String(50))
    actor_id = Column(Integer, nullable=True)
    actor_name = Column(String(100), default='')
    character_id = Column(Integer, nullable=True)
    character_name = Column(String(100), default='')
    target_id = Column(Integer, nullable=True)
    target_name = Column(String(100), default='')
    action_data = Column(Text, default='{}')
    roll_result = Column(Text, default='{}')
    result = Column(String(20), default='')
    message = Column(Text, default='')
    visibility = Column(String(20), default='public')
    gm_modified = Column(Boolean, default=False)

# ============================================================
# 5. МИГРАЦИЯ
# ============================================================

def migrate_database():
    session = Session()
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if 'game_rooms' not in inspector.get_table_names():
            print("🔄 Создаём таблицы...")
            Base.metadata.create_all(engine)
            print("✅ Таблицы созданы!")
        if 'custom_skills' not in inspector.get_table_names():
            print("🔄 Создаём таблицу Custom Skills...")
            Base.metadata.create_all(engine)
            print("✅ Таблица навыков создана!")
        if 'action_logs' not in inspector.get_table_names():
            print("🔄 Создаём таблицу Action Logs...")
            Base.metadata.create_all(engine)
            print("✅ Таблица логов создана!")
    except Exception as e:
        print(f"⚠️ Ошибка миграции: {e}")
    finally:
        session.close()

Base.metadata.create_all(engine)
migrate_database()

# ============================================================
# 6. FASTAPI
# ============================================================

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AVATAR_DIR = "static/avatars"
MAP_DIR = "static/maps"
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(MAP_DIR, exist_ok=True)

connections = {}

# ============================================================
# 7. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_by_login_or_email(login_or_email):
    session = Session()
    user = session.query(User).filter((User.login == login_or_email) | (User.email == login_or_email)).first()
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
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None
    try:
        data = serializer.loads(session_cookie, max_age=60 * 60 * 24 * 7)
        user_id = data.get("user_id")
        if user_id:
            return get_user_by_id(user_id)
    except:
        return None
    return None

def generate_room_id():
    return secrets.token_urlsafe(8)

# ============================================================
# 8. API: ПЕРСОНАЖИ (НОВАЯ ФИЛОСОФИЯ)
# ============================================================

@app.post("/api/character/create")
async def create_character(request: Request, data: dict):
    """Создаёт персонажа для ЛЮБОГО сеттинга."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = Character(
            name=data.get('name', 'Новый персонаж'),
            surname=data.get('surname', ''),
            nickname=data.get('nickname', ''),
            portrait=data.get('portrait', ''),
            token=data.get('token', ''),
            description=data.get('description', ''),
            biography=data.get('biography', ''),
            class_name=data.get('class', ''),
            race=data.get('race', ''),
            background=data.get('background', ''),
            alignment=data.get('alignment', ''),
            armor_class=data.get('armor_class', 10),
            speed=data.get('speed', 30),
            max_hp=data.get('max_hp', 20),
            current_hp=data.get('current_hp', 20),
            temporary_hp=data.get('temporary_hp', 0),
            player_id=user.id,
            room_id=data.get('room_id'),
            is_npc=data.get('is_npc', False),
            created_by=user.id
        )
        
        # Инициализируем пустые JSON поля
        character.stats = json.dumps(data.get('stats', {}))
        character.skills = json.dumps(data.get('skills', []))
        character.inventory = json.dumps(data.get('inventory', []))
        character.equipment = json.dumps(data.get('equipment', {}))
        character.effects = json.dumps(data.get('effects', []))
        character.currency = json.dumps(data.get('currency', {}))
        
        session.add(character)
        session.commit()
        
        return {
            'success': True,
            'character_id': character.id,
            'character': character.to_dict()
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/character/{character_id}")
async def get_character(character_id: int):
    """Получает персонажа."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        return {'success': True, 'character': character.to_dict()}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.put("/api/character/{character_id}")
async def update_character(character_id: int, data: dict):
    """Обновляет персонажа (любые поля)."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        # Обновляем все переданные поля
        for key, value in data.items():
            if hasattr(character, key):
                setattr(character, key, value)
        
        session.commit()
        
        # Уведомляем через WebSocket
        if character.room_id:
            await broadcast_to_room(character.room_id, {
                'type': 'character_update',
                'character_id': character.id,
                'character': character.to_dict()
            })
        
        return {'success': True, 'character': character.to_dict()}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/character/{character_id}/stat")
async def update_character_stat(character_id: int, data: dict):
    """Обновляет конкретную характеристику."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        stat_name = data.get('stat_name')
        stat_value = data.get('stat_value')
        
        if not stat_name or stat_value is None:
            return {"success": False, "message": "Не указаны stat_name или stat_value"}
        
        character.set_stat(stat_name, stat_value)
        session.commit()
        
        return {
            'success': True,
            'stat_name': stat_name,
            'stat_value': stat_value
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/character/{character_id}/skill")
async def add_character_skill(character_id: int, data: dict):
    """Добавляет навык персонажу."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        skill_data = data.get('skill')
        if not skill_data:
            return {"success": False, "message": "Не указан skill"}
        
        character.add_skill(skill_data)
        session.commit()
        
        return {
            'success': True,
            'skill': skill_data
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.delete("/api/character/{character_id}/skill/{skill_id}")
async def remove_character_skill(character_id: int, skill_id: str):
    """Удаляет навык у персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        character.remove_skill(skill_id)
        session.commit()
        
        return {'success': True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/character/{character_id}/item")
async def add_character_item(character_id: int, data: dict):
    """Добавляет предмет персонажу."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        item_data = data.get('item')
        if not item_data:
            return {"success": False, "message": "Не указан item"}
        
        character.add_item(item_data)
        session.commit()
        
        return {
            'success': True,
            'item': item_data
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.delete("/api/character/{character_id}/item/{item_id}")
async def remove_character_item(character_id: int, item_id: str):
    """Удаляет предмет у персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        character.remove_item(item_id)
        session.commit()
        
        return {'success': True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/character/{character_id}/currency")
async def update_character_currency(character_id: int, data: dict):
    """Обновляет валюту персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        currency_type = data.get('currency_type')
        amount = data.get('amount')
        
        if not currency_type or amount is None:
            return {"success": False, "message": "Не указаны currency_type или amount"}
        
        character.set_currency(currency_type, amount)
        session.commit()
        
        return {
            'success': True,
            'currency_type': currency_type,
            'amount': amount
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 9. API: КАСТОМНЫЕ НАВЫКИ (СОЗДАЮТСЯ ГМ)
# ============================================================

@app.post("/api/skill/create")
async def create_custom_skill(request: Request, data: dict):
    """Создаёт кастомный навык (только для ГМ)."""
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return {"success": False, "message": "Только GM может создавать навыки"}
    
    session = Session()
    try:
        skill = CustomSkill(
            name=data.get('name', 'Новый навык'),
            icon=data.get('icon', ''),
            description=data.get('description', ''),
            dice_formula=data.get('dice_formula', '1d20'),
            damage_formula=data.get('damage_formula', ''),
            saving_throw=data.get('saving_throw', ''),
            target_type=data.get('target_type', 'single'),
            cost_type=data.get('cost_type', 'action'),
            cost_value=data.get('cost_value', 1),
            cooldown=data.get('cooldown', 0),
            animation=data.get('animation', ''),
            created_by=user.id,
            room_id=data.get('room_id')
        )
        skill.effects = json.dumps(data.get('effects', []))
        
        session.add(skill)
        session.commit()
        
        return {
            'success': True,
            'skill': skill.to_dict()
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/skill/room/{room_id}")
async def get_room_skills(room_id: int):
    """Получает все навыки комнаты."""
    session = Session()
    try:
        skills = session.query(CustomSkill).filter_by(room_id=room_id).all()
        return {
            'success': True,
            'skills': [s.to_dict() for s in skills]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.delete("/api/skill/{skill_id}")
async def delete_custom_skill(skill_id: int, request: Request):
    """Удаляет кастомный навык."""
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return {"success": False, "message": "Только GM может удалять навыки"}
    
    session = Session()
    try:
        skill = session.query(CustomSkill).filter_by(id=skill_id).first()
        if not skill:
            return {"success": False, "message": "Навык не найден"}
        
        session.delete(skill)
        session.commit()
        
        return {'success': True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 10. ROOM MANAGER
# ============================================================

class RoomManager:
    def __init__(self):
        self._rooms: Dict[str, GameRoom] = {}

    def create_room(self, name: str, gm_id: int, is_private: bool = False, password: str = None) -> GameRoom:
        room_id = generate_room_id()
        session = Session()
        try:
            room = GameRoom(
                room_id=room_id,
                name=name,
                gm_id=gm_id,
                is_private=is_private,
                password_hash=hash_password(password) if password else None,
                state='lobby'
            )
            session.add(room)
            session.commit()
            room_player = RoomPlayer(
                room_id=room.id,
                user_id=gm_id,
                role='gm',
                is_ready=True
            )
            session.add(room_player)
            session.commit()
            session.refresh(room)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
        return room

    def get_room(self, room_id: str) -> Optional[GameRoom]:
        session = Session()
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        session.close()
        return room

    def get_all_rooms(self) -> List[GameRoom]:
        session = Session()
        rooms = session.query(GameRoom).filter(GameRoom.state != 'finished').all()
        session.close()
        return rooms

    def get_room_players(self, room_id: str) -> List[dict]:
        session = Session()
        players = session.query(RoomPlayer).filter_by(room_id=room_id).all()
        result = []
        for p in players:
            user = session.query(User).filter_by(id=p.user_id).first()
            character = session.query(Character).filter_by(id=p.character_id).first() if p.character_id else None
            result.append({
                'user_id': p.user_id,
                'login': user.login if user else 'Unknown',
                'role': p.role,
                'is_ready': p.is_ready,
                'character_id': p.character_id,
                'character_name': character.name if character else None
            })
        session.close()
        return result

room_manager = RoomManager()

# ============================================================
# 11. WEBSOCKET ДЛЯ СИНХРОНИЗАЦИИ
# ============================================================

async def broadcast_to_room(room_id: int, message: dict):
    """Отправляет сообщение всем в комнате."""
    for ws in connections.get(room_id, []):
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass

@app.websocket("/ws/character/{character_id}")
async def character_websocket(websocket: WebSocket, character_id: int):
    """WebSocket для синхронизации карточки персонажа."""
    await websocket.accept()
    
    user = get_current_user(websocket)
    if not user:
        await websocket.close()
        return
    
    session = Session()
    character = session.query(Character).filter_by(id=character_id).first()
    session.close()
    
    if not character:
        await websocket.close()
        return
    
    room_id = character.room_id
    
    if room_id not in connections:
        connections[room_id] = []
    connections[room_id].append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                
                if msg.get('type') == 'update':
                    # Обновление карточки
                    session = Session()
                    character = session.query(Character).filter_by(id=character_id).first()
                    if character:
                        for key, value in msg.get('data', {}).items():
                            if hasattr(character, key):
                                setattr(character, key, value)
                        session.commit()
                        
                        # Отправляем обновление всем в комнате
                        await broadcast_to_room(room_id, {
                            'type': 'character_updated',
                            'character_id': character_id,
                            'character': character.to_dict()
                        })
                    session.close()
                
                elif msg.get('type') == 'get':
                    # Запрос текущего состояния
                    session = Session()
                    character = session.query(Character).filter_by(id=character_id).first()
                    if character:
                        await websocket.send_text(json.dumps({
                            'type': 'character_data',
                            'character': character.to_dict()
                        }))
                    session.close()
                    
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        if room_id in connections:
            if websocket in connections[room_id]:
                connections[room_id].remove(websocket)
            if not connections[room_id]:
                del connections[room_id]

# ============================================================
# 12. СТРАНИЦЫ
# ============================================================

@app.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == 'gm':
            return RedirectResponse(url="/gm_dashboard", status_code=303)
        else:
            return RedirectResponse(url="/player_dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, login_or_email: str = Form(...), password: str = Form(...), next: str = Form("")):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
    user = get_user_by_login_or_email(login_or_email)
    if not user or user.password_hash != hash_password(password):
        return HTMLResponse(content="<h2>❌ Неверный логин/email или пароль</h2><a href='/login'>Вернуться</a>", status_code=400)
    session_token = serializer.dumps({"user_id": user.id})
    if next:
        response = RedirectResponse(url=next, status_code=303)
    elif user.role == 'gm':
        response = RedirectResponse(url="/gm_dashboard", status_code=303)
    else:
        response = RedirectResponse(url="/player_dashboard", status_code=303)
    response.set_cookie(key="session", value=session_token, httponly=True, max_age=604800)
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, login: str = Form(...), email: str = Form(...), password: str = Form(...), password_confirm: str = Form(...), role: str = Form("unassigned")):
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
    return RedirectResponse(url="/login?registered=true", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response

@app.get("/gm_dashboard", response_class=HTMLResponse)
async def gm_dashboard(request: Request):
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return RedirectResponse(url="/login", status_code=303)
    rooms = room_manager.get_all_rooms()
    return templates.TemplateResponse("gm_dashboard.html", {
        "request": request,
        "user": user,
        "rooms": rooms
    })

@app.get("/player_dashboard", response_class=HTMLResponse)
async def player_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    player_rooms = session.query(GameRoom).join(RoomPlayer).filter(RoomPlayer.user_id == user.id).all()
    session.close()
    return templates.TemplateResponse("player_dashboard.html", {
        "request": request,
        "user": user,
        "rooms": player_rooms
    })

@app.get("/join/{room_id}", response_class=HTMLResponse)
async def join_room_page(request: Request, room_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/join/{room_id}", status_code=303)
    return RedirectResponse(url=f"/room/{room_id}", status_code=303)

@app.get("/room/{room_id}", response_class=HTMLResponse)
async def room_page(request: Request, room_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/room/{room_id}", status_code=303)
    
    room = room_manager.get_room(room_id)
    if not room:
        return HTMLResponse(content="<h2>❌ Комната не найдена</h2><a href='/'>На главную</a>", status_code=404)
    
    session = Session()
    room_player = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user.id).first()
    if not room_player:
        return HTMLResponse(content="<h2>⛔ Вы не в этой комнате</h2><a href='/'>На главную</a>", status_code=403)
    
    characters = session.query(Character).filter_by(room_id=room.id).all()
    skills = session.query(CustomSkill).filter_by(room_id=room.id).all()
    tokens = session.query(GameToken).filter_by(room_id=room.id).all()
    session.close()
    
    return templates.TemplateResponse("room.html", {
        "request": request,
        "user": user,
        "room": room,
        "characters": characters,
        "skills": skills,
        "tokens": tokens,
        "is_gm": room.gm_id == user.id
    })

# ============================================================
# 13. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
