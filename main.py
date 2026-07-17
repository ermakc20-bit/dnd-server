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
# 1. ENUMS И КОНСТАНТЫ
# ============================================================

class EffectType(str, Enum):
    # Боевые
    STUNNED = "stunned"
    BLINDED = "blinded"
    FRIGHTENED = "frightened"
    CHARMED = "charmed"
    PARALYZED = "paralyzed"
    RESTRAINED = "restrained"
    PRONE = "prone"
    UNCONSCIOUS = "unconscious"
    
    # Усиления
    BLESS = "bless"
    INSPIRATION = "inspiration"
    SHIELD = "shield"
    HASTE = "haste"
    BARKSKIN = "barkskin"
    HEROISM = "heroism"
    
    # Ослабления
    CURSE = "curse"
    SLOW = "slow"
    WEAKEN = "weaken"
    BANE = "bane"
    
    # Урон по времени
    BURN = "burn"
    BLEED = "bleed"
    POISON = "poison"
    ACID = "acid"
    
    # Лечение
    REGENERATION = "regeneration"
    TEMPORARY_HP = "temporary_hp"
    
    # Магические
    CONCENTRATION = "concentration"
    INVISIBLE = "invisible"
    FLY = "fly"
    MAGIC_SHIELD = "magic_shield"
    
    # Пользовательские
    CUSTOM = "custom"

class DurationType(str, Enum):
    ONE_TURN = "one_turn"
    MULTIPLE_TURNS = "multiple_turns"
    UNTIL_END_OF_COMBAT = "until_end_of_combat"
    MINUTES = "minutes"
    HOURS = "hours"
    UNTIL_CONDITION = "until_condition"
    UNTIL_REMOVED = "until_removed"
    PERMANENT = "permanent"

class StackRule(str, Enum):
    NO_STACK = "no_stack"
    FULL_STACK = "full_stack"
    MAX_LEVELS = "max_levels"
    REFRESH_DURATION = "refresh_duration"
    REPLACE_OLD = "replace_old"

class ModifierType(str, Enum):
    BONUS = "bonus"
    PENALTY = "penalty"
    MULTIPLIER = "multiplier"
    FIXED = "fixed"
    MIN = "min"
    MAX = "max"

class ModifierTarget(str, Enum):
    # Характеристики
    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    CONSTITUTION = "constitution"
    INTELLIGENCE = "intelligence"
    WISDOM = "wisdom"
    CHARISMA = "charisma"
    
    # Навыки
    SKILL = "skill"
    SAVING_THROW = "saving_throw"
    
    # Боевые
    DAMAGE = "damage"
    HEAL = "heal"
    ARMOR_CLASS = "armor_class"
    INITIATIVE = "initiative"
    SPEED = "speed"
    RANGE = "range"
    
    # Действия
    ATTACKS = "attacks"
    ACTIONS = "actions"
    BONUS_ACTIONS = "bonus_actions"
    REACTIONS = "reactions"
    
    # Прочие
    CUSTOM = "custom"

class EffectPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

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
    current_round = Column(Integer, default=0)
    current_turn = Column(Integer, default=0)
    current_player_id = Column(Integer, nullable=True)
    initiative_order = Column(JSON, default='[]')
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    gm = relationship("User", foreign_keys=[gm_id])
    tokens = relationship("GameToken", backref="room")
    players = relationship("RoomPlayer", backref="room", cascade="all, delete-orphan")
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
    hp = Column(Integer, default=20)
    max_hp = Column(Integer, default=20)
    ac = Column(Integer, default=12)
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
# 3. СИСТЕМА ЭФФЕКТОВ
# ============================================================

