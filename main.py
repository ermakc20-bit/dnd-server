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
from typing import Dict, Optional, List, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# 1. ENUMS
# ============================================================

class RoomState(str, Enum):
    PREPARATION = "preparation"
    CHARACTER_SELECTION = "character_selection"
    WAITING_FOR_PLAYERS = "waiting_for_players"
    EXPLORATION = "exploration"
    DIALOG = "dialog"
    CHECK = "check"
    COMBAT = "combat"
    CUTSCENE = "cutscene"
    PAUSED = "paused"
    FINISHED = "finished"

class TurnMode(str, Enum):
    FREE = "free"
    INITIATIVE = "initiative"
    SCRIPT = "script"
    GM_CONTROLLED = "gm_controlled"

class TurnEventType(str, Enum):
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    ROUND_STARTED = "round_started"
    ROUND_ENDED = "round_ended"
    COMBAT_STARTED = "combat_started"
    COMBAT_ENDED = "combat_ended"
    PLAYER_SKIPPED = "player_skipped"
    TIMER_EXPIRED = "timer_expired"
    TURN_ORDER_CHANGED = "turn_order_changed"
    PARTICIPANT_ADDED = "participant_added"
    PARTICIPANT_REMOVED = "participant_removed"

class DiceType(str, Enum):
    D2 = "d2"
    D4 = "d4"
    D6 = "d6"
    D8 = "d8"
    D10 = "d10"
    D12 = "d12"
    D20 = "d20"
    D100 = "d100"

class DiceVisibility(str, Enum):
    PUBLIC = "public"
    SECRET = "secret"

class DiceMode(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    CINEMATIC = "cinematic"

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

class GameRoom(Base):
    __tablename__ = 'game_rooms'
    id = Column(Integer, primary_key=True)
    room_id = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, default='')
    gm_id = Column(Integer, ForeignKey('users.id'))
    password_hash = Column(String, nullable=True)
    state = Column(String(20), default=RoomState.PREPARATION)
    turn_mode = Column(String(20), default=TurnMode.FREE)
    turn_timer = Column(Integer, default=0)  # 0 = no limit
    max_players = Column(Integer, default=6)
    is_private = Column(Boolean, default=False)
    current_map = Column(String(255), default='')
    current_scene = Column(String(100), default='')
    current_round = Column(Integer, default=0)
    current_turn = Column(Integer, default=0)
    current_player_id = Column(Integer, nullable=True)
    initiative_order = Column(JSON, default='[]')
    combat_data = Column(JSON, default='{}')
    dice_mode = Column(String(20), default='standard')
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    gm = relationship("User", foreign_keys=[gm_id])
    tokens = relationship("GameToken", backref="room", cascade="all, delete-orphan")
    players = relationship("RoomPlayer", backref="room", cascade="all, delete-orphan")
    characters = relationship("Character", backref="room", cascade="all, delete-orphan")

class RoomPlayer(Base):
    __tablename__ = 'room_players'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    role = Column(String(20), default='player')
    is_ready = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.now)

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
# 3. TURN MANAGER
# ============================================================

