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

# ============================================================
# 1. БАЗА ДАННЫХ
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
# 2. CHARACTER — ЕДИНАЯ СТРУКТУРА ПЕРСОНАЖА
# ============================================================

class Character(Base):
    __tablename__ = 'characters'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    surname = Column(String(50), default='')
    nickname = Column(String(50), default='')
    race = Column(String(50), default='')
    class_name = Column(String(50), default='')
    background = Column(String(50), default='')
    player_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    table_id = Column(Integer, ForeignKey('game_tables.id'), nullable=True)
    
    portrait = Column(String(255), default='')
    token = Column(String(255), default='')
    model = Column(String(255), default='')
    gender = Column(String(20), default='')
    age = Column(Integer, default=0)
    height = Column(Float, default=0.0)
    weight = Column(Float, default=0.0)
    hair = Column(String(30), default='')
    eyes = Column(String(30), default='')
    skin = Column(String(30), default='')
    
    str_base = Column(Integer, default=10)
    str_bonus = Column(Integer, default=0)
    str_temporary = Column(Integer, default=0)
    dex_base = Column(Integer, default=10)
    dex_bonus = Column(Integer, default=0)
    dex_temporary = Column(Integer, default=0)
    con_base = Column(Integer, default=10)
    con_bonus = Column(Integer, default=0)
    con_temporary = Column(Integer, default=0)
    int_base = Column(Integer, default=10)
    int_bonus = Column(Integer, default=0)
    int_temporary = Column(Integer, default=0)
    wis_base = Column(Integer, default=10)
    wis_bonus = Column(Integer, default=0)
    wis_temporary = Column(Integer, default=0)
    cha_base = Column(Integer, default=10)
    cha_bonus = Column(Integer, default=0)
    cha_temporary = Column(Integer, default=0)
    
    armor_class = Column(Integer, default=12)
    initiative_bonus = Column(Integer, default=0)
    speed = Column(Integer, default=30)
    proficiency_bonus = Column(Integer, default=2)
    critical_range = Column(Integer, default=20)
    critical_multiplier = Column(Integer, default=2)
    
    resources = Column(JSON, default='{}')
    skills = Column(JSON, default='[]')
    inventory = Column(JSON, default='[]')
    equipment = Column(JSON, default='{}')
    effects = Column(JSON, default='[]')
    
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    skill_points = Column(Integer, default=0)
    perks = Column(JSON, default='[]')
    achievements = Column(JSON, default='[]')
    
    description = Column(Text, default='')
    biography = Column(Text, default='')
    goals = Column(Text, default='')
    faction = Column(String(50), default='')
    religion = Column(String(50), default='')
    occupation = Column(String(50), default='')
    history = Column(Text, default='')
    notes = Column(Text, default='')
    
    is_npc = Column(Boolean, default=False)
    is_hostile = Column(Boolean, default=False)
    
    permissions = Column(JSON, default='{}')
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey('users.id'))
    owner = relationship("User", foreign_keys=[created_by])
    tokens = relationship("GameToken", backref="character")

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'surname': self.surname,
            'nickname': self.nickname,
            'race': self.race,
            'class': self.class_name,
            'background': self.background,
            'player_id': self.player_id,
            'table_id': self.table_id,
            'portrait': self.portrait,
            'token': self.token,
            'gender': self.gender,
            'age': self.age,
            'height': self.height,
            'weight': self.weight,
            'hair': self.hair,
            'eyes': self.eyes,
            'skin': self.skin,
            'strength': {'base': self.str_base, 'bonus': self.str_bonus, 'temporary': self.str_temporary},
            'dexterity': {'base': self.dex_base, 'bonus': self.dex_bonus, 'temporary': self.dex_temporary},
            'constitution': {'base': self.con_base, 'bonus': self.con_bonus, 'temporary': self.con_temporary},
            'intelligence': {'base': self.int_base, 'bonus': self.int_bonus, 'temporary': self.int_temporary},
            'wisdom': {'base': self.wis_base, 'bonus': self.wis_bonus, 'temporary': self.wis_temporary},
            'charisma': {'base': self.cha_base, 'bonus': self.cha_bonus, 'temporary': self.cha_temporary},
            'armor_class': self.armor_class,
            'initiative_bonus': self.initiative_bonus,
            'speed': self.speed,
            'proficiency_bonus': self.proficiency_bonus,
            'resources': json.loads(self.resources) if self.resources else {},
            'skills': json.loads(self.skills) if self.skills else [],
            'inventory': json.loads(self.inventory) if self.inventory else [],
            'equipment': json.loads(self.equipment) if self.equipment else {},
            'effects': json.loads(self.effects) if self.effects else [],
            'level': self.level,
            'experience': self.experience,
            'description': self.description,
            'biography': self.biography,
            'is_npc': self.is_npc
        }
    
    def get_attribute(self, attr_name: str) -> int:
        attr_map = {
            'strength': ('str_base', 'str_bonus', 'str_temporary'),
            'dexterity': ('dex_base', 'dex_bonus', 'dex_temporary'),
            'constitution': ('con_base', 'con_bonus', 'con_temporary'),
            'intelligence': ('int_base', 'int_bonus', 'int_temporary'),
            'wisdom': ('wis_base', 'wis_bonus', 'wis_temporary'),
            'charisma': ('cha_base', 'cha_bonus', 'cha_temporary')
        }
        base, bonus, temp = attr_map.get(attr_name, (None, None, None))
        if base is None:
            return 0
        return getattr(self, base, 0) + getattr(self, bonus, 0) + getattr(self, temp, 0)
    
    def get_resource(self, resource_name: str) -> dict:
        resources = json.loads(self.resources) if self.resources else {}
        return resources.get(resource_name, {'current': 0, 'maximum': 0, 'temporary': 0, 'regeneration': 0})
    
    def set_resource(self, resource_name: str, value: dict):
        resources = json.loads(self.resources) if self.resources else {}
        resources[resource_name] = value
        self.resources = json.dumps(resources)

# ============================================================
# 3. ИГРОВЫЕ СУЩНОСТИ
# ============================================================

class GameTable(Base):
    __tablename__ = 'game_tables'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    gm_id = Column(Integer, ForeignKey('users.id'))
    setting_id = Column(Integer, ForeignKey('settings.id'))
    link = Column(String, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    gm = relationship("User")
    setting = relationship("Settings")
    map_image = Column(String, default='')
    map_x = Column(Float, default=0.0)
    map_y = Column(Float, default=0.0)
    map_width = Column(Float, default=40)
    map_height = Column(Float, default=30)
    map_opacity = Column(Float, default=1.0)
    map_rotation = Column(Float, default=0.0)
    map_layer = Column(String, default='map')

class GameToken(Base):
    __tablename__ = 'game_tokens'
    id = Column(Integer, primary_key=True)
    table_link = Column(String, ForeignKey('game_tables.link'))
    name = Column(String, default='')
    avatar_url = Column(String, default='')
    role = Column(String, default='NPC')
    owner_name = Column(String, default='')
    x = Column(Float, default=0)
    y = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    is_visible = Column(Boolean, default=True)
    layer = Column(String, default='common')
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    table = relationship("GameTable", backref="tokens")
    description = Column(String, default='')

class PlayerGame(Base):
    __tablename__ = 'player_games'
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('users.id'))
    table_link = Column(String, ForeignKey('game_tables.link'))
    joined_at = Column(DateTime, default=datetime.now)
    player = relationship("User", foreign_keys=[player_id])
    table = relationship("GameTable", foreign_keys=[table_link])