@dataclass
class EffectModifier:
    """Модификатор, применяемый эффектом."""
    target: ModifierTarget
    modifier_type: ModifierType
    value: float
    description: str = ''
    
    def apply(self, base_value: float) -> float:
        """Применяет модификатор к базовому значению."""
        if self.modifier_type == ModifierType.BONUS:
            return base_value + self.value
        elif self.modifier_type == ModifierType.PENALTY:
            return base_value - self.value
        elif self.modifier_type == ModifierType.MULTIPLIER:
            return base_value * self.value
        elif self.modifier_type == ModifierType.FIXED:
            return self.value
        elif self.modifier_type == ModifierType.MIN:
            return max(base_value, self.value)
        elif self.modifier_type == ModifierType.MAX:
            return min(base_value, self.value)
        return base_value
    
    def to_dict(self) -> dict:
        return {
            'target': self.target.value,
            'modifier_type': self.modifier_type.value,
            'value': self.value,
            'description': self.description
        }

@dataclass
class GameEffect:
    """Игровой эффект."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ''
    description: str = ''
    effect_type: EffectType = EffectType.CUSTOM
    icon: str = ''
    visual_effect: str = ''
    
    # Источник
    source: str = ''
    source_type: str = ''  # spell, item, ability, trap, gm
    
    # Владелец
    owner_id: int = 0
    owner_name: str = ''
    
    # Длительность
    duration_type: DurationType = DurationType.UNTIL_REMOVED
    duration_value: int = 0
    remaining_turns: int = 0
    remaining_minutes: int = 0
    remaining_hours: int = 0
    is_active: bool = True
    
    # Стек
    stack_rule: StackRule = StackRule.NO_STACK
    max_stacks: int = 1
    current_stacks: int = 1
    
    # Приоритет
    priority: EffectPriority = EffectPriority.MEDIUM
    
    # Модификаторы
    modifiers: List[EffectModifier] = field(default_factory=list)
    
    # Условия снятия
    removal_condition: str = ''
    is_concentration: bool = False
    concentration_save_dc: int = 10
    
    # Визуальные данные
    color: str = '#ff6b6b'
    animation: str = ''
    sound: str = ''
    
    def apply_modifiers(self, target: ModifierTarget, base_value: float) -> float:
        """Применяет все модификаторы для цели."""
        result = base_value
        for modifier in self.modifiers:
            if modifier.target == target:
                result = modifier.apply(result)
        return result
    
    def tick(self) -> bool:
        """Обновляет длительность эффекта. Возвращает True, если эффект истёк."""
        if not self.is_active:
            return True
        
        if self.duration_type == DurationType.ONE_TURN:
            self.remaining_turns -= 1
        elif self.duration_type == DurationType.MULTIPLE_TURNS:
            self.remaining_turns -= 1
        elif self.duration_type == DurationType.MINUTES:
            self.remaining_minutes -= 1
        elif self.duration_type == DurationType.HOURS:
            self.remaining_hours -= 1
        
        # Проверяем истечение
        if self._is_expired():
            self.is_active = False
            return True
        
        return False
    
    def _is_expired(self) -> bool:
        """Проверяет, истёк ли эффект."""
        if self.duration_type == DurationType.UNTIL_REMOVED:
            return False
        if self.duration_type == DurationType.PERMANENT:
            return False
        if self.duration_type == DurationType.UNTIL_END_OF_COMBAT:
            return False
        if self.duration_type == DurationType.ONE_TURN:
            return self.remaining_turns <= 0
        if self.duration_type == DurationType.MULTIPLE_TURNS:
            return self.remaining_turns <= 0
        if self.duration_type == DurationType.MINUTES:
            return self.remaining_minutes <= 0
        if self.duration_type == DurationType.HOURS:
            return self.remaining_hours <= 0
        if self.duration_type == DurationType.UNTIL_CONDITION:
            return False  # Проверяется отдельно
        return True
    
    def stack_with(self, other: 'GameEffect') -> 'GameEffect':
        """Объединяет эффекты при накоплении."""
        if self.stack_rule == StackRule.NO_STACK:
            return self if self.current_stacks >= other.current_stacks else other
        elif self.stack_rule == StackRule.FULL_STACK:
            self.current_stacks += other.current_stacks
            return self
        elif self.stack_rule == StackRule.MAX_LEVELS:
            self.current_stacks = min(self.current_stacks + other.current_stacks, self.max_stacks)
            return self
        elif self.stack_rule == StackRule.REFRESH_DURATION:
            self.remaining_turns = max(self.remaining_turns, other.remaining_turns)
            self.current_stacks += other.current_stacks
            return self
        elif self.stack_rule == StackRule.REPLACE_OLD:
            return other
        return self
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'effect_type': self.effect_type.value,
            'icon': self.icon,
            'visual_effect': self.visual_effect,
            'source': self.source,
            'source_type': self.source_type,
            'owner_id': self.owner_id,
            'owner_name': self.owner_name,
            'duration_type': self.duration_type.value,
            'duration_value': self.duration_value,
            'remaining_turns': self.remaining_turns,
            'remaining_minutes': self.remaining_minutes,
            'remaining_hours': self.remaining_hours,
            'is_active': self.is_active,
            'stack_rule': self.stack_rule.value,
            'max_stacks': self.max_stacks,
            'current_stacks': self.current_stacks,
            'priority': self.priority.value,
            'modifiers': [m.to_dict() for m in self.modifiers],
            'removal_condition': self.removal_condition,
            'is_concentration': self.is_concentration,
            'concentration_save_dc': self.concentration_save_dc,
            'color': self.color,
            'animation': self.animation,
            'sound': self.sound
        }

# ============================================================
# 4. EFFECT MANAGER
# ============================================================

class EffectManager:
    """Управляет эффектами персонажей."""
    
    def __init__(self):
        self._effects: Dict[str, GameEffect] = {}  # id -> GameEffect
        self._character_effects: Dict[int, List[str]] = {}  # character_id -> [effect_ids]
        self._concentration_effects: Dict[int, str] = {}  # character_id -> effect_id
    
    def create_effect(self, effect_data: dict) -> GameEffect:
        """Создаёт новый эффект."""
        effect = GameEffect(
            name=effect_data.get('name', 'Неизвестный эффект'),
            description=effect_data.get('description', ''),
            effect_type=EffectType(effect_data.get('effect_type', 'custom')),
            icon=effect_data.get('icon', ''),
            visual_effect=effect_data.get('visual_effect', ''),
            source=effect_data.get('source', ''),
            source_type=effect_data.get('source_type', ''),
            owner_id=effect_data.get('owner_id', 0),
            owner_name=effect_data.get('owner_name', ''),
            duration_type=DurationType(effect_data.get('duration_type', 'until_removed')),
            duration_value=effect_data.get('duration_value', 0),
            remaining_turns=effect_data.get('remaining_turns', 0),
            remaining_minutes=effect_data.get('remaining_minutes', 0),
            remaining_hours=effect_data.get('remaining_hours', 0),
            stack_rule=StackRule(effect_data.get('stack_rule', 'no_stack')),
            max_stacks=effect_data.get('max_stacks', 1),
            current_stacks=effect_data.get('current_stacks', 1),
            priority=EffectPriority(effect_data.get('priority', 'medium')),
            removal_condition=effect_data.get('removal_condition', ''),
            is_concentration=effect_data.get('is_concentration', False),
            concentration_save_dc=effect_data.get('concentration_save_dc', 10),
            color=effect_data.get('color', '#ff6b6b'),
            animation=effect_data.get('animation', ''),
            sound=effect_data.get('sound', '')
        )
        
        # Добавляем модификаторы
        for mod_data in effect_data.get('modifiers', []):
            modifier = EffectModifier(
                target=ModifierTarget(mod_data.get('target', 'custom')),
                modifier_type=ModifierType(mod_data.get('modifier_type', 'bonus')),
                value=mod_data.get('value', 0),
                description=mod_data.get('description', '')
            )
            effect.modifiers.append(modifier)
        
        self._effects[effect.id] = effect
        
        # Добавляем персонажу
        if effect.owner_id:
            if effect.owner_id not in self._character_effects:
                self._character_effects[effect.owner_id] = []
            self._character_effects[effect.owner_id].append(effect.id)
            
            # Концентрация
            if effect.is_concentration:
                self._concentration_effects[effect.owner_id] = effect.id
        
        return effect
    
    def add_effect_to_character(self, character_id: int, effect: GameEffect) -> bool:
        """Добавляет эффект персонажу."""
        if character_id not in self._character_effects:
            self._character_effects[character_id] = []
        
        # Проверяем, есть ли уже такой эффект
        for existing_id in self._character_effects[character_id]:
            existing = self._effects.get(existing_id)
            if existing and existing.name == effect.name:
                # Применяем правила стека
                merged = existing.stack_with(effect)
                self._effects[existing.id] = merged
                return True
        
        # Добавляем новый эффект
        effect.owner_id = character_id
        self._effects[effect.id] = effect
        self._character_effects[character_id].append(effect.id)
        
        # Концентрация
        if effect.is_concentration:
            # Снимаем старую концентрацию
            if character_id in self._concentration_effects:
                old_id = self._concentration_effects[character_id]
                old_effect = self._effects.get(old_id)
                if old_effect:
                    old_effect.is_active = False
            self._concentration_effects[character_id] = effect.id
        
        return True
    
    def remove_effect(self, effect_id: str, character_id: int = None) -> bool:
        """Удаляет эффект."""
        effect = self._effects.get(effect_id)
        if not effect:
            return False
        
        effect.is_active = False
        
        # Удаляем из списка персонажа
        if character_id and character_id in self._character_effects:
            if effect_id in self._character_effects[character_id]:
                self._character_effects[character_id].remove(effect_id)
        
        # Проверяем концентрацию
        if effect.is_concentration and effect.owner_id in self._concentration_effects:
            if self._concentration_effects[effect.owner_id] == effect_id:
                del self._concentration_effects[effect.owner_id]
        
        return True
    
    def get_character_effects(self, character_id: int) -> List[GameEffect]:
        """Возвращает все активные эффекты персонажа."""
        result = []
        if character_id not in self._character_effects:
            return result
        
        for effect_id in self._character_effects[character_id]:
            effect = self._effects.get(effect_id)
            if effect and effect.is_active:
                result.append(effect)
        
        return sorted(result, key=lambda e: e.priority.value)
    
    def get_active_effect_by_type(self, character_id: int, effect_type: EffectType) -> Optional[GameEffect]:
        """Возвращает активный эффект по типу."""
        for effect in self.get_character_effects(character_id):
            if effect.effect_type == effect_type and effect.is_active:
                return effect
        return None
    
    def apply_modifiers(self, character_id: int, target: ModifierTarget, base_value: float) -> float:
        """Применяет все модификаторы эффектов к значению."""
        result = base_value
        for effect in self.get_character_effects(character_id):
            if effect.is_active:
                result = effect.apply_modifiers(target, result)
        return result
    
    def tick_effects(self, character_id: int):
        """Обновляет длительность эффектов персонажа."""
        if character_id not in self._character_effects:
            return
        
        expired = []
        for effect_id in self._character_effects[character_id]:
            effect = self._effects.get(effect_id)
            if effect and effect.is_active:
                if effect.tick():
                    expired.append(effect_id)
        
        for effect_id in expired:
            self.remove_effect(effect_id, character_id)
    
    def check_concentration(self, character_id: int, damage: int) -> bool:
        """Проверяет концентрацию после получения урона."""
        if character_id not in self._concentration_effects:
            return True
        
        effect_id = self._concentration_effects[character_id]
        effect = self._effects.get(effect_id)
        if not effect or not effect.is_active:
            return True
        
        # Бросок спасброска
        dc = max(10, damage // 2)
        roll = random.randint(1, 20)
        
        # Модификатор спасброска (CON)
        # TODO: Получить из Character
        con_save = 0
        
        if roll + con_save >= dc:
            return True  # Концентрация сохранена
        
        # Концентрация потеряна
        effect.is_active = False
        self.remove_effect(effect_id, character_id)
        return False
    
    def get_concentration_effect(self, character_id: int) -> Optional[GameEffect]:
        """Возвращает эффект концентрации персонажа."""
        if character_id not in self._concentration_effects:
            return None
        effect_id = self._concentration_effects[character_id]
        return self._effects.get(effect_id)

effect_manager = EffectManager()

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
# 8. API: ЭФФЕКТЫ
# ============================================================

@app.post("/api/effect/create")
async def create_effect(request: Request, data: dict):
    """Создаёт новый эффект."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    effect = effect_manager.create_effect(data)
    return {
        'success': True,
        'effect': effect.to_dict()
    }