@dataclass
class TurnParticipant:
    """Участник очереди ходов."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: int = 0
    name: str = ''
    initiative: int = 0
    is_active: bool = True
    is_skipped: bool = False
    turn_order: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

class TurnManager:
    """
    Универсальная система управления ходами.
    Не знает о Combat, Character, Skill.
    Управляет только очередностью.
    """
    
    def __init__(self, room_id: int):
        self.room_id = room_id
        self.mode: TurnMode = TurnMode.FREE
        self.participants: List[TurnParticipant] = []
        self.current_index: int = -1
        self.current_round: int = 0
        self.timer_seconds: int = 0
        self.timer_active: bool = False
        self._timer_task: Optional[asyncio.Task] = None
        self._event_listeners: Dict[TurnEventType, List[Callable]] = {}
        self._is_combat: bool = False
    
    # ===== УПРАВЛЕНИЕ УЧАСТНИКАМИ =====
    
    def add_participant(self, participant: TurnParticipant) -> bool:
        """Добавляет участника в очередь."""
        if any(p.id == participant.id for p in self.participants):
            return False
        self.participants.append(participant)
        self._sort_participants()
        self._publish_event(TurnEventType.PARTICIPANT_ADDED, {'participant': participant})
        return True
    
    def remove_participant(self, participant_id: str) -> bool:
        """Удаляет участника из очереди."""
        removed = None
        for i, p in enumerate(self.participants):
            if p.id == participant_id:
                removed = self.participants.pop(i)
                break
        
        if removed:
            self._publish_event(TurnEventType.PARTICIPANT_REMOVED, {'participant': removed})
            return True
        return False
    
    def get_participant(self, participant_id: str) -> Optional[TurnParticipant]:
        """Получает участника по ID."""
        for p in self.participants:
            if p.id == participant_id:
                return p
        return None
    
    def get_current_participant(self) -> Optional[TurnParticipant]:
        """Получает текущего участника."""
        if 0 <= self.current_index < len(self.participants):
            return self.participants[self.current_index]
        return None
    
    def _sort_participants(self):
        """Сортирует участников по инициативе."""
        self.participants.sort(key=lambda p: p.initiative, reverse=True)
        for i, p in enumerate(self.participants):
            p.turn_order = i
    
    # ===== УПРАВЛЕНИЕ РЕЖИМАМИ =====
    
    def set_mode(self, mode: TurnMode) -> bool:
        """Устанавливает режим управления ходами."""
        self.mode = mode
        
        if mode == TurnMode.FREE:
            self.current_index = -1
            self.current_round = 0
            self._stop_timer()
        
        self._publish_event(TurnEventType.TURN_ORDER_CHANGED, {'mode': mode.value})
        return True
    
    def start_initiative_mode(self, participants: List[TurnParticipant]) -> bool:
        """Начинает инициативный режим (бой)."""
        self.participants = sorted(participants, key=lambda p: p.initiative, reverse=True)
        for i, p in enumerate(self.participants):
            p.turn_order = i
            p.is_active = True
            p.is_skipped = False
        
        self.current_index = 0
        self.current_round = 1
        self._is_combat = True
        self.mode = TurnMode.INITIATIVE
        
        self._publish_event(TurnEventType.COMBAT_STARTED, {
            'participants': [p.__dict__ for p in self.participants]
        })
        self._publish_event(TurnEventType.ROUND_STARTED, {'round': self.current_round})
        self._start_turn()
        
        return True
    
    def end_combat(self) -> bool:
        """Завершает боевой режим."""
        if not self._is_combat:
            return False
        
        self._is_combat = False
        self.mode = TurnMode.FREE
        self._stop_timer()
        
        self._publish_event(TurnEventType.COMBAT_ENDED, {
            'rounds': self.current_round,
            'total_participants': len(self.participants)
        })
        
        return True
    
    # ===== УПРАВЛЕНИЕ ХОДАМИ =====
    
    def _start_turn(self):
        """Начинает ход текущего участника."""
        if not self._is_combat:
            return
        
        participant = self.get_current_participant()
        if not participant:
            self._next_turn()
            return
        
        if not participant.is_active or participant.is_skipped:
            self._next_turn()
            return
        
        self._publish_event(TurnEventType.TURN_STARTED, {
            'participant': participant.__dict__,
            'round': self.current_round,
            'turn_index': self.current_index
        })
        
        # Запускаем таймер
        if self.timer_seconds > 0:
            self._start_timer()
    
    def _end_turn(self):
        """Завершает ход текущего участника."""
        participant = self.get_current_participant()
        self._stop_timer()
        
        self._publish_event(TurnEventType.TURN_ENDED, {
            'participant': participant.__dict__ if participant else None
        })
        
        self._next_turn()
    
    def _next_turn(self):
        """Переходит к следующему ходу."""
        if not self._is_combat:
            return
        
        self.current_index += 1
        
        # Проверяем, не кончился ли раунд
        if self.current_index >= len(self.participants):
            self.current_round += 1
            self.current_index = 0
            
            # Обновляем активность участников
            for p in self.participants:
                p.is_skipped = False
            
            self._publish_event(TurnEventType.ROUND_ENDED, {'round': self.current_round - 1})
            self._publish_event(TurnEventType.ROUND_STARTED, {'round': self.current_round})
        
        # Проверяем, есть ли активные участники
        active = [p for p in self.participants if p.is_active and not p.is_skipped]
        if not active:
            self.end_combat()
            return
        
        # Начинаем новый ход
        self._start_turn()
    
    def next_turn(self) -> bool:
        """Принудительно переходит к следующему ходу."""
        if self.mode == TurnMode.FREE:
            return False
        self._end_turn()
        return True
    
    def skip_participant(self, participant_id: str) -> bool:
        """Пропускает ход участника."""
        participant = self.get_participant(participant_id)
        if not participant:
            return False
        
        participant.is_skipped = True
        
        self._publish_event(TurnEventType.PLAYER_SKIPPED, {
            'participant': participant.__dict__
        })
        
        # Если текущий участник пропущен, переходим к следующему
        current = self.get_current_participant()
        if current and current.id == participant_id:
            self._end_turn()
        
        return True
    
    def move_participant(self, participant_id: str, new_position: int) -> bool:
        """Перемещает участника в очереди."""
        if new_position < 0 or new_position >= len(self.participants):
            return False
        
        # Находим участника
        current_index = -1
        for i, p in enumerate(self.participants):
            if p.id == participant_id:
                current_index = i
                break
        
        if current_index == -1:
            return False
        
        # Перемещаем
        participant = self.participants.pop(current_index)
        self.participants.insert(new_position, participant)
        
        # Обновляем порядок
        for i, p in enumerate(self.participants):
            p.turn_order = i
        
        self._publish_event(TurnEventType.TURN_ORDER_CHANGED, {
            'participants': [p.__dict__ for p in self.participants]
        })
        
        return True
    
    # ===== ТАЙМЕР =====
    
    def set_timer(self, seconds: int):
        """Устанавливает таймер хода."""
        self.timer_seconds = seconds
    
    def _start_timer(self):
        """Запускает таймер."""
        if self.timer_seconds <= 0:
            return
        
        self.timer_active = True
        self._timer_task = asyncio.create_task(self._timer_loop())
    
    async def _timer_loop(self):
        """Цикл таймера."""
        remaining = self.timer_seconds
        while remaining > 0 and self.timer_active:
            await asyncio.sleep(1)
            remaining -= 1
            
            # Отправляем обновление таймера
            self._publish_event(TurnEventType.TIMER_EXPIRED, {
                'remaining': remaining,
                'participant': self.get_current_participant().__dict__ if self.get_current_participant() else None
            })
        
        if self.timer_active:
            self.timer_active = False
            self._publish_event(TurnEventType.TIMER_EXPIRED, {
                'remaining': 0,
                'participant': self.get_current_participant().__dict__ if self.get_current_participant() else None
            })
            self._end_turn()
    
    def _stop_timer(self):
        """Останавливает таймер."""
        self.timer_active = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
    
    # ===== ГМ КОНТРОЛЬ =====
    
    def add_participant_mid_combat(self, participant: TurnParticipant) -> bool:
        """Добавляет участника во время боя."""
        if self.mode != TurnMode.INITIATIVE and self.mode != TurnMode.GM_CONTROLLED:
            return False
        
        # Добавляем после текущего участника
        insert_index = self.current_index + 1 if self.current_index >= 0 else 0
        self.participants.insert(insert_index, participant)
        for i, p in enumerate(self.participants):
            p.turn_order = i
        
        self._publish_event(TurnEventType.PARTICIPANT_ADDED, {'participant': participant})
        self._publish_event(TurnEventType.TURN_ORDER_CHANGED, {
            'participants': [p.__dict__ for p in self.participants]
        })
        
        return True
    
    def set_gm_order(self, participant_ids: List[str]) -> bool:
        """Устанавливает порядок ходов вручную (GM)."""
        new_participants = []
        for pid in participant_ids:
            for p in self.participants:
                if p.id == pid:
                    new_participants.append(p)
                    break
        
        if len(new_participants) != len(self.participants):
            return False
        
        self.participants = new_participants
        for i, p in enumerate(self.participants):
            p.turn_order = i
        
        self.mode = TurnMode.GM_CONTROLLED
        
        self._publish_event(TurnEventType.TURN_ORDER_CHANGED, {
            'participants': [p.__dict__ for p in self.participants],
            'mode': 'gm_controlled'
        })
        
        return True
    
    # ===== СОБЫТИЯ =====
    
    def subscribe(self, event_type: TurnEventType, callback: Callable):
        """Подписывается на события."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(callback)
    
    def _publish_event(self, event_type: TurnEventType, data: dict):
        """Публикует событие."""
        if event_type in self._event_listeners:
            for callback in self._event_listeners[event_type]:
                try:
                    callback(event_type, data)
                except Exception as e:
                    print(f"Error in turn event callback: {e}")
    
    # ===== СОСТОЯНИЕ =====
    
    def get_state(self) -> dict:
        """Возвращает текущее состояние очереди."""
        current = self.get_current_participant()
        return {
            'mode': self.mode.value,
            'is_combat': self._is_combat,
            'current_round': self.current_round,
            'current_index': self.current_index,
            'total_participants': len(self.participants),
            'current_participant': current.__dict__ if current else None,
            'participants': [p.__dict__ for p in self.participants],
            'timer_seconds': self.timer_seconds,
            'timer_active': self.timer_active
        }

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