class GameSession(Base):
    __tablename__ = 'game_sessions'
    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    gm_id = Column(Integer, ForeignKey('users.id'))
    table_link = Column(String, ForeignKey('game_tables.link'))
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    state = Column(String(20), default='LOBBY')
    current_map = Column(String(255), default='')
    current_scene = Column(String(100), default='')
    current_round = Column(Integer, default=0)
    current_turn = Column(Integer, default=0)
    current_player_id = Column(Integer, nullable=True)
    settings = Column(Text, default='{}')
    gm = relationship("User", foreign_keys=[gm_id])
    table = relationship("GameTable", foreign_keys=[table_link])
    logs = relationship("SessionLog", back_populates="session", cascade="all, delete-orphan")

class SessionLog(Base):
    __tablename__ = 'session_logs'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('game_sessions.id'))
    timestamp = Column(DateTime, default=datetime.now)
    event_type = Column(String(50))
    actor_id = Column(Integer, nullable=True)
    message = Column(Text)
    data = Column(Text, default='{}')
    session = relationship("GameSession", back_populates="logs")

# ============================================================
# 4. PARSER SERVICE — НЕТ ИИ, ТОЛЬКО СТРУКТУРЫ
# ============================================================

class ParserService:
    """
    Сервис парсинга данных.
    Работает ТОЛЬКО по заранее определённым шаблонам.
    НИКАКОГО ИИ. НИКАКОЙ ГЕНЕРАЦИИ.
    """
    
    @staticmethod
    def parse_character(data: dict) -> dict:
        """
        Парсит карточку персонажа из словаря.
        Возвращает структуру для создания Character.
        """
        result = {
            'name': data.get('name', ''),
            'surname': data.get('surname', ''),
            'nickname': data.get('nickname', ''),
            'race': data.get('race', ''),
            'class_name': data.get('class', data.get('class_name', '')),
            'background': data.get('background', ''),
            'portrait': data.get('portrait', ''),
            'token': data.get('token', ''),
            'gender': data.get('gender', ''),
            'age': data.get('age', 0),
            'height': data.get('height', 0.0),
            'weight': data.get('weight', 0.0),
            'hair': data.get('hair', ''),
            'eyes': data.get('eyes', ''),
            'skin': data.get('skin', ''),
            'str_base': data.get('strength', data.get('str_base', 10)),
            'dex_base': data.get('dexterity', data.get('dex_base', 10)),
            'con_base': data.get('constitution', data.get('con_base', 10)),
            'int_base': data.get('intelligence', data.get('int_base', 10)),
            'wis_base': data.get('wisdom', data.get('wis_base', 10)),
            'cha_base': data.get('charisma', data.get('cha_base', 10)),
            'armor_class': data.get('armor_class', 12),
            'initiative_bonus': data.get('initiative_bonus', 0),
            'speed': data.get('speed', 30),
            'level': data.get('level', 1),
            'experience': data.get('experience', 0),
            'description': data.get('description', ''),
            'biography': data.get('biography', ''),
            'goals': data.get('goals', ''),
            'faction': data.get('faction', ''),
            'religion': data.get('religion', ''),
            'occupation': data.get('occupation', ''),
            'history': data.get('history', ''),
            'notes': data.get('notes', ''),
            'is_npc': data.get('is_npc', False),
            'max_hp': data.get('max_hp', 20),
            'max_mana': data.get('max_mana', 0),
            'max_energy': data.get('max_energy', 0),
            'max_rage': data.get('max_rage', 0)
        }
        return result
    
    @staticmethod
    def parse_npc(data: dict) -> dict:
        """
        Парсит карточку NPC.
        """
        result = ParserService.parse_character(data)
        result['is_npc'] = True
        return result
    
    @staticmethod
    def parse_item(data: dict) -> dict:
        """
        Парсит предмет.
        """
        return {
            'name': data.get('name', ''),
            'type': data.get('type', ''),
            'rarity': data.get('rarity', 'common'),
            'description': data.get('description', ''),
            'weight': data.get('weight', 0.0),
            'value': data.get('value', 0),
            'quantity': data.get('quantity', 1),
            'durability': data.get('durability', 100),
            'charges': data.get('charges', 0),
            'damage': data.get('damage', {}),
            'armor': data.get('armor', {}),
            'effects': data.get('effects', [])
        }
    
    @staticmethod
    def parse_spell(data: dict) -> dict:
        """
        Парсит заклинание.
        """
        return {
            'name': data.get('name', ''),
            'level': data.get('level', 1),
            'school': data.get('school', ''),
            'range': data.get('range', 0),
            'duration': data.get('duration', ''),
            'casting_time': data.get('casting_time', ''),
            'damage': data.get('damage', {}),
            'description': data.get('description', ''),
            'components': data.get('components', {}),
            'is_ritual': data.get('is_ritual', False),
            'is_concentration': data.get('is_concentration', False)
        }
    
    @staticmethod
    def parse_scenario(data: dict) -> dict:
        """
        Парсит сценарий из JSON.
        """
        return {
            'name': data.get('name', ''),
            'description': data.get('description', ''),
            'locations': data.get('locations', []),
            'scenes': data.get('scenes', []),
            'npcs': data.get('npcs', []),
            'monsters': data.get('monsters', []),
            'items': data.get('items', []),
            'maps': data.get('maps', []),
            'tokens': data.get('tokens', []),
            'triggers': data.get('triggers', []),
            'effects': data.get('effects', [])
        }
    
    @staticmethod
    def parse_json_file(file_content: str) -> dict:
        """
        Парсит JSON-файл.
        """
        try:
            data = json.loads(file_content)
            return data
        except json.JSONDecodeError as e:
            return {'error': f'Ошибка парсинга JSON: {str(e)}'}
    
    @staticmethod
    def validate_character(data: dict) -> dict:
        """
        Валидирует данные персонажа.
        Возвращает {'valid': True/False, 'errors': [...]}
        """
        errors = []
        if not data.get('name'):
            errors.append('Отсутствует имя персонажа')
        if data.get('level', 0) < 1:
            errors.append('Уровень должен быть не меньше 1')
        return {'valid': len(errors) == 0, 'errors': errors}

# ============================================================
# 5. МИГРАЦИЯ
# ============================================================

def migrate_database():
    session = Session()
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if 'characters' not in inspector.get_table_names():
            print("🔄 Создаём таблицы...")
            Base.metadata.create_all(engine)
            print("✅ Таблицы созданы!")
        if 'game_sessions' not in inspector.get_table_names():
            print("🔄 Создаём таблицы Game Session...")
            Base.metadata.create_all(engine)
            print("✅ Таблицы сессий созданы!")
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

