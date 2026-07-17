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

class SkillType(str, Enum):
    ACTIVE = "active"
    PASSIVE = "passive"
    REACTION = "reaction"
    CONTEXTUAL = "contextual"

class TargetType(str, Enum):
    NONE = "none"
    SINGLE = "single"
    MULTIPLE = "multiple"
    AREA = "area"
    SELF = "self"
    ANY_OBJECT = "any_object"
    POSITION = "position"

class CooldownType(str, Enum):
    TURNS = "turns"
    ROUNDS = "rounds"
    TIME = "time"
    UNTIL_END_OF_SCENE = "until_end_of_scene"
    UNTIL_REST = "until_rest"
    NONE = "none"

class SkillEventType(str, Enum):
    SKILL_ACTIVATED = "skill_activated"
    SKILL_CANCELLED = "skill_cancelled"
    SKILL_ON_COOLDOWN = "skill_on_cooldown"
    SKILL_FINISHED = "skill_finished"
    SKILL_INTERRUPTED = "skill_interrupted"
    SKILL_UNLOCKED = "skill_unlocked"
    SKILL_REMOVED = "skill_removed"
    SKILL_AVAILABLE = "skill_available"

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
# 3. SKILL SYSTEM
# ============================================================

@dataclass
class Skill:
    """Универсальная способность."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ''
    description: str = ''
    icon: str = ''
    category: str = 'Active'
    skill_type: SkillType = SkillType.ACTIVE
    
    # Игровые параметры
    action_id: str = ''  # ID действия в Action System
    cooldown_type: CooldownType = CooldownType.NONE
    cooldown_value: int = 0
    charges: int = 0
    max_charges: int = 0
    resource_cost: Dict[str, int] = field(default_factory=dict)  # {"mana": 10, "stamina": 5}
    range: float = 0.0
    target_type: TargetType = TargetType.SINGLE
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Контекстные условия
    context_condition: str = ''  # JSON-условие для контекстных способностей
    
    # Визуал
    animation: str = ''
    sound: str = ''
    color: str = '#c7a252'
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'category': self.category,
            'skill_type': self.skill_type.value,
            'action_id': self.action_id,
            'cooldown_type': self.cooldown_type.value,
            'cooldown_value': self.cooldown_value,
            'charges': self.charges,
            'max_charges': self.max_charges,
            'resource_cost': self.resource_cost,
            'range': self.range,
            'target_type': self.target_type.value,
            'tags': self.tags,
            'metadata': self.metadata,
            'context_condition': self.context_condition,
            'animation': self.animation,
            'sound': self.sound,
            'color': self.color
        }
    
    def is_available(self, character: 'Character', cooldown_tracker: Dict[str, int]) -> bool:
        """Проверяет, доступна ли способность."""
        # Проверяем кулдаун
        if self.cooldown_type != CooldownType.NONE:
            remaining = cooldown_tracker.get(self.id, 0)
            if remaining > 0:
                return False
        
        # Проверяем заряды
        if self.max_charges > 0 and self.charges <= 0:
            return False
        
        # Проверяем ресурсы
        stats = json.loads(character.stats) if character.stats else {}
        for resource, cost in self.resource_cost.items():
            current = stats.get(resource, 0)
            if current < cost:
                return False
        
        return True
    
    def get_cooldown_remaining(self, cooldown_tracker: Dict[str, int]) -> int:
        """Возвращает оставшееся время кулдауна."""
        return cooldown_tracker.get(self.id, 0)


class SkillBar:
    """Панель способностей персонажа."""
    
    def __init__(self, character_id: int):
        self.character_id = character_id
        self._skills: Dict[str, Skill] = {}
        self._cooldowns: Dict[str, int] = {}  # skill_id -> remaining_turns
        self._slot_order: List[str] = []  # порядок слотов
    
    def add_skill(self, skill: Skill, slot: int = None) -> bool:
        """Добавляет способность на панель."""
        if skill.id in self._skills:
            return False
        
        self._skills[skill.id] = skill
        if slot is not None:
            self._slot_order.insert(slot, skill.id)
        else:
            self._slot_order.append(skill.id)
        return True
    
    def remove_skill(self, skill_id: str) -> bool:
        """Удаляет способность с панели."""
        if skill_id not in self._skills:
            return False
        
        del self._skills[skill_id]
        if skill_id in self._slot_order:
            self._slot_order.remove(skill_id)
        return True
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Получает способность по ID."""
        return self._skills.get(skill_id)
    
    def get_all_skills(self) -> List[Skill]:
        """Получает все способности в порядке слотов."""
        ordered = []
        for skill_id in self._slot_order:
            if skill_id in self._skills:
                ordered.append(self._skills[skill_id])
        return ordered
    
    def get_available_skills(self, character: Character) -> List[Skill]:
        """Получает доступные способности."""
        return [
            skill for skill in self.get_all_skills()
            if skill.is_available(character, self._cooldowns)
        ]
    
    def get_skills_by_category(self, category: str) -> List[Skill]:
        """Получает способности по категории."""
        return [s for s in self._skills.values() if s.category == category]
    
    def get_skills_by_type(self, skill_type: SkillType) -> List[Skill]:
        """Получает способности по типу."""
        return [s for s in self._skills.values() if s.skill_type == skill_type]
    
    def get_contextual_skills(self, context: Dict) -> List[Skill]:
        """Получает контекстные способности."""
        result = []
        for skill in self._skills.values():
            if skill.skill_type == SkillType.CONTEXTUAL:
                # Простая проверка контекста (можно расширить)
                if skill.context_condition:
                    try:
                        condition = json.loads(skill.context_condition)
                        if self._check_context(condition, context):
                            result.append(skill)
                    except:
                        pass
        return result
    
    def _check_context(self, condition: Dict, context: Dict) -> bool:
        """Проверяет условие контекста."""
        # Простая реализация — можно расширить
        for key, value in condition.items():
            if context.get(key) != value:
                return False
        return True
    
    def use_skill(self, skill_id: str, character: Character) -> bool:
        """Использует способность."""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        
        if not skill.is_available(character, self._cooldowns):
            return False
        
        # Устанавливаем кулдаун
        if skill.cooldown_type != CooldownType.NONE:
            self._cooldowns[skill_id] = skill.cooldown_value
        
        # Тратим заряды
        if skill.max_charges > 0:
            skill.charges -= 1
        
        return True
    
    def tick_cooldowns(self):
        """Обновляет кулдауны (уменьшает на 1)."""
        for skill_id in list(self._cooldowns.keys()):
            self._cooldowns[skill_id] -= 1
            if self._cooldowns[skill_id] <= 0:
                del self._cooldowns[skill_id]
    
    def to_dict(self, character: Character = None) -> dict:
        """Преобразует панель в словарь."""
        result = {
            'skills': [s.to_dict() for s in self.get_all_skills()],
            'cooldowns': self._cooldowns.copy()
        }
        
        if character:
            result['available'] = [
                s.id for s in self.get_available_skills(character)
            ]
        
        return result
    
    def load_from_character(self, character: Character):
        """Загружает способности из Character."""
        skills_data = json.loads(character.skills) if character.skills else []
        for skill_data in skills_data:
            skill = Skill(
                id=skill_data.get('id', str(uuid.uuid4())),
                name=skill_data.get('name', ''),
                description=skill_data.get('description', ''),
                icon=skill_data.get('icon', ''),
                category=skill_data.get('category', 'Active'),
                skill_type=SkillType(skill_data.get('skill_type', 'active')),
                action_id=skill_data.get('action_id', ''),
                cooldown_type=CooldownType(skill_data.get('cooldown_type', 'none')),
                cooldown_value=skill_data.get('cooldown_value', 0),
                charges=skill_data.get('charges', 0),
                max_charges=skill_data.get('max_charges', 0),
                resource_cost=skill_data.get('resource_cost', {}),
                range=skill_data.get('range', 0.0),
                target_type=TargetType(skill_data.get('target_type', 'single')),
                tags=skill_data.get('tags', []),
                metadata=skill_data.get('metadata', {}),
                context_condition=skill_data.get('context_condition', ''),
                animation=skill_data.get('animation', ''),
                sound=skill_data.get('sound', ''),
                color=skill_data.get('color', '#c7a252')
            )
            self.add_skill(skill)
    
    def save_to_character(self, character: Character):
        """Сохраняет способности в Character."""
        character.skills = json.dumps([s.to_dict() for s in self.get_all_skills()])


