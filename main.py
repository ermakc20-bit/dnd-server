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
import asyncio
from typing import Dict, Optional, List, Any, Set
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# 1. ENUMS И КОНСТАНТЫ
# ============================================================

class UserRole(str, Enum):
    GM = "gm"
    PLAYER = "player"
    OBSERVER = "observer"
    UNAssIGNED = "unassigned"

class RoomState(str, Enum):
    LOBBY = "lobby"
    CHARACTER_SELECTION = "character_selection"
    PLAYING = "playing"
    COMBAT = "combat"
    PAUSED = "paused"
    FINISHED = "finished"

class MessageType(str, Enum):
    # Системные
    SYSTEM = "system"
    ERROR = "error"
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    
    # Игровые
    MOVE = "move"
    CHAT = "chat"
    ROLL = "roll"
    COMBAT_ACTION = "combat_action"
    COMBAT_RESULT = "combat_result"
    INITIATIVE = "initiative"
    TURN_CHANGE = "turn_change"
    
    # Объекты
    TOKEN_CREATE = "token_create"
    TOKEN_UPDATE = "token_update"
    TOKEN_DELETE = "token_delete"
    TOKEN_VISIBILITY = "token_visibility"
    
    # Карта
    MAP_UPDATE = "map_update"
    
    # Состояние
    STATE_UPDATE = "state_update"
    RESYNC = "resync"

# ============================================================
# 2. БАЗА ДАННЫХ
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
    role = Column(String, default=UserRole.UNAssIGNED)
    created_at = Column(DateTime, default=datetime.now)
    last_active = Column(DateTime, default=datetime.now)

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    theme = Column(String)
    background_image = Column(String)

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
    
    portrait = Column(String(255), default='')
    token = Column(String(255), default='')
    gender = Column(String(20), default='')
    age = Column(Integer, default=0)
    
    str_base = Column(Integer, default=10)
    str_bonus = Column(Integer, default=0)
    dex_base = Column(Integer, default=10)
    dex_bonus = Column(Integer, default=0)
    con_base = Column(Integer, default=10)
    con_bonus = Column(Integer, default=0)
    int_base = Column(Integer, default=10)
    int_bonus = Column(Integer, default=0)
    wis_base = Column(Integer, default=10)
    wis_bonus = Column(Integer, default=0)
    cha_base = Column(Integer, default=10)
    cha_bonus = Column(Integer, default=0)
    
    armor_class = Column(Integer, default=12)
    initiative_bonus = Column(Integer, default=0)
    speed = Column(Integer, default=30)
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    
    resources = Column(JSON, default='{}')
    inventory = Column(JSON, default='[]')
    equipment = Column(JSON, default='{}')
    effects = Column(JSON, default='[]')
    skills = Column(JSON, default='[]')
    
    description = Column(Text, default='')
    biography = Column(Text, default='')
    is_npc = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey('users.id'))
    owner = relationship("User", foreign_keys=[created_by])