def generate_table_link():
    return secrets.token_urlsafe(8)

# ============================================================
# 8. CHARACTER RUNTIME (ТОЛЬКО ДЛЯ ИГРЫ)
# ============================================================

@dataclass
class CharacterRuntime:
    runtime_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: int = 0
    player_id: int = 0
    table_link: str = ''
    current_hp: int = 20
    temporary_hp: int = 0
    max_hp: int = 20
    armor_class: int = 12
    speed: int = 30
    movement_left: int = 30
    action_used: bool = False
    bonus_action_used: bool = False
    reaction_used: bool = False
    initiative: int = 0
    is_alive: bool = True
    is_unconscious: bool = False
    conditions: List[str] = field(default_factory=list)
    active_effects: List[Dict] = field(default_factory=list)
    mana: int = 0
    max_mana: int = 0
    energy: int = 0
    max_energy: int = 0
    rage: int = 0
    max_rage: int = 0
    x: float = 0
    y: float = 0
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    str_save: int = 0
    dex_save: int = 0
    con_save: int = 0
    int_save: int = 0
    wis_save: int = 0
    cha_save: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            'runtime_id': self.runtime_id,
            'character_id': self.character_id,
            'player_id': self.player_id,
            'current_hp': self.current_hp,
            'temporary_hp': self.temporary_hp,
            'max_hp': self.max_hp,
            'armor_class': self.armor_class,
            'speed': self.speed,
            'movement_left': self.movement_left,
            'action_used': self.action_used,
            'bonus_action_used': self.bonus_action_used,
            'reaction_used': self.reaction_used,
            'initiative': self.initiative,
            'is_alive': self.is_alive,
            'is_unconscious': self.is_unconscious,
            'conditions': self.conditions,
            'active_effects': self.active_effects,
            'mana': self.mana,
            'max_mana': self.max_mana,
            'energy': self.energy,
            'max_energy': self.max_energy,
            'rage': self.rage,
            'max_rage': self.max_rage,
            'x': self.x,
            'y': self.y,
            'strength': self.strength,
            'dexterity': self.dexterity,
            'constitution': self.constitution,
            'intelligence': self.intelligence,
            'wisdom': self.wisdom,
            'charisma': self.charisma,
            'str_save': self.str_save,
            'dex_save': self.dex_save,
            'con_save': self.con_save,
            'int_save': self.int_save,
            'wis_save': self.wis_save,
            'cha_save': self.cha_save,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }

    def take_damage(self, damage: int) -> int:
        if self.temporary_hp > 0:
            temp_damage = min(damage, self.temporary_hp)
            self.temporary_hp -= temp_damage
            damage -= temp_damage
            if self.temporary_hp < 0:
                self.temporary_hp = 0
        if damage > 0:
            self.current_hp -= damage
            if self.current_hp < 0:
                self.current_hp = 0
        if self.current_hp <= 0:
            self.is_alive = False
            self.is_unconscious = True
        self.last_updated = datetime.now()
        return damage

    def heal(self, amount: int) -> int:
        old_hp = self.current_hp
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        if self.current_hp > 0:
            self.is_alive = True
            self.is_unconscious = False
        self.last_updated = datetime.now()
        return self.current_hp - old_hp

class RuntimeManager:
    def __init__(self):
        self._runtimes: Dict[str, CharacterRuntime] = {}
        self._character_runtimes: Dict[int, str] = {}
        self._player_runtimes: Dict[int, str] = {}
        self._table_runtimes: Dict[str, List[str]] = {}

    def create_runtime(self, character_id: int, player_id: int, table_link: str) -> CharacterRuntime:
        if character_id in self._character_runtimes:
            return self.get_runtime_by_character(character_id)
        session = Session()
        character = session.query(Character).filter_by(id=character_id).first()
        session.close()
        if not character:
            raise ValueError(f"Character {character_id} not found")
        resources = json.loads(character.resources) if character.resources else {}
        hp = resources.get('hp', {'current': 20, 'maximum': 20})
        mana = resources.get('mana', {'current': 0, 'maximum': 0})
        energy = resources.get('energy', {'current': 0, 'maximum': 0})
        rage = resources.get('rage', {'current': 0, 'maximum': 0})
        runtime = CharacterRuntime(
            character_id=character_id,
            player_id=player_id,
            table_link=table_link,
            current_hp=hp.get('current', 20),
            max_hp=hp.get('maximum', 20),
            armor_class=character.armor_class,
            speed=character.speed,
            mana=mana.get('current', 0),
            max_mana=mana.get('maximum', 0),
            energy=energy.get('current', 0),
            max_energy=energy.get('maximum', 0),
            rage=rage.get('current', 0),
            max_rage=rage.get('maximum', 0),
            strength=character.str_base,
            dexterity=character.dex_base,
            constitution=character.con_base,
            intelligence=character.int_base,
            wisdom=character.wis_base,
            charisma=character.cha_base,
            str_save=character.str_base // 2 - 5,
            dex_save=character.dex_base // 2 - 5,
            con_save=character.con_base // 2 - 5,
            int_save=character.int_base // 2 - 5,
            wis_save=character.wis_base // 2 - 5,
            cha_save=character.cha_base // 2 - 5
        )
        self._runtimes[runtime.runtime_id] = runtime
        self._character_runtimes[character_id] = runtime.runtime_id
        self._player_runtimes[player_id] = runtime.runtime_id
        if table_link not in self._table_runtimes:
            self._table_runtimes[table_link] = []
        self._table_runtimes[table_link].append(runtime.runtime_id)
        return runtime

    def get_runtime(self, runtime_id: str) -> Optional[CharacterRuntime]:
        return self._runtimes.get(runtime_id)

    def get_runtime_by_character(self, character_id: int) -> Optional[CharacterRuntime]:
        runtime_id = self._character_runtimes.get(character_id)
        if runtime_id:
            return self._runtimes.get(runtime_id)
        return None

    def get_runtime_by_player(self, player_id: int) -> Optional[CharacterRuntime]:
        runtime_id = self._player_runtimes.get(player_id)
        if runtime_id:
            return self._runtimes.get(runtime_id)
        return None

    def get_table_runtimes(self, table_link: str) -> List[CharacterRuntime]:
        runtime_ids = self._table_runtimes.get(table_link, [])
        return [self._runtimes[rid] for rid in runtime_ids if rid in self._runtimes]

    def update_runtime(self, runtime_id: str, **kwargs) -> Optional[CharacterRuntime]:
        runtime = self._runtimes.get(runtime_id)
        if not runtime:
            return None
        for key, value in kwargs.items():
            if hasattr(runtime, key):
                setattr(runtime, key, value)
        runtime.last_updated = datetime.now()
        return runtime

    def delete_runtime(self, runtime_id: str) -> bool:
        runtime = self._runtimes.pop(runtime_id, None)
        if not runtime:
            return False
        self._character_runtimes.pop(runtime.character_id, None)
        self._player_runtimes.pop(runtime.player_id, None)
        if runtime.table_link in self._table_runtimes:
            self._table_runtimes[runtime.table_link] = [
                rid for rid in self._table_runtimes[runtime.table_link] 
                if rid != runtime_id
            ]
        return True

    def save_runtime_to_character(self, runtime_id: str) -> bool:
        runtime = self._runtimes.get(runtime_id)
        if not runtime:
            return False
        session = Session()
        try:
            character = session.query(Character).filter_by(id=runtime.character_id).first()
            if not character:
                return False
            character.set_resource('hp', {
                'current': runtime.current_hp,
                'maximum': runtime.max_hp,
                'temporary': runtime.temporary_hp,
                'regeneration': 0
            })
            character.set_resource('mana', {
                'current': runtime.mana,
                'maximum': runtime.max_mana,
                'temporary': 0,
                'regeneration': 0
            })
            character.set_resource('energy', {
                'current': runtime.energy,
                'maximum': runtime.max_energy,
                'temporary': 0,
                'regeneration': 0
            })
            character.set_resource('rage', {
                'current': runtime.rage,
                'maximum': runtime.max_rage,
                'temporary': 0,
                'regeneration': 0
            })
            character.armor_class = runtime.armor_class
            character.speed = runtime.speed
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error saving runtime: {e}")
            return False
        finally:
            session.close()