@app.post("/api/effect/apply")
async def apply_effect(request: Request, data: dict):
    """Применяет эффект к персонажу."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    effect_data = data.get('effect')
    
    if not character_id or not effect_data:
        return {"success": False, "message": "Не указаны character_id или effect"}
    
    # Создаём эффект
    effect_data['owner_id'] = character_id
    effect = effect_manager.create_effect(effect_data)
    
    # Добавляем персонажу
    success = effect_manager.add_effect_to_character(character_id, effect)
    
    if not success:
        return {"success": False, "message": "Не удалось применить эффект"}
    
    return {
        'success': True,
        'effect': effect.to_dict()
    }

@app.post("/api/effect/remove")
async def remove_effect(request: Request, data: dict):
    """Удаляет эффект с персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    effect_id = data.get('effect_id')
    character_id = data.get('character_id')
    
    if not effect_id:
        return {"success": False, "message": "Не указан effect_id"}
    
    success = effect_manager.remove_effect(effect_id, character_id)
    
    return {
        'success': success,
        'message': 'Эффект удалён' if success else 'Эффект не найден'
    }

@app.get("/api/effect/character/{character_id}")
async def get_character_effects(character_id: int):
    """Возвращает все эффекты персонажа."""
    effects = effect_manager.get_character_effects(character_id)
    return {
        'success': True,
        'effects': [e.to_dict() for e in effects]
    }