class GameRoom(Base):
    """Игровая комната — основная единица многопользовательской игры."""
    __tablename__ = 'game_rooms'
    
    id = Column(Integer, primary_key=True)
    room_id = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    gm_id = Column(Integer, ForeignKey('users.id'))
    password_hash = Column(String, nullable=True)
    state = Column(String(20), default=RoomState.LOBBY)
    
    # Настройки комнаты
    max_players = Column(Integer, default=6)
    is_private = Column(Boolean, default=False)
    
    # Игровые данные
    current_map = Column(String(255), default='')
    current_scene = Column(String(100), default='')
    current_round = Column(Integer, default=0)
    current_turn = Column(Integer, default=0)
    current_player_id = Column(Integer, nullable=True)
    initiative_order = Column(JSON, default='[]')
    
    # Состояние
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    
    # Связи
    gm = relationship("User", foreign_keys=[gm_id])
    tokens = relationship("GameToken", backref="room")
    players = relationship("RoomPlayer", backref="room", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict:
        return {
            'room_id': self.room_id,
            'name': self.name,
            'gm_id': self.gm_id,
            'state': self.state,
            'max_players': self.max_players,
            'is_private': self.is_private,
            'current_round': self.current_round,
            'current_turn': self.current_turn,
            'current_player_id': self.current_player_id,
            'initiative_order': json.loads(self.initiative_order) if self.initiative_order else [],
            'players_count': len(self.players),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None
        }

class RoomPlayer(Base):
    """Участник игровой комнаты."""
    __tablename__ = 'room_players'
    
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    role = Column(String(20), default=UserRole.PLAYER)
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
    hp = Column(Integer, default=20)
    max_hp = Column(Integer, default=20)
    ac = Column(Integer, default=12)
    description = Column(String, default='')
    created_at = Column(DateTime, default=datetime.now)
    
    character = relationship("Character", foreign_keys=[character_id])

class SessionLog(Base):
    __tablename__ = 'session_logs'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    timestamp = Column(DateTime, default=datetime.now)
    event_type = Column(String(50))
    actor_id = Column(Integer, nullable=True)
    message = Column(Text)
    data = Column(Text, default='{}')

# ============================================================
# 3. МИГРАЦИЯ
# ============================================================

def migrate_database():
    session = Session()
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if 'game_rooms' not in inspector.get_table_names():
            print("🔄 Создаём таблицы комнат...")
            Base.metadata.create_all(engine)
            print("✅ Таблицы созданы!")
    except Exception as e:
        print(f"⚠️ Ошибка миграции: {e}")
    finally:
        session.close()

Base.metadata.create_all(engine)
migrate_database()

# ============================================================
# 4. FASTAPI
# ============================================================

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AVATAR_DIR = "static/avatars"
MAP_DIR = "static/maps"
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(MAP_DIR, exist_ok=True)

# ============================================================
# 5. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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

def generate_invite_code():
    return secrets.token_hex(4).upper()

# ============================================================
# 6. СЕТЕВАЯ АРХИТЕКТУРА — WEBSOCKET МЕНЕДЖЕР
# ============================================================

class ConnectionManager:
    """Управляет WebSocket-соединениями."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.user_connections: Dict[int, str] = {}  # user_id -> room_id
        self.connection_users: Dict[WebSocket, int] = {}  # websocket -> user_id
        self.connection_rooms: Dict[WebSocket, str] = {}  # websocket -> room_id
    
    async def connect(self, websocket: WebSocket, room_id: str, user_id: int):
        """Подключает пользователя к комнате."""
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        
        self.connection_users[websocket] = user_id
        self.connection_rooms[websocket] = room_id
        self.user_connections[user_id] = room_id
        
        # Логируем подключение
        user = get_user_by_id(user_id)
        if user:
            await self.broadcast(
                room_id,
                {
                    'type': MessageType.SYSTEM,
                    'text': f"🔗 {user.login} подключился к игре"
                },
                exclude=[websocket]
            )
    
    def disconnect(self, websocket: WebSocket):
        """Отключает пользователя."""
        room_id = self.connection_rooms.get(websocket)
        user_id = self.connection_users.get(websocket)
        
        if room_id and room_id in self.active_connections:
            if websocket in self.active_connections[room_id]:
                self.active_connections[room_id].remove(websocket)
            
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        
        if user_id and user_id in self.user_connections:
            del self.user_connections[user_id]
        
        if websocket in self.connection_users:
            del self.connection_users[websocket]
        if websocket in self.connection_rooms:
            del self.connection_rooms[websocket]
    
    async def broadcast(self, room_id: str, message: dict, exclude: List[WebSocket] = None):
        """Отправляет сообщение всем в комнате."""
        if room_id not in self.active_connections:
            return
        
        exclude = exclude or []
        for connection in self.active_connections[room_id]:
            if connection not in exclude:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    pass
    
    async def send_to_user(self, user_id: int, message: dict):
        """Отправляет сообщение конкретному пользователю."""
        room_id = self.user_connections.get(user_id)
        if not room_id:
            return
        
        for connection in self.active_connections.get(room_id, []):
            if self.connection_users.get(connection) == user_id:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    pass
                break
    
    async def send_to_gm(self, room_id: str, message: dict):
        """Отправляет сообщение GM комнаты."""
        # Получаем GM комнаты из БД
        session = Session()
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        session.close()
        if not room or not room.gm_id:
            return
        
        await self.send_to_user(room.gm_id, message)
    
    def get_room_id(self, websocket: WebSocket) -> Optional[str]:
        return self.connection_rooms.get(websocket)
    
    def get_user_id(self, websocket: WebSocket) -> Optional[int]:
        return self.connection_users.get(websocket)
    
    def get_room_users(self, room_id: str) -> List[int]:
        """Возвращает список пользователей в комнате."""
        users = []
        for ws, rid in self.connection_rooms.items():
            if rid == room_id:
                uid = self.connection_users.get(ws)
                if uid:
                    users.append(uid)
        return users
    
    def get_user_count(self, room_id: str) -> int:
        return len(self.active_connections.get(room_id, []))

manager = ConnectionManager()

# ============================================================
# 7. CHARACTER RUNTIME (В ПАМЯТИ)
# ============================================================

@dataclass
class CharacterRuntime:
    runtime_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: int = 0
    player_id: int = 0
    room_id: str = ''
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
        self._room_runtimes: Dict[str, List[str]] = {}

    def create_runtime(self, character_id: int, player_id: int, room_id: str) -> CharacterRuntime:
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
            room_id=room_id,
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
        
        if room_id not in self._room_runtimes:
            self._room_runtimes[room_id] = []
        self._room_runtimes[room_id].append(runtime.runtime_id)
        
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

    def get_room_runtimes(self, room_id: str) -> List[CharacterRuntime]:
        runtime_ids = self._room_runtimes.get(room_id, [])
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
        if runtime.room_id in self._room_runtimes:
            self._room_runtimes[runtime.room_id] = [
                rid for rid in self._room_runtimes[runtime.room_id] 
                if rid != runtime_id
            ]
        return True

    def save_runtime_to_db(self, runtime_id: str) -> bool:
        runtime = self._runtimes.get(runtime_id)
        if not runtime:
            return False
        
        session = Session()
        try:
            character = session.query(Character).filter_by(id=runtime.character_id).first()
            if not character:
                return False
            
            resources = json.loads(character.resources) if character.resources else {}
            resources['hp'] = {
                'current': runtime.current_hp,
                'maximum': runtime.max_hp,
                'temporary': runtime.temporary_hp,
                'regeneration': 0
            }
            resources['mana'] = {
                'current': runtime.mana,
                'maximum': runtime.max_mana,
                'temporary': 0,
                'regeneration': 0
            }
            resources['energy'] = {
                'current': runtime.energy,
                'maximum': runtime.max_energy,
                'temporary': 0,
                'regeneration': 0
            }
            resources['rage'] = {
                'current': runtime.rage,
                'maximum': runtime.max_rage,
                'temporary': 0,
                'regeneration': 0
            }
            character.resources = json.dumps(resources)
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
# 8. COMBAT ENGINE
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
        room_id: str,
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
# 9. ROOM MANAGER
# ============================================================

class RoomManager:
    """Управляет игровыми комнатами."""
    
    def __init__(self):
        self._rooms: Dict[str, GameRoom] = {}
    
    def create_room(self, name: str, gm_id: int, is_private: bool = False, password: str = None) -> GameRoom:
        """Создаёт новую игровую комнату."""
        room_id = generate_room_id()
        
        session = Session()
        try:
            room = GameRoom(
                room_id=room_id,
                name=name,
                gm_id=gm_id,
                is_private=is_private,
                password_hash=hash_password(password) if password else None,
                state=RoomState.LOBBY,
                initiative_order=json.dumps([])
            )
            session.add(room)
            session.commit()
            
            # Добавляем GM как участника
            room_player = RoomPlayer(
                room_id=room.id,
                user_id=gm_id,
                role=UserRole.GM,
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
    
    def get_room_by_id(self, room_id: str) -> Optional[GameRoom]:
        return self.get_room(room_id)
    
    def get_room_by_player(self, user_id: int) -> Optional[GameRoom]:
        session = Session()
        room = session.query(GameRoom).join(RoomPlayer).filter(RoomPlayer.user_id == user_id).first()
        session.close()
        return room
    
    def get_all_rooms(self) -> List[GameRoom]:
        session = Session()
        rooms = session.query(GameRoom).filter(GameRoom.state != RoomState.FINISHED).all()
        session.close()
        return rooms
    
    def join_room(self, room_id: str, user_id: int, password: str = None) -> dict:
        """Присоединяет пользователя к комнате."""
        session = Session()
        try:
            room = session.query(GameRoom).filter_by(room_id=room_id).first()
            if not room:
                return {'success': False, 'error': 'Комната не найдена'}
            
            if room.state == RoomState.FINISHED:
                return {'success': False, 'error': 'Комната завершена'}
            
            if room.is_private and room.password_hash:
                if not password or hash_password(password) != room.password_hash:
                    return {'success': False, 'error': 'Неверный пароль'}
            
            # Проверяем, не присоединён ли уже
            existing = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user_id).first()
            if existing:
                return {'success': True, 'message': 'Вы уже в комнате', 'room': room.to_dict()}
            
            # Проверяем лимит игроков
            players_count = session.query(RoomPlayer).filter_by(room_id=room.id).count()
            if players_count >= room.max_players:
                return {'success': False, 'error': 'Комната заполнена'}
            
            # Добавляем игрока
            user = session.query(User).filter_by(id=user_id).first()
            role = UserRole.PLAYER if user and user.role != UserRole.GM else UserRole.PLAYER
            
            room_player = RoomPlayer(
                room_id=room.id,
                user_id=user_id,
                role=role,
                is_ready=False
            )
            session.add(room_player)
            session.commit()
            
            session.refresh(room)
            return {'success': True, 'room': room.to_dict()}
        except Exception as e:
            session.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            session.close()
    
    def leave_room(self, room_id: str, user_id: int) -> dict:
        """Покидает комнату."""
        session = Session()
        try:
            room = session.query(GameRoom).filter_by(room_id=room_id).first()
            if not room:
                return {'success': False, 'error': 'Комната не найдена'}
            
            room_player = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user_id).first()
            if not room_player:
                return {'success': False, 'error': 'Вы не в этой комнате'}
            
            # Если это GM, передаём права или закрываем комнату
            if room_player.role == UserRole.GM:
                # Проверяем, есть ли другие игроки
                other_players = session.query(RoomPlayer).filter(
                    RoomPlayer.room_id == room.id,
                    RoomPlayer.user_id != user_id
                ).all()
                
                if other_players:
                    # Делаем первого игрока GM
                    other_players[0].role = UserRole.GM
                    session.commit()
                else:
                    # Закрываем комнату
                    room.state = RoomState.FINISHED
                    session.commit()
            
            session.delete(room_player)
            session.commit()
            
            return {'success': True, 'message': 'Вы покинули комнату'}
        except Exception as e:
            session.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            session.close()
    
    def update_room_state(self, room_id: str, state: RoomState) -> bool:
        session = Session()
        try:
            room = session.query(GameRoom).filter_by(room_id=room_id).first()
            if not room:
                return False
            room.state = state
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            return False
        finally:
            session.close()
    
    def get_room_players(self, room_id: str) -> List[dict]:
        session = Session()
        players = session.query(RoomPlayer).filter_by(room_id=room_id).all()
        result = []
        for p in players:
            user = session.query(User).filter_by(id=p.user_id).first()
            result.append({
                'user_id': p.user_id,
                'login': user.login if user else 'Unknown',
                'role': p.role,
                'is_ready': p.is_ready,
                'character_id': p.character_id
            })
        session.close()
        return result

room_manager = RoomManager()

# ============================================================
# 10. API: ROOMS
# ============================================================

@app.post("/api/room/create")
async def create_room(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    if user.role != UserRole.GM:
        return {"success": False, "message": "Только GM может создавать комнаты"}
    
    try:
        room = room_manager.create_room(
            name=data.get('name', 'Новая игра'),
            gm_id=user.id,
            is_private=data.get('is_private', False),
            password=data.get('password')
        )
        return {
            'success': True,
            'room': room.to_dict(),
            'invite_link': f"/join/{room.room_id}"
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/room/join")
async def join_room(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    password = data.get('password')
    
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    result = room_manager.join_room(room_id, user.id, password)
    return result

@app.post("/api/room/leave")
async def leave_room(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    result = room_manager.leave_room(room_id, user.id)
    return result

@app.get("/api/room/{room_id}")
async def get_room_info(room_id: str):
    room = room_manager.get_room(room_id)
    if not room:
        return {"success": False, "message": "Комната не найдена"}
    
    players = room_manager.get_room_players(room_id)
    return {
        'success': True,
        'room': room.to_dict(),
        'players': players
    }

@app.get("/api/rooms")
async def get_all_rooms():
    rooms = room_manager.get_all_rooms()
    return {
        'success': True,
        'rooms': [r.to_dict() for r in rooms]
    }

@app.post("/api/room/start")
async def start_room(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    room = room_manager.get_room(room_id)
    if not room:
        return {"success": False, "message": "Комната не найдена"}
    
    if room.gm_id != user.id:
        return {"success": False, "message": "Только GM может начать игру"}
    
    success = room_manager.update_room_state(room_id, RoomState.PLAYING)
    if not success:
        return {"success": False, "message": "Не удалось начать игру"}
    
    # Уведомляем всех в комнате
    await manager.broadcast(room_id, {
        'type': MessageType.SYSTEM,
        'text': f"🎮 Игра начата! ГМ: {user.login}"
    })
    
    return {"success": True, "message": "Игра начата"}

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
            str_base=data.get('strength', 10),
            dex_base=data.get('dexterity', 10),
            con_base=data.get('constitution', 10),
            int_base=data.get('intelligence', 10),
            wis_base=data.get('wisdom', 10),
            cha_base=data.get('charisma', 10),
            armor_class=data.get('armor_class', 12),
            initiative_bonus=data.get('initiative_bonus', 0),
            speed=data.get('speed', 30),
            level=data.get('level', 1),
            experience=data.get('experience', 0),
            description=data.get('description', ''),
            biography=data.get('biography', ''),
            is_npc=data.get('is_npc', False),
            created_by=user.id
        )
        character.resources = json.dumps({
            'hp': {'current': data.get('max_hp', 20), 'maximum': data.get('max_hp', 20), 'temporary': 0, 'regeneration': 0},
            'mana': {'current': data.get('max_mana', 0), 'maximum': data.get('max_mana', 0), 'temporary': 0, 'regeneration': 0},
            'energy': {'current': data.get('max_energy', 0), 'maximum': data.get('max_energy', 0), 'temporary': 0, 'regeneration': 0},
            'rage': {'current': data.get('max_rage', 0), 'maximum': data.get('max_rage', 0), 'temporary': 0, 'regeneration': 0}
        })
        character.inventory = json.dumps([])
        character.equipment = json.dumps({})
        character.effects = json.dumps([])
        character.skills = json.dumps([])
        
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
        return {"success": True, "character": {
            'id': character.id,
            'name': character.name,
            'surname': character.surname,
            'nickname': character.nickname,
            'race': character.race,
            'class': character.class_name,
            'background': character.background,
            'player_id': character.player_id,
            'portrait': character.portrait,
            'token': character.token,
            'gender': character.gender,
            'age': character.age,
            'strength': character.str_base,
            'dexterity': character.dex_base,
            'constitution': character.con_base,
            'intelligence': character.int_base,
            'wisdom': character.wis_base,
            'charisma': character.cha_base,
            'armor_class': character.armor_class,
            'initiative_bonus': character.initiative_bonus,
            'speed': character.speed,
            'level': character.level,
            'experience': character.experience,
            'description': character.description,
            'biography': character.biography,
            'is_npc': character.is_npc,
            'resources': json.loads(character.resources) if character.resources else {},
            'inventory': json.loads(character.inventory) if character.inventory else [],
            'equipment': json.loads(character.equipment) if character.equipment else {},
            'effects': json.loads(character.effects) if character.effects else []
        }}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 12. API: TOKENS
# ============================================================

@app.post("/api/token/create")
async def create_token(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        # Проверяем, что пользователь в комнате
        room_player = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user.id).first()
        if not room_player:
            return {"success": False, "message": "Вы не в этой комнате"}
        
        token = GameToken(
            room_id=room.id,
            name=data.get('name', 'Токен'),
            avatar_url=data.get('avatar_url', ''),
            role=data.get('role', 'NPC'),
            owner_id=user.id if data.get('role') == 'player' else None,
            character_id=data.get('character_id'),
            x=data.get('x', 0.0),
            y=data.get('y', 0.0),
            is_visible=True,
            layer=data.get('layer', 'common'),
            hp=data.get('hp', 20),
            max_hp=data.get('max_hp', 20),
            ac=data.get('ac', 12),
            description=data.get('description', '')
        )
        session.add(token)
        session.commit()
        
        # Уведомляем всех в комнате
        await manager.broadcast(room_id, {
            'type': MessageType.TOKEN_CREATE,
            'token': {
                'id': token.id,
                'name': token.name,
                'avatar_url': token.avatar_url,
                'role': token.role,
                'x': token.x,
                'y': token.y,
                'layer': token.layer,
                'hp': token.hp,
                'max_hp': token.max_hp,
                'ac': token.ac
            }
        })
        
        return {"success": True, "token_id": token.id}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/move")
async def move_token(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    token_id = data.get('token_id')
    room_id = data.get('room_id')
    x = data.get('x')
    y = data.get('y')
    
    if not token_id or not room_id or x is None or y is None:
        return {"success": False, "message": "Не указаны все параметры"}
    
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=token_id).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        
        # Проверяем права
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        is_gm = room.gm_id == user.id
        is_owner = token.owner_id == user.id
        
        if not is_gm and not is_owner:
            return {"success": False, "message": "Нет прав на перемещение"}
        
        token.x = float(x)
        token.y = float(y)
        session.commit()
        
        # Уведомляем всех в комнате
        await manager.broadcast(room_id, {
            'type': MessageType.MOVE,
            'token_id': token_id,
            'x': token.x,
            'y': token.y,
            'user_id': user.id
        })
        
        return {"success": True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/delete")
async def delete_token(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    token_id = data.get('token_id')
    room_id = data.get('room_id')
    
    if not token_id or not room_id:
        return {"success": False, "message": "Не указаны параметры"}
    
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=token_id).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room or room.gm_id != user.id:
            return {"success": False, "message": "Только GM может удалять токены"}
        
        session.delete(token)
        session.commit()
        
        await manager.broadcast(room_id, {
            'type': MessageType.TOKEN_DELETE,
            'token_id': token_id
        })
        
        return {"success": True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 13. WEBHOOK: COMBAT
# ============================================================

@app.post("/api/combat/action")
async def combat_action(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    source_runtime_id = data.get('source_runtime_id')
    target_runtime_id = data.get('target_runtime_id')
    ability_id = data.get('ability_id')
    room_id = data.get('room_id')
    gm_confirmed = data.get('gm_confirmed', False)
    
    if not source_runtime_id or not target_runtime_id or not ability_id or not room_id:
        return {"success": False, "message": "Не указаны все параметры"}
    
    if not gm_confirmed:
        return {'success': False, 'error': 'Требуется подтверждение ГМ'}
    
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
        room_id,
        gm_confirmed
    )
    
    if not result.get('success'):
        return result
    
    # Сохраняем изменения
    runtime_manager.save_runtime_to_db(source_runtime_id)
    runtime_manager.save_runtime_to_db(target_runtime_id)
    
    # Уведомляем всех в комнате
    await manager.broadcast(room_id, {
        'type': MessageType.COMBAT_RESULT,
        'result': result
    })
    
    return {'success': True, 'result': result}

# ============================================================
# 14. WEBHOOK: INITIATIVE
# ============================================================

@app.post("/api/combat/initiative")
async def set_initiative(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    order = data.get('order', [])
    
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        if room.gm_id != user.id:
            return {"success": False, "message": "Только GM может устанавливать инициативу"}
        
        room.initiative_order = json.dumps(order)
        room.state = RoomState.COMBAT
        session.commit()
        
        await manager.broadcast(room_id, {
            'type': MessageType.INITIATIVE,
            'order': order,
            'current_round': room.current_round,
            'current_turn': room.current_turn
        })
        
        return {"success": True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/combat/next_turn")
async def next_turn(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        if room.gm_id != user.id:
            return {"success": False, "message": "Только GM может менять ход"}
        
        order = json.loads(room.initiative_order) if room.initiative_order else []
        if not order:
            return {"success": False, "message": "Нет инициативы"}
        
        room.current_turn += 1
        if room.current_turn >= len(order):
            room.current_turn = 0
            room.current_round += 1
        
        current_player_id = order[room.current_turn] if room.current_turn < len(order) else None
        room.current_player_id = current_player_id
        
        session.commit()
        
        await manager.broadcast(room_id, {
            'type': MessageType.TURN_CHANGE,
            'current_round': room.current_round,
            'current_turn': room.current_turn,
            'current_player_id': current_player_id,
            'order': order
        })
        
        return {"success": True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 15. API: MAP
# ============================================================

@app.post("/api/map/update")
async def update_map(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    map_url = data.get('map_url')
    map_x = data.get('map_x', 0)
    map_y = data.get('map_y', 0)
    map_width = data.get('map_width', 40)
    map_height = data.get('map_height', 30)
    map_opacity = data.get('map_opacity', 1.0)
    
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        if room.gm_id != user.id:
            return {"success": False, "message": "Только GM может менять карту"}
        
        room.current_map = map_url
        session.commit()
        
        await manager.broadcast(room_id, {
            'type': MessageType.MAP_UPDATE,
            'map_url': map_url,
            'map_x': map_x,
            'map_y': map_y,
            'map_width': map_width,
            'map_height': map_height,
            'map_opacity': map_opacity
        })
        
        return {"success": True}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 16. СТРАНИЦЫ
# ============================================================

@app.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == UserRole.GM:
            return RedirectResponse(url=f"/gm_dashboard", status_code=303)
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
    elif user.role == UserRole.GM:
        response = RedirectResponse(url=f"/gm_dashboard", status_code=303)
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

@app.get("/gm_dashboard", response_class=HTMLResponse)
async def gm_dashboard(request: Request):
    user = get_current_user(request)
    if not user or user.role != UserRole.GM:
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
    
    # Получаем комнаты, в которых участвует игрок
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
    
    room = room_manager.get_room(room_id)
    if not room:
        return HTMLResponse(content="<h2>❌ Комната не найдена</h2><a href='/'>На главную</a>", status_code=404)
    
    # Присоединяем пользователя к комнате
    result = room_manager.join_room(room_id, user.id)
    if not result.get('success'):
        return HTMLResponse(content=f"<h2>❌ {result.get('error', 'Ошибка присоединения')}</h2><a href='/'>На главную</a>", status_code=400)
    
    return RedirectResponse(url=f"/room/{room_id}", status_code=303)

@app.get("/room/{room_id}", response_class=HTMLResponse)
async def room_page(request: Request, room_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/room/{room_id}", status_code=303)
    
    room = room_manager.get_room(room_id)
    if not room:
        return HTMLResponse(content="<h2>❌ Комната не найдена</h2><a href='/'>На главную</a>", status_code=404)
    
    # Проверяем, что пользователь в комнате
    session = Session()
    room_player = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user.id).first()
    session.close()
    
    if not room_player:
        return HTMLResponse(content="<h2>⛔ Вы не в этой комнате</h2><a href='/'>На главную</a>", status_code=403)
    
    # Получаем токены комнаты
    session = Session()
    tokens = session.query(GameToken).filter_by(room_id=room.id).all()
    session.close()
    
    return templates.TemplateResponse("room.html", {
        "request": request,
        "user": user,
        "room": room,
        "tokens": tokens,
        "is_gm": room.gm_id == user.id
    })

# ============================================================
# 17. WEBSOCKET
# ============================================================

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    # Получаем пользователя из cookie
    # В реальном проекте нужно передавать токен в WebSocket
    # Пока используем заглушку
    
    # Получаем комнату
    room = room_manager.get_room(room_id)
    if not room:
        await websocket.accept()
        await websocket.send_text(json.dumps({
            'type': MessageType.ERROR,
            'message': 'Комната не найдена'
        }))
        await websocket.close()
        return
    
    # Принимаем соединение
    await manager.connect(websocket, room_id, 0)  # user_id будет определён позже
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get('type')
                
                if msg_type == MessageType.CHAT:
                    user_id = manager.get_user_id(websocket)
                    user = get_user_by_id(user_id) if user_id else None
                    await manager.broadcast(room_id, {
                        'type': MessageType.CHAT,
                        'user_id': user_id,
                        'username': user.login if user else 'Unknown',
                        'text': msg.get('text', ''),
                        'timestamp': datetime.now().isoformat()
                    })
                
                elif msg_type == MessageType.MOVE:
                    token_id = msg.get('token_id')
                    x = msg.get('x')
                    y = msg.get('y')
                    
                    if token_id and x is not None and y is not None:
                        session = Session()
                        token = session.query(GameToken).filter_by(id=token_id).first()
                        if token:
                            token.x = float(x)
                            token.y = float(y)
                            session.commit()
                        session.close()
                        
                        await manager.broadcast(room_id, {
                            'type': MessageType.MOVE,
                            'token_id': token_id,
                            'x': x,
                            'y': y
                        })
                
                elif msg_type == MessageType.ROLL:
                    user_id = manager.get_user_id(websocket)
                    user = get_user_by_id(user_id) if user_id else None
                    dice = msg.get('dice', '1d20')
                    result = CombatEngine.roll_dice(dice)
                    
                    await manager.broadcast(room_id, {
                        'type': MessageType.ROLL,
                        'user_id': user_id,
                        'username': user.login if user else 'Unknown',
                        'dice': dice,
                        'result': result
                    })
                
                elif msg_type == MessageType.COMBAT_ACTION:
                    # Обработка боевого действия через WebSocket
                    source_runtime_id = msg.get('source_runtime_id')
                    target_runtime_id = msg.get('target_runtime_id')
                    ability_id = msg.get('ability_id')
                    gm_confirmed = msg.get('gm_confirmed', False)
                    
                    # Проверяем, что пользователь GM
                    user_id = manager.get_user_id(websocket)
                    if room.gm_id == user_id:
                        gm_confirmed = True
                    
                    if source_runtime_id and target_runtime_id and ability_id:
                        source_runtime = runtime_manager.get_runtime(source_runtime_id)
                        target_runtime = runtime_manager.get_runtime(target_runtime_id)
                        
                        if source_runtime and target_runtime:
                            result = CombatEngine.resolve_action(
                                source_runtime,
                                target_runtime,
                                ability_id,
                                room_id,
                                gm_confirmed
                            )
                            
                            if result.get('success'):
                                runtime_manager.save_runtime_to_db(source_runtime_id)
                                runtime_manager.save_runtime_to_db(target_runtime_id)
                            
                            await manager.broadcast(room_id, {
                                'type': MessageType.COMBAT_RESULT,
                                'result': result
                            })
                
            except json.JSONDecodeError:
                await manager.send_to_user(manager.get_user_id(websocket), {
                    'type': MessageType.ERROR,
                    'message': 'Неверный формат JSON'
                })
    
    except WebSocketDisconnect:
        user_id = manager.get_user_id(websocket)
        if user_id:
            user = get_user_by_id(user_id)
            await manager.broadcast(room_id, {
                'type': MessageType.SYSTEM,
                'text': f"🔌 {user.login if user else 'Игрок'} отключился"
            })
        manager.disconnect(websocket)

# ============================================================
# 18. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