runtime_manager = RuntimeManager()

# ============================================================
# 9. COMBAT ENGINE — ТОЛЬКО ВЫЧИСЛЕНИЯ
# ============================================================

class CombatEngine:
    ABILITIES = {
        'fireball': {
            'id': 'fireball',
            'name': 'Fireball',
            'type': 'spell',
            'range': 18,
            'cost': {'action': 1, 'mana': 10},
            'damage': {'dice': '8d6', 'type': 'fire'},
            'save': {'ability': 'dex', 'dc': 15},
            'effects': ['burn'],
            'animation': 'fireball'
        },
        'sword_attack': {
            'id': 'sword_attack',
            'name': 'Sword Attack',
            'type': 'attack',
            'range': 1,
            'cost': {'action': 1},
            'damage': {'dice': '1d8+3', 'type': 'slashing'},
            'save': None,
            'effects': [],
            'animation': 'slash'
        },
        'heal': {
            'id': 'heal',
            'name': 'Heal',
            'type': 'spell',
            'range': 6,
            'cost': {'action': 1, 'mana': 5},
            'damage': {'dice': '2d8+4', 'type': 'healing'},
            'save': None,
            'effects': ['healing'],
            'animation': 'heal'
        },
        'firebolt': {
            'id': 'firebolt',
            'name': 'Firebolt',
            'type': 'spell',
            'range': 12,
            'cost': {'action': 1, 'mana': 3},
            'damage': {'dice': '2d6', 'type': 'fire'},
            'save': None,
            'effects': ['burn'],
            'animation': 'firebolt'
        }
    }
    
    @staticmethod
    def roll_dice(dice_str: str) -> int:
        if '+' in dice_str:
            parts = dice_str.split('+')
            dice_part = parts[0].strip()
            bonus = int(parts[1].strip())
        elif '-' in dice_str:
            parts = dice_str.split('-')
            dice_part = parts[0].strip()
            bonus = -int(parts[1].strip())
        else:
            dice_part = dice_str
            bonus = 0
        if 'd' in dice_part:
            count, sides = dice_part.split('d')
            count = int(count) if count else 1
            sides = int(sides)
            total = sum(random.randint(1, sides) for _ in range(count))
            return total + bonus
        else:
            return int(dice_part) + bonus
    
    @staticmethod
    def calculate_distance(pos1: tuple, pos2: tuple) -> float:
        return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)
    
    @staticmethod
    def check_conditions(runtime: CharacterRuntime) -> tuple:
        if not runtime.is_alive:
            return False, "Персонаж мёртв"
        if runtime.is_unconscious:
            return False, "Персонаж без сознания"
        return True, "OK"
    
    @staticmethod
    def check_resources(runtime: CharacterRuntime, ability: dict) -> tuple:
        cost = ability.get('cost', {})
        if cost.get('action', 0) and runtime.action_used:
            return False, "Основное действие уже использовано"
        if cost.get('bonus_action', 0) and runtime.bonus_action_used:
            return False, "Бонусное действие уже использовано"
        if cost.get('reaction', 0) and runtime.reaction_used:
            return False, "Реакция уже использована"
        if cost.get('mana', 0) and runtime.mana < cost['mana']:
            return False, f"Недостаточно маны (нужно {cost['mana']})"
        return True, "OK"
    
    @staticmethod
    def calculate_saving_throw(target: CharacterRuntime, ability: dict) -> tuple:
        if 'save' not in ability:
            return True, 0
        save_info = ability['save']
        ability_name = save_info['ability']
        dc = save_info['dc']
        save_map = {
            'str': target.str_save,
            'dex': target.dex_save,
            'con': target.con_save,
            'int': target.int_save,
            'wis': target.wis_save,
            'cha': target.cha_save
        }
        mod = save_map.get(ability_name, 0)
        roll = random.randint(1, 20) + mod
        success = roll >= dc
        return success, roll
    
    @staticmethod
    def apply_effects(target: CharacterRuntime, effects: list):
        for effect in effects:
            if effect == 'burn':
                target.active_effects.append({
                    'effect': 'burn',
                    'duration': 3,
                    'damage': '1d6'
                })
    
    @staticmethod
    def resolve_action(
        source_runtime: CharacterRuntime,
        target_runtime: CharacterRuntime,
        ability_id: str,
        table_link: str,
        gm_confirmed: bool = True
    ) -> dict:
        if not gm_confirmed:
            return {
                'success': False,
                'error': 'Действие требует подтверждения ГМ'
            }
        
        ability = CombatEngine.ABILITIES.get(ability_id)
        if not ability:
            return {'success': False, 'error': f"Способность {ability_id} не найдена"}
        
        can_act, msg = CombatEngine.check_conditions(source_runtime)
        if not can_act:
            return {'success': False, 'error': msg}
        
        has_resources, msg = CombatEngine.check_resources(source_runtime, ability)
        if not has_resources:
            return {'success': False, 'error': msg}
        
        source_pos = (source_runtime.x, source_runtime.y)
        target_pos = (target_runtime.x, target_runtime.y)
        distance = CombatEngine.calculate_distance(source_pos, target_pos)
        if distance > ability.get('range', 999):
            return {'success': False, 'error': f"Цель слишком далеко (дистанция: {distance:.1f}, нужно: {ability['range']})"}
        
        hit = False
        save_success = False
        damage = 0
        roll_info = {}
        
        if 'save' in ability:
            save_success, save_roll = CombatEngine.calculate_saving_throw(target_runtime, ability)
            roll_info['save_roll'] = save_roll
            roll_info['save_dc'] = ability['save']['dc']
            roll_info['save_ability'] = ability['save']['ability']
            if not save_success:
                damage = CombatEngine.roll_dice(ability['damage']['dice'])
                hit = True
            else:
                damage = CombatEngine.roll_dice(ability['damage']['dice']) // 2
                hit = True
        else:
            damage = CombatEngine.roll_dice(ability['damage']['dice'])
            hit = True
        
        actual_damage = 0
        if hit and damage > 0:
            if ability['damage']['type'] == 'healing':
                actual_damage = target_runtime.heal(damage)
            else:
                actual_damage = target_runtime.take_damage(damage)
        
        if hit:
            CombatEngine.apply_effects(target_runtime, ability.get('effects', []))
        
        cost = ability.get('cost', {})
        if cost.get('action', 0):
            source_runtime.action_used = True
        if cost.get('mana', 0):
            source_runtime.mana -= cost['mana']
        
        source_runtime.last_updated = datetime.now()
        target_runtime.last_updated = datetime.now()
        
        return {
            'success': True,
            'source': source_runtime.to_dict(),
            'target': target_runtime.to_dict(),
            'ability': {
                'id': ability_id,
                'name': ability['name'],
                'type': ability['type'],
                'animation': ability.get('animation', 'default')
            },
            'roll_info': roll_info,
            'hit': hit,
            'damage': actual_damage,
            'damage_type': ability['damage']['type'],
            'effects_applied': ability.get('effects', []),
            'save_success': save_success if 'save' in ability else None,
            'distance': distance,
            'gm_confirmed': gm_confirmed
        }