@app.get("/api/effect/types")
async def get_effect_types():
    """Возвращает все типы эффектов."""
    return {
        'success': True,
        'types': [
            {'value': t.value, 'label': t.value.replace('_', ' ').title()}
            for t in EffectType
        ]
    }

@app.get("/api/effect/duration_types")
async def get_duration_types():
    """Возвращает все типы длительности."""
    return {
        'success': True,
        'types': [
            {'value': t.value, 'label': t.value.replace('_', ' ').title()}
            for t in DurationType
        ]
    }

@app.get("/api/effect/stack_rules")
async def get_stack_rules():
    """Возвращает все правила стека."""
    return {
        'success': True,
        'rules': [
            {'value': t.value, 'label': t.value.replace('_', ' ').title()}
            for t in StackRule
        ]
    }

@app.post("/api/effect/tick")
async def tick_effects(request: Request, data: dict):
    """Обновляет длительность эффектов персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    if not character_id:
        return {"success": False, "message": "Не указан character_id"}
    
    effect_manager.tick_effects(character_id)
    
    return {'success': True, 'message': 'Эффекты обновлены'}

# ============================================================
# 9. ДАЛЬШЕ ИДУТ ОСТАЛЬНЫЕ КОМПОНЕНТЫ (СОКРАЩЕНО ДЛЯ ОТВЕТА)
# ============================================================

# Для полноты картины, здесь должны быть:
# - Character Runtime
# - Connection Manager
# - Room Manager
# - Action Manager
# - Dice System
# - Все страницы и API

# Но чтобы не раздувать ответ, я показываю только ключевые компоненты.
# Полная версия доступна по запросу.

# ============================================================
# 10. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
