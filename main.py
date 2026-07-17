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

class DiceMode(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    CINEMATIC = "cinematic"

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
    dice_mode = Column(String(20), default='standard')

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
    dice_mode = Column(String(20), default='standard')
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
# 3. CINEMATIC DICE SYSTEM (СИСТЕМА КИНОШНЫХ КУБИКОВ)
# ============================================================

@dataclass
class DiceAnimationConfig:
    """Конфигурация анимации кубиков."""
    mode: DiceMode = DiceMode.STANDARD
    duration: float = 2.5
    roll_count: int = 10
    physics_steps: int = 30
    camera_zoom: float = 1.0
    slow_motion: bool = False
    sound_enabled: bool = True

@dataclass
class DiceAnimationFrame:
    """Кадр анимации кубика."""
    frame: int
    dice_values: List[int]
    positions: List[tuple]
    rotations: List[float]
    scales: List[float]
    opacities: List[float]
    is_final: bool = False
    total: int = 0
    is_critical: bool = False
    is_fumble: bool = False
    camera_x: float = 0
    camera_y: float = 0
    camera_zoom: float = 1.0

class CinematicDiceSystem:
    """
    Система кинематографической визуализации кубиков.
    Получает данные от Universal Dice Engine.
    Создаёт анимацию на игровом столе.
    """
    
    # Конфигурации режимов
    _MODES = {
        DiceMode.FAST: {
            'duration': 1.0,
            'roll_count': 5,
            'physics_steps': 10,
            'camera_zoom': 1.0,
            'slow_motion': False
        },
        DiceMode.STANDARD: {
            'duration': 2.5,
            'roll_count': 10,
            'physics_steps': 30,
            'camera_zoom': 1.0,
            'slow_motion': False
        },
        DiceMode.CINEMATIC: {
            'duration': 4.5,
            'roll_count': 20,
            'physics_steps': 50,
            'camera_zoom': 1.3,
            'slow_motion': True
        }
    }
    
    def __init__(self):
        self._event_listeners: Dict[DiceEventType, List[Callable]] = {}
        self._current_animation: Optional[DiceAnimationFrame] = None
    
    def get_mode_config(self, mode: DiceMode) -> dict:
        """Возвращает конфигурацию для режима."""
        return self._MODES.get(mode, self._MODES[DiceMode.STANDARD])
    
    def generate_animation_frames(self, result: RollResult, mode: DiceMode = DiceMode.STANDARD) -> List[DiceAnimationFrame]:
        """
        Генерирует кадры анимации для броска.
        """
        config = self.get_mode_config(mode)
        total_frames = int(config['duration'] * 20)  # 20 FPS
        frames = []
        
        # Данные кубиков
        dice_count = result.count
        dice_values = result.results
        
        # Начальное состояние (кубики появляются)
        start_positions = []
        start_rotations = []
        start_scales = []
        start_opacities = []
        
        for i in range(dice_count):
            angle = (i / dice_count) * 2 * math.pi
            radius = 50 + random.uniform(-20, 20)
            x = math.cos(angle) * radius + random.uniform(-30, 30)
            y = -math.sin(angle) * radius + random.uniform(-30, 30) - 200  # Появляются сверху
            start_positions.append((x, y))
            start_rotations.append(random.uniform(0, 360))
            start_scales.append(0.1)
            start_opacities.append(0)
        
        # Добавляем начальный кадр
        frames.append(DiceAnimationFrame(
            frame=0,
            dice_values=dice_values,
            positions=start_positions,
            rotations=start_rotations,
            scales=start_scales,
            opacities=start_opacities,
            is_final=False
        ))
        
        # Промежуточные кадры (физика)
        for frame in range(1, total_frames):
            progress = frame / total_frames
            
            # Вычисляем позиции с физикой
            positions = []
            rotations = []
            scales = []
            opacities = []
            
            for i in range(dice_count):
                # Падение с ускорением
                fall_progress = min(1, progress * 1.5)
                if mode == DiceMode.CINEMATIC:
                    fall_progress = min(1, progress * 1.2)
                
                # Синусоидальное движение для реалистичности
                bounce = abs(math.sin(fall_progress * math.pi * 3)) * 30 * (1 - fall_progress)
                
                # Основная позиция
                target_x = (i - (dice_count - 1) / 2) * 60 + random.uniform(-5, 5) * (1 - progress)
                target_y = -math.cos(fall_progress * math.pi * 1.5) * 100 + 20 + bounce
                
                positions.append((target_x, target_y))
                
                # Вращение
                rot = frame * (2 + i * 0.5) + random.uniform(-10, 10)
                rotations.append(rot)
                
                # Масштаб
                if mode == DiceMode.CINEMATIC and frame < total_frames * 0.3:
                    scale = 0.1 + 0.9 * (progress / 0.3)  # Постепенное появление
                else:
                    scale = min(1, 0.3 + 0.7 * (1 - math.exp(-progress * 3)))
                scales.append(min(1, scale))
                
                # Прозрачность
                if mode == DiceMode.FAST:
                    opacity = min(1, progress * 4)
                else:
                    opacity = min(1, progress * 3)
                opacities.append(opacity)
            
            # Финальный кадр
            is_final = (frame == total_frames - 1)
            
            frames.append(DiceAnimationFrame(
                frame=frame,
                dice_values=dice_values,
                positions=positions,
                rotations=rotations,
                scales=scales,
                opacities=opacities,
                is_final=is_final,
                total=result.final_total,
                is_critical=result.is_critical,
                is_fumble=result.is_fumble,
                camera_x=0,
                camera_y=0,
                camera_zoom=config['camera_zoom']
            ))
        
        # Финальный кадр с подсветкой результата
        final_positions = []
        final_rotations = []
        for i in range(dice_count):
            final_x = (i - (dice_count - 1) / 2) * 70
            final_y = random.uniform(-5, 5)
            final_positions.append((final_x, final_y))
            final_rotations.append(random.choice([0, 90, 180, 270]))
        
        frames.append(DiceAnimationFrame(
            frame=total_frames,
            dice_values=dice_values,
            positions=final_positions,
            rotations=final_rotations,
            scales=[1.0] * dice_count,
            opacities=[1.0] * dice_count,
            is_final=True,
            total=result.final_total,
            is_critical=result.is_critical,
            is_fumble=result.is_fumble,
            camera_x=0,
            camera_y=0,
            camera_zoom=config['camera_zoom'] * 1.2 if result.is_critical or result.is_fumble else config['camera_zoom']
        ))
        
        return frames
    
    def generate_sound_events(self, mode: DiceMode, is_critical: bool = False, is_fumble: bool = False) -> List[dict]:
        """Генерирует звуковые события для анимации."""
        events = []
        
        if mode == DiceMode.FAST:
            events.append({'time': 0.0, 'sound': 'dice_roll.wav', 'volume': 0.5})
            events.append({'time': 0.5, 'sound': 'dice_land.wav', 'volume': 0.3})
        elif mode == DiceMode.STANDARD:
            events.append({'time': 0.0, 'sound': 'dice_roll.wav', 'volume': 0.7})
            events.append({'time': 0.5, 'sound': 'dice_bounce.wav', 'volume': 0.4})
            events.append({'time': 1.2, 'sound': 'dice_bounce.wav', 'volume': 0.3})
            events.append({'time': 2.0, 'sound': 'dice_land.wav', 'volume': 0.5})
        else:  # CINEMATIC
            events.append({'time': 0.0, 'sound': 'dice_roll_cinematic.wav', 'volume': 0.8})
            events.append({'time': 0.8, 'sound': 'dice_bounce.wav', 'volume': 0.5})
            events.append({'time': 1.6, 'sound': 'dice_bounce.wav', 'volume': 0.4})
            events.append({'time': 2.4, 'sound': 'dice_bounce.wav', 'volume': 0.3})
            events.append({'time': 3.5, 'sound': 'dice_land_cinematic.wav', 'volume': 0.6})
        
        # Критические звуки
        if is_critical:
            events.append({'time': 3.8, 'sound': 'critical_success.wav', 'volume': 1.0})
        if is_fumble:
            events.append({'time': 3.8, 'sound': 'critical_failure.wav', 'volume': 1.0})
        
        return events
    
    def get_animation_data(self, result: RollResult, mode: DiceMode) -> dict:
        """Возвращает полные данные анимации."""
        frames = self.generate_animation_frames(result, mode)
        sounds = self.generate_sound_events(mode, result.is_critical, result.is_fumble)
        
        return {
            'roll_id': result.roll_id,
            'mode': mode.value,
            'duration': self._MODES[mode]['duration'],
            'frames': [f.__dict__ for f in frames],
            'sounds': sounds,
            'result': result.to_dict(),
            'critical_type': 'critical_success' if result.is_critical else 'critical_failure' if result.is_fumble else None
        }

# Создаём глобальный экземпляр
cinematic_dice = CinematicDiceSystem()

# ============================================================
# 4. DICE ENGINE (ОБНОВЛЁННЫЙ ДЛЯ CINEMATIC)
# ============================================================

@dataclass
class RollRequest:
    """Запрос на бросок кубиков."""
    dice_type: str
    count: int = 1
    modifier: int = 0
    reason: str = ''
    visibility: DiceVisibility = DiceVisibility.PUBLIC
    user_id: int = 0
    character_id: int = 0
    room_id: int = 0
    advantage: bool = False
    disadvantage: bool = False
    mode: DiceMode = DiceMode.STANDARD
    custom_modifiers: List[Dict] = field(default_factory=list)

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
    mode: DiceMode = DiceMode.STANDARD

class DiceEngine:
    """Универсальная система бросков кубиков с поддержкой кинематографического режима."""
    
    _DICE_SIDES = {
        'd2': 2, 'd4': 4, 'd6': 6, 'd8': 8,
        'd10': 10, 'd12': 12, 'd20': 20, 'd100': 100
    }
    
    def __init__(self):
        self._history: List[RollResult] = []
    
    def roll(self, request: RollRequest) -> RollResult:
        """Выполняет бросок кубиков."""
        dice_type = request.dice_type.lower()
        if dice_type not in self._DICE_SIDES:
            raise ValueError(f"Неизвестный тип кубика: {dice_type}")
        
        max_value = self._DICE_SIDES[dice_type]
        
        results = []
        if request.advantage or request.disadvantage:
            if dice_type == 'd20' and request.count == 1:
                roll1 = random.randint(1, max_value)
                roll2 = random.randint(1, max_value)
                if request.advantage:
                    results = [max(roll1, roll2)]
                else:
                    results = [min(roll1, roll2)]
            else:
                results = [random.randint(1, max_value) for _ in range(request.count)]
        else:
            results = [random.randint(1, max_value) for _ in range(request.count)]
        
        total = sum(results)
        final_total = total + request.modifier
        
        is_critical = False
        is_fumble = False
        if dice_type == 'd20' and request.count == 1:
            roll = results[0] if results else 0
            is_critical = roll == 20
            is_fumble = roll == 1
        
        return RollResult(
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
            room_id=request.room_id,
            mode=request.mode
        )
    
    def roll_formula(self, formula: str, **kwargs) -> RollResult:
        """Выполняет бросок по формуле."""
        match = re.match(r'(\d+)?d(\d+)([+-]\d+)?', formula.strip())
        if not match:
            raise ValueError(f"Неверный формат формулы: {formula}")
        
        count = int(match.group(1) or 1)
        dice_type = f"d{match.group(2)}"
        extra_mod = int(match.group(3) or 0) if match.group(3) else 0
        
        request = RollRequest(
            dice_type=dice_type,
            count=count,
            modifier=extra_mod + kwargs.get('modifier', 0),
            reason=kwargs.get('reason', formula),
            visibility=kwargs.get('visibility', DiceVisibility.PUBLIC),
            user_id=kwargs.get('user_id', 0),
            character_id=kwargs.get('character_id', 0),
            room_id=kwargs.get('room_id', 0),
            advantage=kwargs.get('advantage', False),
            disadvantage=kwargs.get('disadvantage', False),
            mode=kwargs.get('mode', DiceMode.STANDARD),
            custom_modifiers=kwargs.get('custom_modifiers', [])
        )
        return self.roll(request)

dice_engine = DiceEngine()

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
        if 'dice_history' not in inspector.get_table_names():
            print("🔄 Создаём таблицу Dice History...")
            Base.metadata.create_all(engine)
            print("✅ Таблица истории бросков создана!")
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

async def broadcast_to_room(room_id: int, message: dict):
    for ws in connections.get(room_id, []):
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass

# ============================================================
# 8. API: DICE ENGINE С КИНОШНЫМИ КУБИКАМИ
# ============================================================

@app.post("/api/dice/roll")
async def roll_dice(request: Request, data: dict):
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
    advantage = data.get('advantage', False)
    disadvantage = data.get('disadvantage', False)
    mode_str = data.get('mode', 'standard')
    
    try:
        mode = DiceMode(mode_str)
    except ValueError:
        mode = DiceMode.STANDARD
    
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
            # Используем режим комнаты, если не указан конкретный
            if not data.get('mode'):
                mode = DiceMode(room.dice_mode)
        session.close()
    
    roll_request = RollRequest(
        dice_type=dice_type,
        count=count,
        modifier=modifier,
        reason=reason,
        visibility=visibility_enum,
        user_id=user.id,
        character_id=character_id,
        room_id=room_id,
        advantage=advantage,
        disadvantage=disadvantage,
        mode=mode
    )
    
    result = dice_engine.roll(roll_request)
    
    # Сохраняем в БД
    session = Session()
    try:
        history = DiceHistory(
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
            timestamp=result.timestamp,
            dice_mode=mode.value
        )
        session.add(history)
        session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()
    
    # Генерируем кинематографическую анимацию
    animation_data = cinematic_dice.get_animation_data(result, mode)
    
    # Отправляем всем в комнате
    if visibility_enum == DiceVisibility.PUBLIC and room_id_str:
        await broadcast_to_room(room_id, {
            'type': 'dice_roll_cinematic',
            'result': result.to_dict(),
            'animation': animation_data
        })
    
    return {
        'success': True,
        'result': result.to_dict(),
        'animation': animation_data
    }

@app.post("/api/dice/mode")
async def set_dice_mode(request: Request, data: dict):
    """Устанавливает режим кубиков для комнаты."""
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return {"success": False, "message": "Только GM может менять режим"}
    
    room_id_str = data.get('room_id')
    mode_str = data.get('mode', 'standard')
    
    if not room_id_str:
        return {"success": False, "message": "Не указан room_id"}
    
    try:
        mode = DiceMode(mode_str)
    except ValueError:
        return {"success": False, "message": f"Неизвестный режим: {mode_str}"}
    
    session = Session()
    try:
        room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
        if not room:
            return {"success": False, "message": "Комната не найдена"}
        
        room.dice_mode = mode.value
        session.commit()
        
        await broadcast_to_room(room.id, {
            'type': 'dice_mode_changed',
            'mode': mode.value
        })
        
        return {'success': True, 'message': f'Режим кубиков изменён на {mode.value}'}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/dice/modes")
async def get_dice_modes():
    """Возвращает все доступные режимы."""
    return {
        'success': True,
        'modes': [
            {'value': 'fast', 'label': 'Fast', 'description': 'Быстрый бросок (0.5-1.5 сек)'},
            {'value': 'standard', 'label': 'Standard', 'description': 'Стандартный бросок (2-3 сек)'},
            {'value': 'cinematic', 'label': 'Cinematic', 'description': 'Кинематографический бросок (3-5 сек)'}
        ]
    }

# ============================================================
# 9. СТРАНИЦЫ
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
        "is_gm": room.gm_id == user.id,
        "dice_mode": room.dice_mode
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
                    # Обработка броска через WebSocket
                    dice_type = msg.get('dice_type', 'd20')
                    count = msg.get('count', 1)
                    modifier = msg.get('modifier', 0)
                    reason = msg.get('reason', 'Бросок')
                    visibility = msg.get('visibility', 'public')
                    character_id = msg.get('character_id', 0)
                    advantage = msg.get('advantage', False)
                    disadvantage = msg.get('disadvantage', False)
                    mode_str = msg.get('mode', room.dice_mode)
                    
                    try:
                        mode = DiceMode(mode_str)
                    except ValueError:
                        mode = DiceMode(room.dice_mode)
                    
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
                        room_id=room.id,
                        advantage=advantage,
                        disadvantage=disadvantage,
                        mode=mode
                    )
                    
                    result = dice_engine.roll(roll_request)
                    
                    # Сохраняем в БД
                    session2 = Session()
                    try:
                        history = DiceHistory(
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
                            timestamp=result.timestamp,
                            dice_mode=mode.value
                        )
                        session2.add(history)
                        session2.commit()
                    except Exception as e:
                        session2.rollback()
                    finally:
                        session2.close()
                    
                    animation_data = cinematic_dice.get_animation_data(result, mode)
                    
                    if visibility_enum == DiceVisibility.PUBLIC:
                        await broadcast_to_room(room.id, {
                            'type': 'dice_roll_cinematic',
                            'result': result.to_dict(),
                            'animation': animation_data
                        })
                    else:
                        gm = session.query(RoomPlayer).filter_by(room_id=room.id, role='gm').first()
                        if gm:
                            await websocket.send_text(json.dumps({
                                'type': 'dice_roll_secret',
                                'result': result.to_dict(),
                                'animation': animation_data
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