# ============================================================
# 10. SESSION MANAGER
# ============================================================

class GameSessionRuntime:
    def __init__(self, session_id: str, name: str, gm_id: int, table_link: str):
        self.session_id = session_id
        self.name = name
        self.gm_id = gm_id
        self.table_link = table_link
        self.state = 'LOBBY'
        self.created_at = datetime.now()
        self.started_at = None
        self.finished_at = None
        self.current_round = 0
        self.current_turn = 0
        self.players: Dict[int, 'PlayerSession'] = {}
        self.runtimes: Dict[str, CharacterRuntime] = {}
        self.logs: List[Dict] = []
        self.is_active = True

    def to_dict(self) -> dict:
        return {
            'session_id': self.session_id,
            'name': self.name,
            'gm_id': self.gm_id,
            'table_link': self.table_link,
            'state': self.state,
            'current_round': self.current_round,
            'current_turn': self.current_turn,
            'players_count': len(self.players),
            'runtimes_count': len(self.runtimes),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None
        }

    def add_player(self, player_session: 'PlayerSession') -> bool:
        if player_session.player_id in self.players:
            return False
        self.players[player_session.player_id] = player_session
        self.log_event('player_joined', player_session.player_id, f"Игрок {player_session.player_name} присоединился")
        return True

    def remove_player(self, player_id: int) -> bool:
        if player_id not in self.players:
            return False
        player = self.players.pop(player_id)
        self.log_event('player_left', player_id, f"Игрок {player.player_name} покинул сессию")
        return True

    def add_runtime(self, runtime: CharacterRuntime) -> bool:
        if runtime.runtime_id in self.runtimes:
            return False
        self.runtimes[runtime.runtime_id] = runtime
        return True

    def log_event(self, event_type: str, actor_id: int, message: str, data: dict = None):
        self.logs.append({
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'actor_id': actor_id,
            'message': message,
            'data': data or {}
        })
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]

class PlayerSession:
    def __init__(self, player_id: int, player_name: str, connection_id: str = None):
        self.player_id = player_id
        self.player_name = player_name
        self.connection_id = connection_id
        self.character_runtime_id: Optional[str] = None
        self.ready = False
        self.online = True

class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, GameSessionRuntime] = {}
        self._table_sessions: Dict[str, str] = {}
        self._player_sessions: Dict[int, str] = {}

    def create_session(self, name: str, gm_id: int, table_link: str) -> GameSessionRuntime:
        session_id = str(uuid.uuid4())
        db_session = Session()
        try:
            game_session = GameSession(
                session_id=session_id,
                name=name,
                gm_id=gm_id,
                table_link=table_link,
                state='LOBBY'
            )
            db_session.add(game_session)
            db_session.commit()
        except Exception as e:
            db_session.rollback()
            raise e
        finally:
            db_session.close()
        runtime = GameSessionRuntime(session_id, name, gm_id, table_link)
        self._sessions[session_id] = runtime
        self._table_sessions[table_link] = session_id
        return runtime

    def get_session(self, session_id: str) -> Optional[GameSessionRuntime]:
        return self._sessions.get(session_id)

    def get_session_by_table(self, table_link: str) -> Optional[GameSessionRuntime]:
        session_id = self._table_sessions.get(table_link)
        if session_id:
            return self._sessions.get(session_id)
        return None

    def add_player_to_session(self, session_id: str, player_id: int, player_name: str, connection_id: str = None) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        player_session = PlayerSession(player_id, player_name, connection_id)
        if session.add_player(player_session):
            self._player_sessions[player_id] = session_id
            return True
        return False

    def remove_player_from_session(self, player_id: int) -> bool:
        session_id = self._player_sessions.get(player_id)
        if not session_id:
            return False
        session = self._sessions.get(session_id)
        if not session:
            return False
        if session.remove_player(player_id):
            self._player_sessions.pop(player_id, None)
            return True
        return False

    def get_session_logs(self, session_id: str, limit: int = 50) -> List[Dict]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session.logs[-limit:]

session_manager = SessionManager()

# ============================================================
# 11. API: CHARACTERS
# ============================================================