async def broadcast_to_room(room_id: int, message: dict):
    for ws in connections.get(room_id, []):
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass

# ============================================================
# 7. TURN MANAGER MANAGER
# ============================================================

class TurnManagerManager:
    """Управляет Turn Manager для всех комнат."""
    
    def __init__(self):
        self._managers: Dict[int, TurnManager] = {}
    
    def get_manager(self, room_id: int) -> Optional[TurnManager]:
        """Получает Turn Manager для комнаты."""
        return self._managers.get(room_id)
    
    def create_manager(self, room_id: int) -> TurnManager:
        """Создаёт Turn Manager для комнаты."""
        manager = TurnManager(room_id)
        self._managers[room_id] = manager
        return manager
    
    def remove_manager(self, room_id: int):
        """Удаляет Turn Manager комнаты."""
        if room_id in self._managers:
            manager = self._managers[room_id]
            manager._stop_timer()
            del self._managers[room_id]

turn_manager_manager = TurnManagerManager()

# ============================================================
# 8. API: TURN MANAGER
# ============================================================

@app.post("/api/turn/initiative")
async def start_initiative(request: Request, data: dict):
    """Начинает инициативный режим (бой)."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id_str = data.get('room_id')
    participants_data = data.get('participants', [])
    
    if not room_id_str:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    if room.gm_id != user.id:
        session.close()
        return {"success": False, "message": "Только GM может начать бой"}
    
    # Создаём или получаем Turn Manager
    manager = turn_manager_manager.get_manager(room.id)
    if not manager:
        manager = turn_manager_manager.create_manager(room.id)
    
    # Устанавливаем таймер из настроек комнаты
    manager.set_timer(room.turn_timer)
    
    # Создаём участников
    participants = []
    for p_data in participants_data:
        participant = TurnParticipant(
            character_id=p_data.get('character_id', 0),
            name=p_data.get('name', 'Участник'),
            initiative=p_data.get('initiative', 0),
            metadata=p_data.get('metadata', {})
        )
        participants.append(participant)
    
    if not participants:
        session.close()
        return {"success": False, "message": "Нет участников для боя"}
    
    # Запускаем инициативный режим
    success = manager.start_initiative_mode(participants)
    
    if success:
        # Обновляем состояние комнаты
        room.state = RoomState.COMBAT
        session.commit()
        session.close()
        
        # Сохраняем участников в комнату
        room.initiative_order = json.dumps([p.__dict__ for p in participants])
        session.commit()
        
        await broadcast_to_room(room.id, {
            'type': 'turn_initiative_started',
            'state': manager.get_state()
        })
        
        return {
            'success': True,
            'state': manager.get_state()
        }
    
    session.close()
    return {"success": False, "message": "Не удалось начать бой"}

@app.post("/api/turn/next")
async def next_turn(request: Request, data: dict):
    """Переходит к следующему ходу."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id_str = data.get('room_id')
    if not room_id_str:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    manager = turn_manager_manager.get_manager(room.id)
    if not manager:
        session.close()
        return {"success": False, "message": "Turn Manager не найден"}
    
    success = manager.next_turn()
    session.close()
    
    if success:
        await broadcast_to_room(room.id, {
            'type': 'turn_updated',
            'state': manager.get_state()
        })
        return {'success': True, 'state': manager.get_state()}
    
    return {"success": False, "message": "Не удалось перейти к следующему ходу"}

