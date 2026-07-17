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

class DiceEventType(str, Enum):
    ROLL_STARTED = "roll_started"
    ANIMATION_STARTED = "animation_started"
    ANIMATION_FINISHED = "animation_finished"
    ROLL_COMPLETED = "roll_completed"
    CRITICAL_SUCCESS = "critical_success"
    CRITICAL_FAILURE = "critical_failure"

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

class DiceHistory(Base):
    """История бросков кубиков."""
    __tablename__ = 'dice_history'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    dice_type = Column(String(10))
    count = Column(Integer, default=1)
    modifier = Column(Integer, default=0)
    formula = Column(String(100))
    results = Column(JSON, default='[]')
    total = Column(Integer, default=0)
    final_total = Column(Integer, default=0)
    is_critical = Column(Boolean, default=False)
    is_fumble = Column(Boolean, default=False)
    visibility = Column(String(20), default='public')
    reason = Column(String(200), default='')
    timestamp = Column(DateTime, default=datetime.now)
    
    user = relationship("User", foreign_keys=[user_id])
    character = relationship("Character", foreign_keys=[character_id])

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
    current_round = Column(Integer, default=0)
    current_turn = Column(Integer, default=0)
    current_player_id = Column(Integer, nullable=True)
    initiative_order = Column(JSON, default='[]')
    combat_data = Column(JSON, default='{}')
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    gm = relationship("User", foreign_keys=[gm_id])
    tokens = relationship("GameToken", backref="room", cascade="all, delete-orphan")
    players = relationship("RoomPlayer", backref="room", cascade="all, delete-orphan")
    characters = relationship("Character", backref="room", cascade="all, delete-orphan")
    dice_history = relationship("DiceHistory", backref="room", cascade="all, delete-orphan")

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
# 3. DICE ENGINE
# ============================================================

@dataclass
class RollRequest:
    """Запрос на бросок кубиков."""
    dice_type: str  # d4, d6, d8, d10, d12, d20, d100
    count: int = 1
    modifier: int = 0
    reason: str = ''
    visibility: DiceVisibility = DiceVisibility.PUBLIC
    user_id: int = 0
    character_id: int = 0
    room_id: int = 0
    
    def to_dict(self) -> dict:
        return {
            'dice_type': self.dice_type,
            'count': self.count,
            'modifier': self.modifier,
            'reason': self.reason,
            'visibility': self.visibility.value,
            'user_id': self.user_id,
            'character_id': self.character_id,
            'room_id': self.room_id
        }

@dataclass
class RollResult:
    """Результат броска кубиков."""
    dice_type: str
    count: int
    modifier: int
    results: List[int]
    total: int
    final_total: int
    is_critical: bool = False
    is_fumble: bool = False
    visibility: DiceVisibility = DiceVisibility.PUBLIC
    reason: str = ''
    user_id: int = 0
    character_id: int = 0
    room_id: int = 0
    roll_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            'roll_id': self.roll_id,
            'dice_type': self.dice_type,
            'count': self.count,
            'modifier': self.modifier,
            'results': self.results,
            'total': self.total,
            'final_total': self.final_total,
            'is_critical': self.is_critical,
            'is_fumble': self.is_fumble,
            'visibility': self.visibility.value,
            'reason': self.reason,
            'user_id': self.user_id,
            'character_id': self.character_id,
            'room_id': self.room_id,
            'timestamp': self.timestamp.isoformat()
        }
    
    def get_animation_data(self) -> dict:
        """Возвращает данные для анимации кубиков."""
        return {
            'roll_id': self.roll_id,
            'dice_type': self.dice_type,
            'count': self.count,
            'results': self.results,
            'total': self.total,
            'final_total': self.final_total,
            'is_critical': self.is_critical,
            'is_fumble': self.is_fumble,
            'color': '#ffd700' if self.is_critical else '#ff4444' if self.is_fumble else '#ffffff'
        }

