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
from typing import Dict, Optional, List, Any, Set
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# 1. ENUMS — СОСТОЯНИЯ КОМНАТЫ
# ============================================================

class RoomState(str, Enum):
    """Состояния игровой комнаты (Game Flow)."""
    PREPARATION = "preparation"              # Подготовка (только GM)
    CHARACTER_SELECTION = "character_selection"  # Выбор персонажей
    WAITING_FOR_PLAYERS = "waiting_for_players"  # Ожидание игроков
    EXPLORATION = "exploration"              # Исследование (основное состояние)
    DIALOG = "dialog"                        # Диалог / катсцена
    CHECK = "check"                          # Проверка (навык, характеристика)
    COMBAT = "combat"                        # Бой
    CUTSCENE = "cutscene"                    # Катсцена (всё заблокировано)
    PAUSED = "paused"                        # Пауза
    FINISHED = "finished"                    # Завершено

class ActionCategory(str, Enum):
    """Категории действий для проверки разрешений."""
    MOVE = "move"
    ATTACK = "attack"
    USE_SKILL = "use_skill"
    USE_ITEM = "use_item"
    TALK = "talk"
    INTERACT = "interact"
    OPEN_DOOR = "open_door"
    READ = "read"
    CHECK = "check"
    CAST_SPELL = "cast_spell"
    DIALOGUE = "dialogue"
    COMBAT_ACTION = "combat_action"
    ADMIN = "admin"

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
    role = Column(String, default='unassigned')
    created_at = Column(DateTime, default=datetime.now)

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), default='')
    nickname = Column(String(100), default='')
    portrait = Column(String(255), default='')
    token = Column(String(255), default='')
    description = Column(Text, default='')
    biography = Column(Text, default='')
    class_name = Column(String(100), default='')
    race = Column(String(100), default='')
    background = Column(String(100), default='')
    alignment = Column(String(50), default='')
    armor_class = Column(Integer, default=10)
    speed = Column(Integer, default=30)
    max_hp = Column(Integer, default=20)
    current_hp = Column(Integer, default=20)
    temporary_hp = Column(Integer, default=0)
    currency = Column(JSON, default='{}')
    stats = Column(JSON, default='{}')
    skills = Column(JSON, default='[]')
    inventory = Column(JSON, default='[]')
    equipment = Column(JSON, default='{}')
    effects = Column(JSON, default='[]')
    player_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'), nullable=True)
    is_npc = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey('users.id'))
    owner = relationship("User", foreign_keys=[created_by])
    player = relationship("User", foreign_keys=[player_id])

class CustomSkill(Base):
    __tablename__ = 'custom_skills'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(255), default='')
    description = Column(Text, default='')
    dice_formula = Column(String(50), default='1d20')
    damage_formula = Column(String(50), default='')
    saving_throw = Column(String(50), default='')
    target_type = Column(String(50), default='single')
    cost_type = Column(String(50), default='action')
    cost_value = Column(Integer, default=1)
    cooldown = Column(Integer, default=0)
    effects = Column(JSON, default='[]')
    animation = Column(String(100), default='')
    created_by = Column(Integer, ForeignKey('users.id'))
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    created_at = Column(DateTime, default=datetime.now)