@app.post("/api/turn/skip")
async def skip_participant(request: Request, data: dict):
    """Пропускает ход участника."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id_str = data.get('room_id')
    participant_id = data.get('participant_id')
    
    if not room_id_str or not participant_id:
        return {"success": False, "message": "Не указаны room_id или participant_id"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    manager = turn_manager_manager.get_manager(room.id)
    if not manager:
        session.close()
        return {"success": False, "message": "Turn Manager не найден"}
    
    success = manager.skip_participant(participant_id)
    session.close()
    
    if success:
        await broadcast_to_room(room.id, {
            'type': 'turn_updated',
            'state': manager.get_state()
        })
        return {'success': True, 'state': manager.get_state()}
    
    return {"success": False, "message": "Не удалось пропустить ход"}

@app.post("/api/turn/move")
async def move_participant(request: Request, data: dict):
    """Перемещает участника в очереди."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id_str = data.get('room_id')
    participant_id = data.get('participant_id')
    new_position = data.get('new_position')
    
    if not room_id_str or not participant_id or new_position is None:
        return {"success": False, "message": "Не указаны все параметры"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    if room.gm_id != user.id:
        session.close()
        return {"success": False, "message": "Только GM может менять порядок"}
    
    manager = turn_manager_manager.get_manager(room.id)
    if not manager:
        session.close()
        return {"success": False, "message": "Turn Manager не найден"}
    
    success = manager.move_participant(participant_id, new_position)
    session.close()
    
    if success:
        await broadcast_to_room(room.id, {
            'type': 'turn_updated',
            'state': manager.get_state()
        })
        return {'success': True, 'state': manager.get_state()}
    
    return {"success": False, "message": "Не удалось переместить участника"}

@app.post("/api/turn/end_combat")
async def end_combat(request: Request, data: dict):
    """Завершает бой."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id_str = data.get('room_id')
    if not room_id_str:
        return {"success": False, "message": "Не указан room_id"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    if room.gm_id != user.id:
        session.close()
        return {"success": False, "message": "Только GM может завершить бой"}
    
    manager = turn_manager_manager.get_manager(room.id)
    if not manager:
        session.close()
        return {"success": False, "message": "Turn Manager не найден"}
    
    success = manager.end_combat()
    
    if success:
        room.state = RoomState.EXPLORATION
        session.commit()
        session.close()
        
        await broadcast_to_room(room.id, {
            'type': 'combat_ended',
            'state': manager.get_state()
        })
        return {'success': True, 'state': manager.get_state()}
    
    session.close()
    return {"success": False, "message": "Не удалось завершить бой"}

@app.post("/api/turn/timer")
async def set_turn_timer(request: Request, data: dict):
    """Устанавливает таймер хода."""
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return {"success": False, "message": "Только GM может устанавливать таймер"}
    
    room_id_str = data.get('room_id')
    seconds = data.get('seconds', 0)
    
    if not room_id_str:
        return {"success": False, "message": "Не указан room_id"}
    
    if seconds < 0:
        return {"success": False, "message": "Таймер не может быть отрицательным"}
    
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        room.turn_timer = seconds
        session.commit()
        
        manager = turn_manager_manager.get_manager(room.id)
        if manager:
            manager.set_timer(seconds)
        
        await broadcast_to_room(room.id, {
            'type': 'timer_updated',
            'seconds': seconds
        })
        
        return {'success': True, 'message': f'Таймер установлен на {seconds} секунд'}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/turn/state/{room_id}")
async def get_turn_state(room_id: str):
    """Получает состояние очереди ходов."""
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    manager = turn_manager_manager.get_manager(room.id)
    session.close()
    
    if not manager:
        return {'success': True, 'state': {'mode': 'free', 'is_combat': False}}
    
    return {'success': True, 'state': manager.get_state()}

# ============================================================
# 9. СТРАНИЦЫ (СОКРАЩЕНО)
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
    return templates.TemplateResponse("gm_dashboard.html", {"request": request, "user": user})

@app.get("/player_dashboard", response_class=HTMLResponse)
async def player_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("player_dashboard.html", {"request": request, "user": user})

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
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id).first()
    if not room:
        session.close()
        return HTMLResponse(content="<h2>❌ Комната не найдена</h2><a href='/'>На главную</a>", status_code=404)
    
    room_player = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user.id).first()
    if not room_player:
        session.close()
        return HTMLResponse(content="<h2>⛔ Вы не в этой комнате</h2><a href='/'>На главную</a>", status_code=403)
    
    character = None
    if room_player.character_id:
        character = session.query(Character).filter_by(id=room_player.character_id).first()
    
    manager = turn_manager_manager.get_manager(room.id)
    turn_state = manager.get_state() if manager else {'mode': 'free', 'is_combat': False}
    
    session.close()
    
    return templates.TemplateResponse("room.html", {
        "request": request,
        "user": user,
        "room": room,
        "character": character,
        "is_gm": room.gm_id == user.id,
        "turn_state": turn_state
    })

# ============================================================
# 10. WEBSOCKET
# ============================================================

@app.websocket("/ws/room/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str):
    await websocket.accept()
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id).first()
    session.close()
    
    if not room:
        await websocket.send_text(json.dumps({'type': 'error', 'message': 'Комната не найдена'}))
        await websocket.close()
        return
    
    if room.id not in connections:
        connections[room.id] = []
    connections[room.id].append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get('type')
                
                if msg_type == 'chat':
                    await broadcast_to_room(room.id, {
                        'type': 'chat',
                        'username': msg.get('username', 'Unknown'),
                        'text': msg.get('text', ''),
                        'timestamp': datetime.now().isoformat()
                    })
                
                elif msg_type == 'turn_next':
                    session2 = Session()
                    room2 = session2.query(GameRoom).filter_by(room_id=room_id).first()
                    if room2:
                        manager = turn_manager_manager.get_manager(room2.id)
                        if manager:
                            manager.next_turn()
                            await broadcast_to_room(room2.id, {
                                'type': 'turn_updated',
                                'state': manager.get_state()
                            })
                    session2.close()
                
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        if room.id in connections:
            if websocket in connections[room.id]:
                connections[room.id].remove(websocket)
            if not connections[room.id]:
                del connections[room.id]

# ============================================================
# 11. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