class DiceEngine:
    """
    Универсальная система бросков кубиков.
    Не знает про D&D, Vampire или другие системы.
    Только кубики.
    """
    
    # Доступные типы кубиков и их максимальные значения
    _DICE_SIDES = {
        'd2': 2,
        'd4': 4,
        'd6': 6,
        'd8': 8,
        'd10': 10,
        'd12': 12,
        'd20': 20,
        'd100': 100
    }
    
    def __init__(self):
        self._event_listeners: Dict[DiceEventType, List[Callable]] = {}
        self._history: List[RollResult] = []
    
    # ===== ОСНОВНЫЕ МЕТОДЫ БРОСКОВ =====
    
    def roll(self, request: RollRequest) -> RollResult:
        """
        Выполняет бросок кубиков.
        Единственный метод для всех бросков.
        """
        # Проверяем валидность dice_type
        dice_type = request.dice_type.lower()
        if dice_type not in self._DICE_SIDES:
            raise ValueError(f"Неизвестный тип кубика: {dice_type}")
        
        max_value = self._DICE_SIDES[dice_type]
        results = [random.randint(1, max_value) for _ in range(request.count)]
        total = sum(results)
        final_total = total + request.modifier
        
        # Определяем критические результаты (только для d20)
        is_critical = False
        is_fumble = False
        if dice_type == 'd20' and request.count == 1:
            is_critical = results[0] == 20
            is_fumble = results[0] == 1
        
        result = RollResult(
            dice_type=dice_type,
            count=request.count,
            modifier=request.modifier,
            results=results,
            total=total,
            final_total=final_total,
            is_critical=is_critical,
            is_fumble=is_fumble,
            visibility=request.visibility,
            reason=request.reason,
            user_id=request.user_id,
            character_id=request.character_id,
            room_id=request.room_id
        )
        
        # Публикуем события
        self._publish_event(DiceEventType.ROLL_STARTED, result)
        
        if is_critical:
            self._publish_event(DiceEventType.CRITICAL_SUCCESS, result)
        elif is_fumble:
            self._publish_event(DiceEventType.CRITICAL_FAILURE, result)
        
        # Сохраняем в историю
        self._history.append(result)
        
        # Публикуем завершение
        self._publish_event(DiceEventType.ROLL_COMPLETED, result)
        
        return result
    
    def roll_formula(self, formula: str, modifier: int = 0, **kwargs) -> RollResult:
        """
        Выполняет бросок по формуле (например: '2d6+4').
        """
        # Парсим формулу
        match = re.match(r'(\d+)?d(\d+)([+-]\d+)?', formula.strip())
        if not match:
            raise ValueError(f"Неверный формат формулы: {formula}")
        
        count = int(match.group(1) or 1)
        dice_type = f"d{match.group(2)}"
        extra_mod = int(match.group(3) or 0) if match.group(3) else 0
        
        request = RollRequest(
            dice_type=dice_type,
            count=count,
            modifier=modifier + extra_mod,
            reason=kwargs.get('reason', formula),
            visibility=kwargs.get('visibility', DiceVisibility.PUBLIC),
            user_id=kwargs.get('user_id', 0),
            character_id=kwargs.get('character_id', 0),
            room_id=kwargs.get('room_id', 0)
        )
        
        return self.roll(request)
    
    # ===== ПАРСИНГ ФОРМУЛ =====
    
    def parse_formula(self, formula: str) -> dict:
        """
        Разбирает формулу на составляющие.
        Возвращает: {'count': int, 'dice_type': str, 'modifier': int}
        """
        match = re.match(r'(\d+)?d(\d+)([+-]\d+)?', formula.strip())
        if not match:
            raise ValueError(f"Неверный формат формулы: {formula}")
        
        return {
            'count': int(match.group(1) or 1),
            'dice_type': f"d{match.group(2)}",
            'modifier': int(match.group(3) or 0) if match.group(3) else 0
        }
    
    # ===== ВИЗУАЛИЗАЦИЯ =====
    
    def get_animation_data(self, result: RollResult) -> dict:
        """Возвращает данные для анимации кубиков."""
        return result.get_animation_data()
    
    # ===== ИСТОРИЯ =====
    
    def get_history(self, limit: int = 50, room_id: int = None) -> List[RollResult]:
        """Возвращает историю бросков."""
        history = self._history
        if room_id:
            history = [r for r in history if r.room_id == room_id]
        return history[-limit:]
    
    def save_history_to_db(self, result: RollResult) -> bool:
        """Сохраняет результат броска в базу данных."""
        session = Session()
        try:
            history_entry = DiceHistory(
                room_id=result.room_id,
                user_id=result.user_id,
                character_id=result.character_id,
                dice_type=result.dice_type,
                count=result.count,
                modifier=result.modifier,
                formula=f"{result.count}{result.dice_type}{'+' + str(result.modifier) if result.modifier else ''}",
                results=json.dumps(result.results),
                total=result.total,
                final_total=result.final_total,
                is_critical=result.is_critical,
                is_fumble=result.is_fumble,
                visibility=result.visibility.value,
                reason=result.reason,
                timestamp=result.timestamp
            )
            session.add(history_entry)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error saving dice history: {e}")
            return False
        finally:
            session.close()
    
    # ===== СОБЫТИЯ =====
    
    def subscribe(self, event_type: DiceEventType, callback: Callable):
        """Подписывается на события бросков."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(callback)
    
    def _publish_event(self, event_type: DiceEventType, data: RollResult):
        """Публикует событие."""
        if event_type in self._event_listeners:
            for callback in self._event_listeners[event_type]:
                try:
                    callback(event_type, data)
                except Exception as e:
                    print(f"Error in dice event callback: {e}")
    
    # ===== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ =====
    
    def get_supported_dice(self) -> List[str]:
        """Возвращает список поддерживаемых типов кубиков."""
        return list(self._DICE_SIDES.keys())
    
    def get_max_value(self, dice_type: str) -> int:
        """Возвращает максимальное значение для типа кубика."""
        return self._DICE_SIDES.get(dice_type.lower(), 0)

# Создаём глобальный экземпляр Dice Engine
dice_engine = DiceEngine()

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
        if 'dice_history' not in inspector.get_table_names():
            print("🔄 Создаём таблицу Dice History...")
            Base.metadata.create_all(engine)
            print("✅ Таблица истории бросков создана!")
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
# 7. API: DICE ENGINE
# ============================================================

@app.post("/api/dice/roll")
async def roll_dice(request: Request, data: dict):
    """Выполняет бросок кубиков."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    dice_type = data.get('dice_type', 'd20')
    count = data.get('count', 1)
    modifier = data.get('modifier', 0)
    reason = data.get('reason', 'Бросок')
    visibility = data.get('visibility', 'public')
    room_id_str = data.get('room_id')
    character_id = data.get('character_id', 0)
    
    try:
        visibility_enum = DiceVisibility(visibility)
    except ValueError:
        visibility_enum = DiceVisibility.PUBLIC
    
    # Получаем комнату
    room_id = 0
    if room_id_str:
        session = Session()
        room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
        if room:
            room_id = room.id
        session.close()
    
    # Создаём запрос
    roll_request = RollRequest(
        dice_type=dice_type,
        count=count,
        modifier=modifier,
        reason=reason,
        visibility=visibility_enum,
        user_id=user.id,
        character_id=character_id,
        room_id=room_id
    )
    
    # Выполняем бросок
    result = dice_engine.roll(roll_request)
    
    # Сохраняем в БД
    dice_engine.save_history_to_db(result)
    
    # Отправляем всем в комнате (если публичный)
    if visibility_enum == DiceVisibility.PUBLIC and room_id_str:
        await broadcast_to_room(room_id, {
            'type': 'dice_roll',
            'result': result.to_dict(),
            'animation': result.get_animation_data()
        })
    
    return {
        'success': True,
        'result': result.to_dict(),
        'animation': result.get_animation_data()
    }