class GameRoom(Base):
    __tablename__ = 'game_rooms'
    id = Column(Integer, primary_key=True)
    room_id = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, default='')
    gm_id = Column(Integer, ForeignKey('users.id'))
    password_hash = Column(String, nullable=True)
    state = Column(String(20), default=RoomState.PREPARATION)
    max_players = Column(Integer, default=6)
    is_private = Column(Boolean, default=False)
    current_map = Column(String(255), default='')
    current_scene = Column(String(100), default='')
    # Данные для боя
    current_round = Column(Integer, default=0)
    current_turn = Column(Integer, default=0)
    current_player_id = Column(Integer, nullable=True)
    initiative_order = Column(JSON, default='[]')
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    gm = relationship("User", foreign_keys=[gm_id])
    tokens = relationship("GameToken", backref="room", cascade="all, delete-orphan")
    players = relationship("RoomPlayer", backref="room", cascade="all, delete-orphan")
    custom_skills = relationship("CustomSkill", backref="room", cascade="all, delete-orphan")
    characters = relationship("Character", backref="room", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", backref="room", cascade="all, delete-orphan")

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
# 3. GAME STATE MANAGER (СЕРДЦЕ GAME FLOW)
# ============================================================

class GameStateManager:
    """
    Управляет состоянием игровой комнаты.
    Никакой модуль не может изменить состояние напрямую.
    """
    
    # Разрешённые действия для каждого состояния
    _state_permissions: Dict[RoomState, Set[ActionCategory]] = {
        RoomState.PREPARATION: {
            ActionCategory.ADMIN
        },
        RoomState.CHARACTER_SELECTION: {
            ActionCategory.TALK,
            ActionCategory.CHECK
        },
        RoomState.WAITING_FOR_PLAYERS: {
            ActionCategory.TALK
        },
        RoomState.EXPLORATION: {
            ActionCategory.MOVE,
            ActionCategory.TALK,
            ActionCategory.INTERACT,
            ActionCategory.OPEN_DOOR,
            ActionCategory.READ,
            ActionCategory.CHECK,
            ActionCategory.USE_ITEM,
            ActionCategory.USE_SKILL,
            ActionCategory.CAST_SPELL,
            ActionCategory.DIALOGUE
        },
        RoomState.DIALOG: {
            ActionCategory.TALK,
            ActionCategory.DIALOGUE,
            ActionCategory.CHECK
        },
        RoomState.CHECK: {
            ActionCategory.CHECK
        },
        RoomState.COMBAT: {
            ActionCategory.COMBAT_ACTION,
            ActionCategory.USE_ITEM,
            ActionCategory.TALK
        },
        RoomState.CUTSCENE: set(),  # Всё запрещено
        RoomState.PAUSED: set(),    # Всё запрещено
        RoomState.FINISHED: set()   # Всё запрещено
    }
    
    # Допустимые переходы между состояниями
    _allowed_transitions: Dict[RoomState, List[RoomState]] = {
        RoomState.PREPARATION: [RoomState.CHARACTER_SELECTION, RoomState.FINISHED],
        RoomState.CHARACTER_SELECTION: [RoomState.WAITING_FOR_PLAYERS, RoomState.EXPLORATION, RoomState.PREPARATION],
        RoomState.WAITING_FOR_PLAYERS: [RoomState.CHARACTER_SELECTION, RoomState.EXPLORATION],
        RoomState.EXPLORATION: [RoomState.DIALOG, RoomState.CHECK, RoomState.COMBAT, RoomState.PAUSED, RoomState.FINISHED, RoomState.CUTSCENE],
        RoomState.DIALOG: [RoomState.EXPLORATION, RoomState.CHECK, RoomState.COMBAT, RoomState.FINISHED],
        RoomState.CHECK: [RoomState.DIALOG, RoomState.EXPLORATION],
        RoomState.COMBAT: [RoomState.EXPLORATION, RoomState.PAUSED, RoomState.FINISHED],
        RoomState.CUTSCENE: [RoomState.EXPLORATION, RoomState.DIALOG, RoomState.FINISHED],
        RoomState.PAUSED: [RoomState.EXPLORATION, RoomState.COMBAT, RoomState.DIALOG],
        RoomState.FINISHED: []
    }
    
    def __init__(self, room_id: int):
        self.room_id = room_id
        self._state: Optional[RoomState] = None
        self._callbacks: List[callable] = []
    
    @property
    def state(self) -> Optional[RoomState]:
        return self._state
    
    def set_state(self, new_state: RoomState, session: Session, broadcast: bool = True) -> bool:
        """
        Устанавливает новое состояние комнаты.
        Возвращает True, если переход разрешён и выполнен.
        """
        if self._state and new_state not in self._allowed_transitions.get(self._state, []):
            return False
        
        # Обновляем в БД
        room = session.query(GameRoom).filter_by(id=self.room_id).first()
        if not room:
            return False
        
        room.state = new_state.value
        session.commit()
        
        self._state = new_state
        
        # Уведомляем всех в комнате
        if broadcast:
            import asyncio
            asyncio.create_task(self._broadcast_state_change(new_state))
        
        # Вызываем колбэки
        for callback in self._callbacks:
            callback(new_state)
        
        return True
    
    def get_state(self) -> Optional[RoomState]:
        return self._state
    
    def can_execute_action(self, action: ActionCategory, user_role: str = 'player') -> bool:
        """
        Проверяет, разрешено ли действие в текущем состоянии.
        GM всегда может всё.
        """
        if user_role == 'gm':
            return True
        
        if self._state is None:
            return False
        
        allowed = self._state_permissions.get(self._state, set())
        return action in allowed
    
    def lock_actions(self):
        """Блокирует все действия (для CUTSCENE, PAUSED)."""
        # Временно устанавливаем состояние, которое блокирует всё
        pass
    
    def unlock_actions(self):
        """Разблокирует действия."""
        pass
    
    def register_callback(self, callback: callable):
        """Регистрирует callback при смене состояния."""
        self._callbacks.append(callback)
    
    async def _broadcast_state_change(self, new_state: RoomState):
        """Отправляет изменение состояния всем клиентам."""
        from app import manager  # Импорт из основного модуля
        await manager.broadcast_state(self.room_id, new_state)

# ============================================================
# 4. МИГРАЦИЯ
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
# 5. FASTAPI
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
# 6. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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
# 7. ROOM MANAGER
# ============================================================

class RoomManager:
    def __init__(self):
        self._rooms: Dict[str, GameRoom] = {}
        self._state_managers: Dict[int, GameStateManager] = {}

    def create_room(self, name: str, description: str, gm_id: int, max_players: int = 6, is_private: bool = False, password: str = None) -> GameRoom:
        room_id = generate_room_id()
        session = Session()
        try:
            room = GameRoom(
                room_id=room_id,
                name=name,
                description=description,
                gm_id=gm_id,
                max_players=max_players,
                is_private=is_private,
                password_hash=hash_password(password) if password else None,
                state=RoomState.PREPARATION
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
            
            # Создаём GameStateManager для комнаты
            self._state_managers[room.id] = GameStateManager(room.id)
            self._state_managers[room.id]._state = RoomState.PREPARATION
            
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

    def get_room_by_id(self, room_id: int) -> Optional[GameRoom]:
        session = Session()
        room = session.query(GameRoom).filter_by(id=room_id).first()
        session.close()
        return room

    def get_state_manager(self, room_id: int) -> Optional[GameStateManager]:
        return self._state_managers.get(room_id)

    def get_rooms_by_gm(self, gm_id: int) -> List[GameRoom]:
        session = Session()
        rooms = session.query(GameRoom).filter_by(gm_id=gm_id).filter(GameRoom.state != RoomState.FINISHED).all()
        session.close()
        return rooms

    def get_all_rooms(self) -> List[GameRoom]:
        session = Session()
        rooms = session.query(GameRoom).filter(GameRoom.state != RoomState.FINISHED).all()
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
# 8. CONNECTION MANAGER (С ПОДДЕРЖКОЙ STATE)
# ============================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.user_connections: Dict[int, int] = {}
        self.connection_users: Dict[WebSocket, int] = {}
        self.connection_rooms: Dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user_id: int):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        self.connection_users[websocket] = user_id
        self.connection_rooms[websocket] = room_id
        self.user_connections[user_id] = room_id

    def disconnect(self, websocket: WebSocket):
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

    async def broadcast(self, room_id: int, message: dict, exclude: List[WebSocket] = None):
        if room_id not in self.active_connections:
            return
        exclude = exclude or []
        for connection in self.active_connections[room_id]:
            if connection not in exclude:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    pass

    async def broadcast_state(self, room_id: int, new_state: RoomState):
        """Отправляет изменение состояния всем в комнате."""
        await self.broadcast(room_id, {
            'type': 'room_state_changed',
            'state': new_state.value,
            'state_name': new_state.name,
            'timestamp': datetime.now().isoformat()
        })

    def get_user_id(self, websocket: WebSocket) -> Optional[int]:
        return self.connection_users.get(websocket)

    def get_room_id(self, websocket: WebSocket) -> Optional[int]:
        return self.connection_rooms.get(websocket)

manager = ConnectionManager()

# ============================================================
# 9. API: GAME FLOW (УПРАВЛЕНИЕ СОСТОЯНИЕМ)
# ============================================================

@app.post("/api/room/state/change")
async def change_room_state(request: Request, data: dict):
    """Изменяет состояние комнаты (только через GameStateManager)."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    new_state_str = data.get('state')
    
    if not room_id or not new_state_str:
        return {"success": False, "message": "Не указаны room_id или state"}
    
    # Получаем комнату
    room = room_manager.get_room(room_id)
    if not room:
        return {"success": False, "message": "Комната не найдена"}
    
    # Только GM может менять состояние
    if room.gm_id != user.id:
        return {"success": False, "message": "Только GM может менять состояние комнаты"}
    
    try:
        new_state = RoomState(new_state_str)
    except ValueError:
        return {"success": False, "message": f"Неизвестное состояние: {new_state_str}"}
    
    # Получаем State Manager
    state_manager = room_manager.get_state_manager(room.id)
    if not state_manager:
        return {"success": False, "message": "State Manager не найден"}
    
    session = Session()
    try:
        success = state_manager.set_state(new_state, session, broadcast=True)
        if not success:
            return {"success": False, "message": f"Переход из {state_manager.state} в {new_state} запрещён"}
        return {"success": True, "state": new_state.value}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/room/{room_id}/state")
async def get_room_state(room_id: str):
    """Получает текущее состояние комнаты."""
    room = room_manager.get_room(room_id)
    if not room:
        return {"success": False, "message": "Комната не найдена"}
    
    state_manager = room_manager.get_state_manager(room.id)
    if not state_manager:
        return {"success": False, "message": "State Manager не найден"}
    
    return {
        'success': True,
        'state': state_manager.state.value if state_manager.state else None,
        'state_name': state_manager.state.name if state_manager.state else None,
        'allowed_actions': [a.value for a in GameStateManager._state_permissions.get(state_manager.state, set())]
    }

@app.post("/api/action/check")
async def check_action_permission(request: Request, data: dict):
    """Проверяет, разрешено ли действие в текущем состоянии."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    action_str = data.get('action')
    
    if not room_id or not action_str:
        return {"success": False, "message": "Не указаны room_id или action"}
    
    room = room_manager.get_room(room_id)
    if not room:
        return {"success": False, "message": "Комната не найдена"}
    
    state_manager = room_manager.get_state_manager(room.id)
    if not state_manager:
        return {"success": False, "message": "State Manager не найден"}
    
    try:
        action = ActionCategory(action_str)
    except ValueError:
        return {"success": False, "message": f"Неизвестное действие: {action_str}"}
    
    # Определяем роль пользователя
    user_role = 'gm' if room.gm_id == user.id else 'player'
    
    allowed = state_manager.can_execute_action(action, user_role)
    return {
        'success': True,
        'allowed': allowed,
        'state': state_manager.state.value if state_manager.state else None,
        'action': action_str,
        'role': user_role
    }

# ============================================================
# 10. API: КОМНАТЫ (С СОСТОЯНИЕМ)
# ============================================================

@app.post("/api/room/create")
async def create_room(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    if user.role != 'gm':
        return {"success": False, "message": "Только GM может создавать комнаты"}
    
    name = data.get('name', '').strip()
    if not name:
        return {"success": False, "message": "Введите название комнаты"}
    
    try:
        room = room_manager.create_room(
            name=name,
            description=data.get('description', ''),
            gm_id=user.id,
            max_players=data.get('max_players', 6),
            is_private=data.get('is_private', False),
            password=data.get('password')
        )
        return {
            'success': True,
            'room': room.to_dict(),
            'state': RoomState.PREPARATION.value,
            'invite_link': f"/join/{room.room_id}"
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/rooms")
async def get_all_rooms():
    rooms = room_manager.get_all_rooms()
    return {
        'success': True,
        'rooms': [r.to_dict() for r in rooms]
    }

@app.get("/api/rooms/gm/{gm_id}")
async def get_gm_rooms(gm_id: int):
    rooms = room_manager.get_rooms_by_gm(gm_id)
    return {
        'success': True,
        'rooms': [r.to_dict() for r in rooms]
    }

@app.get("/api/room/{room_id}")
async def get_room(room_id: str):
    room = room_manager.get_room(room_id)
    if not room:
        return {"success": False, "message": "Комната не найдена"}
    players = room_manager.get_room_players(room_id)
    
    state_manager = room_manager.get_state_manager(room.id)
    state = state_manager.state if state_manager else None
    
    return {
        'success': True,
        'room': room.to_dict(),
        'players': players,
        'state': state.value if state else None
    }

@app.post("/api/room/join")
async def join_room(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id = data.get('room_id')
    password = data.get('password')
    
    if not room_id:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        if room.state == RoomState.FINISHED:
            return {"success": False, "message": "Комната завершена"}
        
        if room.is_private and room.password_hash:
            if not password or hash_password(password) != room.password_hash:
                return {"success": False, "message": "Неверный пароль"}
        
        existing = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user.id).first()
        if existing:
            return {'success': True, 'message': 'Вы уже в комнате', 'room': room.to_dict()}
        
        players_count = session.query(RoomPlayer).filter_by(room_id=room.id).count()
        if players_count >= room.max_players:
            return {"success": False, "message": "Комната заполнена"}
        
        room_player = RoomPlayer(
            room_id=room.id,
            user_id=user.id,
            role='player',
            is_ready=False
        )
        session.add(room_player)
        session.commit()
        session.refresh(room)
        
        return {'success': True, 'room': room.to_dict()}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

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
    
    state_manager = room_manager.get_state_manager(room.id)
    if not state_manager:
        return {"success": False, "message": "State Manager не найден"}
    
    session = Session()
    try:
        # Переход в EXPLORATION через GameStateManager
        success = state_manager.set_state(RoomState.EXPLORATION, session, broadcast=True)
        if not success:
            return {"success": False, "message": "Не удалось начать игру"}
        
        return {"success": True, "state": RoomState.EXPLORATION.value}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ============================================================
# 11. API: ПЕРСОНАЖИ И НАВЫКИ (С ПРОВЕРКОЙ СОСТОЯНИЯ)
# ============================================================

@app.post("/api/character/create")
async def create_character(request: Request, data: dict):
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
async def update_character(character_id: int, data: dict, request: Request):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        for key, value in data.items():
            if hasattr(character, key):
                setattr(character, key, value)
        
        session.commit()
        
        if character.room_id:
            await manager.broadcast(character.room_id, {
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

@app.post("/api/skill/create")
async def create_custom_skill(request: Request, data: dict):
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
    
    rooms = room_manager.get_rooms_by_gm(user.id)
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
    
    state_manager = room_manager.get_state_manager(room.id)
    state = state_manager.state if state_manager else None
    
    return templates.TemplateResponse("room.html", {
        "request": request,
        "user": user,
        "room": room,
        "characters": characters,
        "skills": skills,
        "tokens": tokens,
        "is_gm": room.gm_id == user.id,
        "current_state": state.value if state else None
    })

# ============================================================
# 13. WEBSOCKET (С ПОДДЕРЖКОЙ STATE)
# ============================================================

@app.websocket("/ws/room/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str):
    await websocket.accept()
    
    room = room_manager.get_room(room_id)
    if not room:
        await websocket.send_text(json.dumps({
            'type': 'error',
            'message': 'Комната не найдена'
        }))
        await websocket.close()
        return
    
    user = get_current_user(websocket)  # В реальном проекте нужно передавать токен
    
    await manager.connect(websocket, room.id, user.id if user else 0)
    
    # Отправляем текущее состояние комнаты
    state_manager = room_manager.get_state_manager(room.id)
    if state_manager and state_manager.state:
        await websocket.send_text(json.dumps({
            'type': 'room_state',
            'state': state_manager.state.value,
            'state_name': state_manager.state.name
        }))
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get('type')
                
                if msg_type == 'chat':
                    await manager.broadcast(room.id, {
                        'type': 'chat',
                        'user_id': msg.get('user_id'),
                        'username': msg.get('username', 'Unknown'),
                        'text': msg.get('text', ''),
                        'timestamp': datetime.now().isoformat()
                    })
                
                elif msg_type == 'move':
                    # Проверяем, разрешено ли движение
                    if state_manager and not state_manager.can_execute_action(ActionCategory.MOVE):
                        await websocket.send_text(json.dumps({
                            'type': 'error',
                            'message': f'Движение запрещено в состоянии {state_manager.state.value}'
                        }))
                        continue
                    
                    await manager.broadcast(room.id, {
                        'type': 'move',
                        'token_id': msg.get('token_id'),
                        'x': msg.get('x'),
                        'y': msg.get('y')
                    })
                
                elif msg_type == 'action':
                    # Проверяем разрешение на действие
                    action_str = msg.get('action_type')
                    if action_str and state_manager:
                        try:
                            action = ActionCategory(action_str)
                            user_role = 'gm' if room.gm_id == user.id else 'player'
                            if not state_manager.can_execute_action(action, user_role):
                                await websocket.send_text(json.dumps({
                                    'type': 'error',
                                    'message': f'Действие {action_str} запрещено в состоянии {state_manager.state.value}'
                                }))
                                continue
                        except ValueError:
                            pass
                    
                    await manager.broadcast(room.id, {
                        'type': 'action_result',
                        'action_type': msg.get('action_type'),
                        'result': msg.get('result', {}),
                        'user_id': msg.get('user_id'),
                        'timestamp': datetime.now().isoformat()
                    })
                    
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ============================================================
# 14. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