class SkillManager:
    """Управляет панелями способностей всех персонажей."""
    
    def __init__(self):
        self._bars: Dict[int, SkillBar] = {}  # character_id -> SkillBar
        self._event_listeners: Dict[SkillEventType, List[Callable]] = {}
    
    def get_skill_bar(self, character_id: int) -> Optional[SkillBar]:
        """Получает панель способностей персонажа."""
        return self._bars.get(character_id)
    
    def load_skill_bar(self, character: Character) -> SkillBar:
        """Загружает панель способностей персонажа."""
        bar = SkillBar(character.id)
        bar.load_from_character(character)
        self._bars[character.id] = bar
        return bar
    
    def save_skill_bar(self, character: Character) -> bool:
        """Сохраняет панель способностей персонажа."""
        bar = self._bars.get(character.id)
        if not bar:
            return False
        bar.save_to_character(character)
        return True
    
    def add_skill_to_character(self, character: Character, skill_data: dict) -> bool:
        """Добавляет способность персонажу."""
        bar = self.get_skill_bar(character.id)
        if not bar:
            bar = self.load_skill_bar(character)
        
        skill = Skill(**skill_data)
        success = bar.add_skill(skill)
        if success:
            self.save_skill_bar(character)
            self._publish_event(SkillEventType.SKILL_UNLOCKED, skill)
        return success
    
    def remove_skill_from_character(self, character: Character, skill_id: str) -> bool:
        """Удаляет способность у персонажа."""
        bar = self.get_skill_bar(character.id)
        if not bar:
            return False
        
        skill = bar.get_skill(skill_id)
        success = bar.remove_skill(skill_id)
        if success and skill:
            self.save_skill_bar(character)
            self._publish_event(SkillEventType.SKILL_REMOVED, skill)
        return success
    
    def use_skill(self, character: Character, skill_id: str, target: Any = None) -> bool:
        """Использует способность."""
        bar = self.get_skill_bar(character.id)
        if not bar:
            return False
        
        skill = bar.get_skill(skill_id)
        if not skill:
            return False
        
        if not bar.use_skill(skill_id, character):
            self._publish_event(SkillEventType.SKILL_ON_COOLDOWN, skill)
            return False
        
        self.save_skill_bar(character)
        self._publish_event(SkillEventType.SKILL_ACTIVATED, skill)
        
        # Здесь вызывается Game Action System
        # TODO: Интеграция с Game Action System
        return True
    
    def tick_cooldowns(self, character_id: int):
        """Обновляет кулдауны персонажа."""
        bar = self._bars.get(character_id)
        if bar:
            bar.tick_cooldowns()
    
    def subscribe(self, event_type: SkillEventType, callback: Callable):
        """Подписывается на события."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(callback)
    
    def _publish_event(self, event_type: SkillEventType, skill: Skill):
        """Публикует событие."""
        if event_type in self._event_listeners:
            for callback in self._event_listeners[event_type]:
                try:
                    callback(event_type, skill)
                except Exception as e:
                    print(f"Error in skill event callback: {e}")

skill_manager = SkillManager()

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
# 7. API: SKILL SYSTEM
# ============================================================

@app.post("/api/skill/load/{character_id}")
async def load_skills(character_id: int):
    """Загружает способности персонажа."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        bar = skill_manager.load_skill_bar(character)
        return {
            'success': True,
            'skills': bar.to_dict(character)
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/skill/add")
async def add_skill(request: Request, data: dict):
    """Добавляет способность персонажу."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    skill_data = data.get('skill')
    
    if not character_id or not skill_data:
        return {"success": False, "message": "Не указаны character_id или skill"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = skill_manager.add_skill_to_character(character, skill_data)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Способность добавлена'}
        return {"success": False, "message": "Не удалось добавить способность"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/skill/remove")
async def remove_skill(request: Request, data: dict):
    """Удаляет способность у персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    skill_id = data.get('skill_id')
    
    if not character_id or not skill_id:
        return {"success": False, "message": "Не указаны character_id или skill_id"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = skill_manager.remove_skill_from_character(character, skill_id)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Способность удалена'}
        return {"success": False, "message": "Способность не найдена"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/skill/use")
async def use_skill(request: Request, data: dict):
    """Использует способность."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    skill_id = data.get('skill_id')
    target = data.get('target')
    
    if not character_id or not skill_id:
        return {"success": False, "message": "Не указаны character_id или skill_id"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = skill_manager.use_skill(character, skill_id, target)
        session.commit()
        
        if success:
            return {
                'success': True,
                'message': 'Способность использована',
                'skill_id': skill_id,
                'target': target
            }
        return {"success": False, "message": "Не удалось использовать способность"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/skill/available/{character_id}")
async def get_available_skills(character_id: int):
    """Получает доступные способности персонажа."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        bar = skill_manager.get_skill_bar(character_id)
        if not bar:
            bar = skill_manager.load_skill_bar(character)
        
        available = bar.get_available_skills(character)
        return {
            'success': True,
            'skills': [s.to_dict() for s in available]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/skill/contextual/{character_id}")
async def get_contextual_skills(character_id: int, context: str = '{}'):
    """Получает контекстные способности."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        bar = skill_manager.get_skill_bar(character_id)
        if not bar:
            bar = skill_manager.load_skill_bar(character)
        
        try:
            context_data = json.loads(context)
        except:
            context_data = {}
        
        contextual = bar.get_contextual_skills(context_data)
        return {
            'success': True,
            'skills': [s.to_dict() for s in contextual]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/skill/types")
async def get_skill_types():
    """Возвращает все типы способностей."""
    return {
        'success': True,
        'types': [
            {'value': t.value, 'label': t.value.title()}
            for t in SkillType
        ]
    }

@app.get("/api/skill/target_types")
async def get_target_types():
    """Возвращает все типы целей."""
    return {
        'success': True,
        'types': [
            {'value': t.value, 'label': t.value.replace('_', ' ').title()}
            for t in TargetType
        ]
    }

# ============================================================
# 8. БЫСТРЫЙ СТАРТ
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
# 9. WEBSOCKET
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
                
                elif msg_type == 'skill_use':
                    character_id = msg.get('character_id')
                    skill_id = msg.get('skill_id')
                    target = msg.get('target')
                    
                    if character_id and skill_id:
                        session2 = Session()
                        character = session2.query(Character).filter_by(id=character_id).first()
                        if character:
                            success = skill_manager.use_skill(character, skill_id, target)
                            if success:
                                session2.commit()
                                await broadcast_to_room(room.id, {
                                    'type': 'skill_used',
                                    'character_id': character_id,
                                    'skill_id': skill_id,
                                    'target': target,
                                    'timestamp': datetime.now().isoformat()
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

async def broadcast_to_room(room_id: int, message: dict):
    """Отправляет сообщение всем в комнате."""
    for ws in connections.get(room_id, []):
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass

# ============================================================
# 10. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