@app.post("/api/dice/roll/formula")
async def roll_dice_formula(request: Request, data: dict):
    """Выполняет бросок по формуле (например: 2d6+4)."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    formula = data.get('formula', '1d20')
    modifier = data.get('modifier', 0)
    reason = data.get('reason', formula)
    visibility = data.get('visibility', 'public')
    room_id_str = data.get('room_id')
    character_id = data.get('character_id', 0)
    
    try:
        visibility_enum = DiceVisibility(visibility)
    except ValueError:
        visibility_enum = DiceVisibility.PUBLIC
    
    room_id = 0
    if room_id_str:
        session = Session()
        room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
        if room:
            room_id = room.id
        session.close()
    
    try:
        result = dice_engine.roll_formula(
            formula=formula,
            modifier=modifier,
            reason=reason,
            visibility=visibility_enum,
            user_id=user.id,
            character_id=character_id,
            room_id=room_id
        )
        
        dice_engine.save_history_to_db(result)
        
        if visibility_enum == DiceVisibility.PUBLIC and room_id_str:
            await broadcast_to_room(room_id, {
                'type': 'dice_roll',
                'result': result.to_dict(),
                'animation': result.get_animation_data()
            })
        
        return {
            'success': True,
            'result': result.to_dict(),
            'animation': result.get_animation_data()
        }
    except ValueError as e:
        return {"success": False, "message": str(e)}

@app.get("/api/dice/history/{room_id}")
async def get_dice_history(room_id: str, limit: int = 50):
    """Получает историю бросков в комнате."""
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        history = session.query(DiceHistory).filter_by(room_id=room.id).order_by(
            DiceHistory.timestamp.desc()
        ).limit(limit).all()
        
        return {
            'success': True,
            'history': [
                {
                    'id': h.id,
                    'dice_type': h.dice_type,
                    'count': h.count,
                    'modifier': h.modifier,
                    'formula': h.formula,
                    'results': json.loads(h.results) if h.results else [],
                    'total': h.total,
                    'final_total': h.final_total,
                    'is_critical': h.is_critical,
                    'is_fumble': h.is_fumble,
                    'visibility': h.visibility,
                    'reason': h.reason,
                    'timestamp': h.timestamp.isoformat()
                }
                for h in history
            ]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/dice/types")
async def get_dice_types():
    """Возвращает все поддерживаемые типы кубиков."""
    return {
        'success': True,
        'dice_types': [
            {'value': d, 'label': d.upper(), 'max_value': dice_engine.get_max_value(d)}
            for d in dice_engine.get_supported_dice()
        ]
    }

@app.post("/api/dice/parse")
async def parse_dice_formula(data: dict):
    """Разбирает формулу броска."""
    formula = data.get('formula', '')
    if not formula:
        return {"success": False, "message": "Не указана формула"}
    
    try:
        parsed = dice_engine.parse_formula(formula)
        return {
            'success': True,
            'parsed': parsed
        }
    except ValueError as e:
        return {"success": False, "message": str(e)}

# ============================================================
# 8. WEBSOCKET HELPER
# ============================================================

async def broadcast_to_room(room_id: int, message: dict):
    """Отправляет сообщение всем в комнате."""
    for ws in connections.get(room_id, []):
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass

# ============================================================
# 9. БЫСТРЫЙ СТАРТ
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
    
    session.close()
    
    return templates.TemplateResponse("room.html", {
        "request": request,
        "user": user,
        "room": room,
        "character": character,
        "is_gm": room.gm_id == user.id
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
                
                elif msg_type == 'dice_roll':
                    # Бросок кубиков через WebSocket
                    dice_type = msg.get('dice_type', 'd20')
                    count = msg.get('count', 1)
                    modifier = msg.get('modifier', 0)
                    reason = msg.get('reason', 'Бросок')
                    visibility = msg.get('visibility', 'public')
                    character_id = msg.get('character_id', 0)
                    
                    try:
                        visibility_enum = DiceVisibility(visibility)
                    except ValueError:
                        visibility_enum = DiceVisibility.PUBLIC
                    
                    roll_request = RollRequest(
                        dice_type=dice_type,
                        count=count,
                        modifier=modifier,
                        reason=reason,
                        visibility=visibility_enum,
                        user_id=msg.get('user_id', 0),
                        character_id=character_id,
                        room_id=room.id
                    )
                    
                    result = dice_engine.roll(roll_request)
                    dice_engine.save_history_to_db(result)
                    
                    if visibility_enum == DiceVisibility.PUBLIC:
                        await broadcast_to_room(room.id, {
                            'type': 'dice_roll',
                            'result': result.to_dict(),
                            'animation': result.get_animation_data()
                        })
                    else:
                        # Секретный бросок — только GM
                        gm = session.query(RoomPlayer).filter_by(room_id=room.id, role='gm').first()
                        if gm:
                            await websocket.send_text(json.dumps({
                                'type': 'dice_roll_secret',
                                'result': result.to_dict()
                            }))
                
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