@app.post("/api/character/create")
async def create_character(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    session = Session()
    try:
        character = Character(
            name=data.get('name', ''),
            surname=data.get('surname', ''),
            nickname=data.get('nickname', ''),
            race=data.get('race', ''),
            class_name=data.get('class', ''),
            background=data.get('background', ''),
            player_id=user.id,
            portrait=data.get('portrait', ''),
            token=data.get('token', ''),
            gender=data.get('gender', ''),
            age=data.get('age', 0),
            height=data.get('height', 0.0),
            weight=data.get('weight', 0.0),
            hair=data.get('hair', ''),
            eyes=data.get('eyes', ''),
            skin=data.get('skin', ''),
            str_base=data.get('strength', 10),
            dex_base=data.get('dexterity', 10),
            con_base=data.get('constitution', 10),
            int_base=data.get('intelligence', 10),
            wis_base=data.get('wisdom', 10),
            cha_base=data.get('charisma', 10),
            armor_class=data.get('armor_class', 12),
            initiative_bonus=data.get('initiative_bonus', 0),
            speed=data.get('speed', 30),
            proficiency_bonus=data.get('proficiency_bonus', 2),
            level=data.get('level', 1),
            experience=data.get('experience', 0),
            description=data.get('description', ''),
            biography=data.get('biography', ''),
            goals=data.get('goals', ''),
            faction=data.get('faction', ''),
            religion=data.get('religion', ''),
            occupation=data.get('occupation', ''),
            history=data.get('history', ''),
            notes=data.get('notes', ''),
            is_npc=data.get('is_npc', False),
            created_by=user.id
        )
        character.resources = json.dumps({
            'hp': {'current': data.get('max_hp', 20), 'maximum': data.get('max_hp', 20), 'temporary': 0, 'regeneration': 0},
            'mana': {'current': data.get('max_mana', 0), 'maximum': data.get('max_mana', 0), 'temporary': 0, 'regeneration': 0},
            'energy': {'current': data.get('max_energy', 0), 'maximum': data.get('max_energy', 0), 'temporary': 0, 'regeneration': 0},
            'rage': {'current': data.get('max_rage', 0), 'maximum': data.get('max_rage', 0), 'temporary': 0, 'regeneration': 0}
        })
        character.permissions = json.dumps({
            'can_move': True, 'can_attack': True, 'can_cast': True,
            'can_trade': True, 'can_speak': True, 'can_loot': True
        })
        character.inventory = json.dumps([])
        character.equipment = json.dumps({})
        character.effects = json.dumps([])
        character.skills = json.dumps([])
        character.perks = json.dumps([])
        character.achievements = json.dumps([])
        session.add(character)
        session.commit()
        return {"success": True, "character_id": character.id}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/character/{character_id}")
async def get_character(character_id: int):
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        return {"success": True, "character": character.to_dict()}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.put("/api/character/{character_id}")
async def update_character(character_id: int, data: dict):
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        for key, value in data.items():
            if hasattr(character, key):
                setattr(character, key, value)
        session.commit()
        return {"success": True, "character": character.to_dict()}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 12. API: PARSER (БЕЗ ИИ)
# ============================================================

@app.post("/api/parse/character")
async def parse_character(request: Request, data: dict):
    """Парсит карточку персонажа из JSON."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    parsed = ParserService.parse_character(data)
    validation = ParserService.validate_character(parsed)
    
    if not validation['valid']:
        return {
            'success': False,
            'message': 'Ошибки валидации',
            'errors': validation['errors'],
            'parsed_data': parsed
        }
    
    return {
        'success': True,
        'parsed_data': parsed,
        'validation': validation
    }

@app.post("/api/parse/npc")
async def parse_npc(request: Request, data: dict):
    """Парсит карточку NPC из JSON."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    parsed = ParserService.parse_npc(data)
    validation = ParserService.validate_character(parsed)
    
    if not validation['valid']:
        return {
            'success': False,
            'message': 'Ошибки валидации',
            'errors': validation['errors'],
            'parsed_data': parsed
        }
    
    return {
        'success': True,
        'parsed_data': parsed,
        'validation': validation
    }

@app.post("/api/parse/item")
async def parse_item(request: Request, data: dict):
    """Парсит предмет из JSON."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    parsed = ParserService.parse_item(data)
    return {
        'success': True,
        'parsed_data': parsed
    }

@app.post("/api/parse/spell")
async def parse_spell(request: Request, data: dict):
    """Парсит заклинание из JSON."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    parsed = ParserService.parse_spell(data)
    return {
        'success': True,
        'parsed_data': parsed
    }

@app.post("/api/parse/scenario")
async def parse_scenario(request: Request, data: dict):
    """Парсит сценарий из JSON."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    parsed = ParserService.parse_scenario(data)
    return {
        'success': True,
        'parsed_data': parsed,
        'preview': {
            'name': parsed.get('name', ''),
            'locations_count': len(parsed.get('locations', [])),
            'scenes_count': len(parsed.get('scenes', [])),
            'npcs_count': len(parsed.get('npcs', []))
        }
    }

@app.post("/api/parse/json")
async def parse_json(request: Request, data: dict):
    """Парсит JSON-файл."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    content = data.get('content', '')
    if not content:
        return {"success": False, "message": "Нет содержимого для парсинга"}
    
    result = ParserService.parse_json_file(content)
    if 'error' in result:
        return {"success": False, "message": result['error']}
    
    return {
        'success': True,
        'parsed_data': result,
        'keys': list(result.keys()) if isinstance(result, dict) else None
    }

@app.post("/api/parse/validate")
async def validate_character_data(request: Request, data: dict):
    """Валидирует данные персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    validation = ParserService.validate_character(data)
    return {
        'success': True,
        'validation': validation
    }

# ============================================================
# 13. API: RUNTIME
# ============================================================

@app.post("/api/runtime/create")
async def create_runtime(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    character_id = data.get('character_id')
    table_link = data.get('table_link')
    if not character_id or not table_link:
        return {"success": False, "message": "Не указан character_id или table_link"}
    try:
        runtime = runtime_manager.create_runtime(character_id, user.id, table_link)
        return {"success": True, "runtime_id": runtime.runtime_id, "runtime": runtime.to_dict()}
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/runtime/{runtime_id}")
async def get_runtime(runtime_id: str):
    runtime = runtime_manager.get_runtime(runtime_id)
    if not runtime:
        return {"success": False, "message": "Runtime не найден"}
    return {"success": True, "runtime": runtime.to_dict()}

@app.post("/api/runtime/update")
async def update_runtime(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    runtime_id = data.get('runtime_id')
    if not runtime_id:
        return {"success": False, "message": "Не указан runtime_id"}
    update_data = {k: v for k, v in data.items() if k != 'runtime_id'}
    runtime = runtime_manager.update_runtime(runtime_id, **update_data)
    if not runtime:
        return {"success": False, "message": "Runtime не найден"}
    return {"success": True, "runtime": runtime.to_dict()}

@app.post("/api/runtime/save")
async def save_runtime(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    runtime_id = data.get('runtime_id')
    if not runtime_id:
        return {"success": False, "message": "Не указан runtime_id"}
    success = runtime_manager.save_runtime_to_character(runtime_id)
    if not success:
        return {"success": False, "message": "Не удалось сохранить Runtime"}
    return {"success": True, "message": "Runtime сохранён"}

# ============================================================
# 14. API: COMBAT
# ============================================================

@app.post("/api/combat/action")
async def combat_action(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    source_runtime_id = data.get('source_runtime_id')
    target_runtime_id = data.get('target_runtime_id')
    ability_id = data.get('ability_id')
    gm_confirmed = data.get('gm_confirmed', False)
    
    if not source_runtime_id or not target_runtime_id or not ability_id:
        return {"success": False, "message": "Не указаны source_runtime_id, target_runtime_id или ability_id"}
    
    if not gm_confirmed:
        return {
            'success': False,
            'error': 'Требуется подтверждение ГМ'
        }
    
    source_runtime = runtime_manager.get_runtime(source_runtime_id)
    target_runtime = runtime_manager.get_runtime(target_runtime_id)
    
    if not source_runtime:
        return {"success": False, "message": "Источник не найден"}
    if not target_runtime:
        return {"success": False, "message": "Цель не найдена"}
    
    result = CombatEngine.resolve_action(
        source_runtime,
        target_runtime,
        ability_id,
        data.get('table_link', ''),
        gm_confirmed=gm_confirmed
    )
    
    if not result.get('success'):
        return result
    
    table_link = data.get('table_link')
    if table_link and table_link in connections:
        for ws in connections[table_link]:
            try:
                await ws.send_text(json.dumps({'type': 'combat_result', 'result': result}))
            except:
                pass
    
    runtime_manager.save_runtime_to_character(source_runtime_id)
    runtime_manager.save_runtime_to_character(target_runtime_id)
    
    return {'success': True, 'result': result}

@app.get("/api/combat/abilities")
async def get_abilities():
    return {'success': True, 'abilities': list(CombatEngine.ABILITIES.values())}

# ============================================================
# 15. API: SESSION
# ============================================================

@app.post("/api/session/create")
async def create_session(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    if user.role != 'gm':
        return {"success": False, "message": "Только GM может создавать сессии"}
    name = data.get('name')
    table_link = data.get('table_link')
    if not name or not table_link:
        return {"success": False, "message": "Не указаны name или table_link"}
    try:
        session = session_manager.create_session(name, user.id, table_link)
        return {"success": True, "session": session.to_dict()}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/session/join")
async def join_session(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    session_id = data.get('session_id')
    if not session_id:
        return {"success": False, "message": "Не указан session_id"}
    success = session_manager.add_player_to_session(session_id, user.id, user.login, data.get('connection_id'))
    if not success:
        return {"success": False, "message": "Не удалось присоединиться к сессии"}
    session = session_manager.get_session(session_id)
    return {"success": True, "session": session.to_dict() if session else None}

@app.post("/api/session/leave")
async def leave_session(request: Request):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    success = session_manager.remove_player_from_session(user.id)
    if not success:
        return {"success": False, "message": "Не удалось покинуть сессию"}
    return {"success": True, "message": "Вы покинули сессию"}

@app.get("/api/session/{session_id}")
async def get_session_info(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "Сессия не найдена"}
    return {"success": True, "session": session.to_dict(), "players": [p.to_dict() for p in session.players.values()]}

# ============================================================
# 16. API: TABLES, TOKENS, MAP
# ============================================================

@app.post("/api/upload_avatar")
async def upload_avatar(file: UploadFile = File(...)):
    try:
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        filename = f"{secrets.token_hex(8)}.{ext}"
        file_path = os.path.join(AVATAR_DIR, filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"success": True, "url": f"/static/avatars/{filename}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/upload_map")
async def upload_map(request: Request, file: UploadFile = File(...)):
    try:
        user = get_current_user(request)
        if not user or user.role != 'gm':
            return {"success": False, "message": "Доступ только для GM"}
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        filename = f"map_{secrets.token_hex(8)}.{ext}"
        file_path = os.path.join(MAP_DIR, filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"success": True, "url": f"/static/maps/{filename}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/set_map")
async def set_map(data: dict):
    session = Session()
    try:
        table = session.query(GameTable).filter_by(link=data['table_link']).first()
        if not table:
            return {"success": False, "message": "Стол не найден"}
        if 'map_x' in data:
            table.map_x = data['map_x']
        if 'map_y' in data:
            table.map_y = data['map_y']
        if 'map_url' in data:
            table.map_image = data['map_url']
        if 'map_width' in data:
            table.map_width = data['map_width']
        if 'map_height' in data:
            table.map_height = data['map_height']
        if 'map_opacity' in data:
            table.map_opacity = data['map_opacity']
        if 'map_rotation' in data:
            table.map_rotation = data['map_rotation']
        if 'map_layer' in data:
            table.map_layer = data['map_layer']
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'map_update',
                        'map_x': table.map_x,
                        'map_y': table.map_y,
                        'map_url': table.map_image,
                        'map_width': table.map_width,
                        'map_height': table.map_height,
                        'map_opacity': table.map_opacity,
                        'map_rotation': table.map_rotation,
                        'map_layer': table.map_layer
                    }))
                except:
                    pass
        return {"success": True, "message": "Карта обновлена"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/create")
async def create_token(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    session = Session()
    try:
        token = GameToken(
            table_link=data['table_link'],
            name=data.get('name', ''),
            avatar_url=data.get('avatar_url', ''),
            role=data.get('role', 'NPC'),
            owner_name='',
            x=float(data.get('x', 0)),
            y=float(data.get('y', 0)),
            is_visible=True,
            layer=data.get('layer', 'common'),
            description=data.get('description', ''),
            character_id=data.get('character_id', None)
        )
        session.add(token)
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_add',
                        'token_id': token.id,
                        'layer': token.layer,
                        'character_id': token.character_id
                    }))
                except:
                    pass
        return {"success": True, "token_id": token.id}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/update")
async def update_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.name = data.get('name', token.name)
        token.avatar_url = data.get('avatar_url', token.avatar_url)
        token.description = data.get('description', token.description)
        if 'character_id' in data:
            token.character_id = data['character_id']
        if 'layer' in data:
            token.layer = data['layer']
        session.commit()
        return {"success": True, "message": "Токен обновлён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/delete")
async def delete_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        session.delete(token)
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_delete',
                        'token_id': data['token_id']
                    }))
                except:
                    pass
        return {"success": True, "message": "Токен удалён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/move")
async def move_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.x = float(data['x'])
        token.y = float(data['y'])
        session.commit()
        return {"success": True, "message": "Токен перемещён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/update_layer")
async def update_token_layer(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.layer = data['layer']
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_layer_update',
                        'token_id': token.id,
                        'layer': token.layer
                    }))
                except:
                    pass
        return {"success": True, "message": "Слой обновлён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/toggle_visibility")
async def toggle_token_visibility(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.is_visible = not token.is_visible
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_visibility',
                        'token_id': token.id,
                        'is_visible': token.is_visible
                    }))
                except:
                    pass
        return {"success": True, "is_visible": token.is_visible}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/select")
async def select_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.owner_name = data.get('player_name', '')
        session.commit()
        player_game = PlayerGame(
            player_id=data.get('player_id'),
            table_link=data['table_link']
        )
        session.add(player_game)
        session.commit()
        return {"success": True, "message": "Токен выбран"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/token/get/{token_id}")
async def get_token(token_id: int):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=token_id).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        return {"success": True, "token": {
            "id": token.id,
            "name": token.name,
            "avatar_url": token.avatar_url,
            "role": token.role,
            "layer": token.layer,
            "character_id": token.character_id,
            "description": token.description
        }}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/table/create")
async def create_table(data: dict):
    session = Session()
    try:
        link = generate_table_link()
        table = GameTable(
            name=data['name'],
            gm_id=data['gm_id'],
            setting_id=data['setting_id'],
            link=link,
            map_x=0,
            map_y=0,
            map_width=40,
            map_height=30,
            map_opacity=1.0,
            map_layer='map'
        )
        session.add(table)
        session.commit()
        return {"success": True, "link": link}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

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

# ============================================================
# 17. ИНИЦИАЛИЗАЦИЯ
# ============================================================

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

# ============================================================
# 18. СТРАНИЦЫ
# ============================================================

@app.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == 'gm':
            return RedirectResponse(url=f"/gm_dashboard/{user.id}", status_code=303)
        else:
            return RedirectResponse(url=f"/player_dashboard", status_code=303)
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
        response = RedirectResponse(url=f"/gm_dashboard/{user.id}", status_code=303)
    else:
        response = RedirectResponse(url=f"/player_dashboard", status_code=303)
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

@app.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user.id != user_id or user.role != 'gm':
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    try:
        settings = session.query(Settings).all()
        tables = session.query(GameTable).options(joinedload(GameTable.setting)).filter_by(gm_id=user_id, is_active=True).all()
        session.close()
        return templates.TemplateResponse("gm_dashboard.html", {
            "request": request,
            "user": user,
            "settings": settings,
            "tables": tables
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

@app.get("/player_dashboard", response_class=HTMLResponse)
async def player_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    try:
        player_games = session.query(PlayerGame).filter_by(player_id=user.id).all()
        games = []
        for pg in player_games:
            table = session.query(GameTable).filter_by(link=pg.table_link, is_active=True).first()
            if table:
                setting = session.query(Settings).filter_by(id=table.setting_id).first()
                games.append({
                    "name": table.name,
                    "link": table.link,
                    "setting": setting.name if setting else "Неизвестный",
                    "joined_at": pg.joined_at
                })
        session.close()
        return templates.TemplateResponse("player_dashboard.html", {
            "request": request,
            "user": user,
            "games": games
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

@app.get("/join/{link}", response_class=HTMLResponse)
async def join_table(request: Request, link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/join/{link}", status_code=303)
    session = Session()
    try:
        table = session.query(GameTable).filter_by(link=link, is_active=True).first()
        if not table:
            session.close()
            return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
        if user.role == 'gm' and table.gm_id == user.id:
            session.close()
            return RedirectResponse(url=f"/game/{link}", status_code=303)
        tokens = session.query(GameToken).filter_by(
            table_link=link,
            role='player',
            is_active=True,
            owner_name='',
            is_visible=True,
            layer='common'
        ).all()
        session.close()
        return templates.TemplateResponse("join.html", {
            "request": request,
            "user": user,
            "table": table,
            "tokens": tokens
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

@app.get("/game/{table_link}", response_class=HTMLResponse)
async def game_room(request: Request, table_link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    try:
        table = session.query(GameTable).filter_by(link=table_link, is_active=True).first()
        if not table:
            session.close()
            return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
        is_gm = user.role == 'gm' and table.gm_id == user.id
        if not is_gm:
            token = session.query(GameToken).filter_by(table_link=table_link, owner_name=user.login, is_active=True).first()
            if not token:
                session.close()
                return HTMLResponse(content="<h2>⛔ У вас нет доступа к этому столу</h2><a href='/'>На главную</a>", status_code=403)
        if is_gm:
            tokens = session.query(GameToken).filter_by(table_link=table_link, is_active=True).all()
        else:
            tokens = session.query(GameToken).filter_by(table_link=table_link, is_active=True, layer='common').all()
        session.close()
        return templates.TemplateResponse("game.html", {
            "request": request,
            "user": user,
            "table": table,
            "tokens": tokens,
            "is_gm": is_gm,
            "map_data": {
                'url': table.map_image,
                'x': table.map_x or 0.0,
                'y': table.map_y or 0.0,
                'width': table.map_width,
                'height': table.map_height,
                'opacity': table.map_opacity,
                'rotation': table.map_rotation or 0.0,
                'layer': table.map_layer or 'map'
            }
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

# ============================================================
# 19. WEBSOCKET
# ============================================================

@app.websocket("/ws/{table_link}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, table_link: str, player_id: int):
    await websocket.accept()
    if table_link not in connections:
        connections[table_link] = []
    connections[table_link].append(websocket)
    user = get_user_by_id(player_id)
    player_name = user.login if user else str(player_id)
    session = session_manager.get_session_by_table(table_link)
    if not session:
        gm = Session().query(GameTable).filter_by(link=table_link).first()
        if gm:
            session = session_manager.create_session(f"Session for {table_link}", gm.gm_id, table_link)
    if session:
        session_manager.add_player_to_session(session.session_id, player_id, player_name, str(id(websocket)))
        await websocket.send_text(json.dumps({"type": "session_joined", "session": session.to_dict()}))
    db_session = Session()
    token = db_session.query(GameToken).filter_by(table_link=table_link, owner_name=player_name, is_active=True).first()
    db_session.close()
    if token and token.character_id:
        try:
            runtime = runtime_manager.create_runtime(token.character_id, player_id, table_link)
            if session:
                session.add_runtime(runtime)
            await websocket.send_text(json.dumps({"type": "runtime_created", "runtime": runtime.to_dict()}))
        except Exception as e:
            await websocket.send_text(json.dumps({"type": "error", "message": f"Ошибка создания Runtime: {e}"}))
    await websocket.send_text(json.dumps({"type": "system", "text": f"Добро пожаловать в игру {table_link}, {player_name}!"}))
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get('type') == 'move':
                    db_session = Session()
                    token = db_session.query(GameToken).filter_by(id=msg['token_id'], table_link=table_link).first()
                    if token:
                        token.x = msg['x']
                        token.y = msg['y']
                        db_session.commit()
                    db_session.close()
                    for ws in connections.get(table_link, []):
                        try:
                            if ws != websocket:
                                await ws.send_text(json.dumps({'type': 'move', 'token_id': msg['token_id'], 'x': msg['x'], 'y': msg['y']}))
                        except:
                            pass
                elif msg.get('type') == 'chat':
                    for ws in connections.get(table_link, []):
                        try:
                            await ws.send_text(json.dumps({'type': 'chat', 'sender': player_name, 'text': msg['text']}))
                        except:
                            pass
                elif msg.get('type') == 'combat_action':
                    source_runtime_id = msg.get('source_runtime_id')
                    target_runtime_id = msg.get('target_runtime_id')
                    ability_id = msg.get('ability_id')
                    gm_confirmed = msg.get('gm_confirmed', False)
                    if source_runtime_id and target_runtime_id and ability_id:
                        if not gm_confirmed:
                            await websocket.send_text(json.dumps({
                                'type': 'error',
                                'message': 'Требуется подтверждение ГМ'
                            }))
                            continue
                        source_runtime = runtime_manager.get_runtime(source_runtime_id)
                        target_runtime = runtime_manager.get_runtime(target_runtime_id)
                        if source_runtime and target_runtime:
                            result = CombatEngine.resolve_action(
                                source_runtime,
                                target_runtime,
                                ability_id,
                                table_link,
                                gm_confirmed=gm_confirmed
                            )
                            for ws in connections.get(table_link, []):
                                try:
                                    await ws.send_text(json.dumps({'type': 'combat_result', 'result': result}))
                                except:
                                    pass
                            runtime_manager.save_runtime_to_character(source_runtime_id)
                            runtime_manager.save_runtime_to_character(target_runtime_id)
            except json.JSONDecodeError:
                for ws in connections.get(table_link, []):
                    try:
                        await ws.send_text(json.dumps({'type': 'chat', 'sender': player_name, 'text': data}))
                    except:
                        pass
    except WebSocketDisconnect:
        if table_link in connections:
            connections[table_link].remove(websocket)
            if not connections[table_link]:
                del connections[table_link]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
