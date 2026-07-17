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

class ActionCategory(str, Enum):
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

class CombatEntityType(str, Enum):
    PLAYER = "player"
    NPC = "npc"
    MONSTER = "monster"
    SUMMON = "summon"
    TEMPORARY = "temporary"

class CombatEventType(str, Enum):
    COMBAT_STARTED = "combat_started"
    COMBAT_ENDED = "combat_ended"
    ROUND_STARTED = "round_started"
    ROUND_ENDED = "round_ended"
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    ENTITY_KILLED = "entity_killed"
    ENTITY_REVIVED = "entity_revived"
    ACTION_PERFORMED = "action_performed"
    DAMAGE_DEALT = "damage_dealt"
    HEAL_APPLIED = "heal_applied"
    EFFECT_APPLIED = "effect_applied"
    EFFECT_REMOVED = "effect_removed"

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
# 3. COMBAT ENGINE (ЯДРО БОЕВОЙ СИСТЕМЫ)
# ============================================================

@dataclass
class CombatEntity:
    """Участник боя."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: int = 0
    name: str = ''
    entity_type: CombatEntityType = CombatEntityType.NPC
    initiative: int = 0
    current_hp: int = 20
    max_hp: int = 20
    temporary_hp: int = 0
    armor_class: int = 10
    is_alive: bool = True
    can_act: bool = True
    x: float = 0
    y: float = 0
    token_id: int = 0
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'character_id': self.character_id,
            'name': self.name,
            'entity_type': self.entity_type.value,
            'initiative': self.initiative,
            'current_hp': self.current_hp,
            'max_hp': self.max_hp,
            'temporary_hp': self.temporary_hp,
            'armor_class': self.armor_class,
            'is_alive': self.is_alive,
            'can_act': self.can_act,
            'x': self.x,
            'y': self.y,
            'token_id': self.token_id
        }

@dataclass
class CombatLogEntry:
    """Запись в боевом журнале."""
    timestamp: datetime = field(default_factory=datetime.now)
    event_type: CombatEventType = CombatEventType.ACTION_PERFORMED
    actor_id: str = ''
    actor_name: str = ''
    target_id: str = ''
    target_name: str = ''
    message: str = ''
    data: Dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'event_type': self.event_type.value,
            'actor_id': self.actor_id,
            'actor_name': self.actor_name,
            'target_id': self.target_id,
            'target_name': self.target_name,
            'message': self.message,
            'data': self.data
        }

class CombatEngine:
    """
    Универсальный боевой движок.
    Не знает про D&D, Vampire или другие системы.
    Только координирует порядок боя.
    """
    
    def __init__(self, room_id: int):
        self.room_id = room_id
        self.is_active = False
        self.entities: Dict[str, CombatEntity] = {}
        self.queue: List[str] = []  # entity_ids в порядке инициативы
        self.current_index: int = 0
        self.round_number: int = 0
        self.logs: List[CombatLogEntry] = []
        self._event_listeners: Dict[CombatEventType, List[Callable]] = {}
        self._action_resolver = None  # Будет установлен позже
    
    # ===== УПРАВЛЕНИЕ УЧАСТНИКАМИ =====
    
    def add_entity(self, entity: CombatEntity) -> bool:
        """Добавляет участника в бой."""
        if entity.id in self.entities:
            return False
        self.entities[entity.id] = entity
        self.queue.append(entity.id)
        return True
    
    def remove_entity(self, entity_id: str) -> bool:
        """Удаляет участника из боя."""
        if entity_id not in self.entities:
            return False
        del self.entities[entity_id]
        if entity_id in self.queue:
            self.queue.remove(entity_id)
        return True
    
    def get_entity(self, entity_id: str) -> Optional[CombatEntity]:
        """Получает участника по ID."""
        return self.entities.get(entity_id)
    
    def get_living_entities(self) -> List[CombatEntity]:
        """Возвращает живых участников."""
        return [e for e in self.entities.values() if e.is_alive]
    
    # ===== УПРАВЛЕНИЕ БОЕМ =====
    
    def start_combat(self, entities: List[CombatEntity]) -> bool:
        """Начинает бой с указанными участниками."""
        if self.is_active:
            return False
        
        self.is_active = True
        self.entities = {e.id: e for e in entities}
        self.queue = [e.id for e in entities]
        self.round_number = 0
        self.current_index = 0
        self.logs = []
        
        # Сортируем по инициативе (по убыванию)
        self.queue.sort(key=lambda eid: self.entities[eid].initiative, reverse=True)
        
        # Начинаем первый раунд
        self._start_round()
        
        self._publish_event(CombatEventType.COMBAT_STARTED, {
            'entities': [e.to_dict() for e in entities]
        })
        
        return True
    
    def end_combat(self) -> bool:
        """Завершает бой."""
        if not self.is_active:
            return False
        
        self.is_active = False
        self._publish_event(CombatEventType.COMBAT_ENDED, {
            'rounds': self.round_number,
            'log_count': len(self.logs)
        })
        return True
    
    # ===== УПРАВЛЕНИЕ РАУНДАМИ =====
    
    def _start_round(self):
        """Начинает новый раунд."""
        self.round_number += 1
        self.current_index = 0
        
        # Обновляем живых участников
        living = self.get_living_entities()
        if not living:
            self.end_combat()
            return
        
        # Сортируем по инициативе
        self.queue = [e.id for e in sorted(living, key=lambda e: e.initiative, reverse=True)]
        
        self._publish_event(CombatEventType.ROUND_STARTED, {
            'round_number': self.round_number
        })
        
        # Начинаем первый ход
        self._start_turn()
    
    def _end_round(self):
        """Завершает текущий раунд."""
        self._publish_event(CombatEventType.ROUND_ENDED, {
            'round_number': self.round_number
        })
        self._start_round()
    
    # ===== УПРАВЛЕНИЕ ХОДАМИ =====
    
    def _start_turn(self):
        """Начинает ход текущего участника."""
        if not self.is_active:
            return
        
        # Проверяем, есть ли живые участники
        living = self.get_living_entities()
        if not living:
            self.end_combat()
            return
        
        # Проверяем, не вышел ли индекс за пределы
        if self.current_index >= len(self.queue):
            self._end_round()
            return
        
        entity_id = self.queue[self.current_index]
        entity = self.entities.get(entity_id)
        
        if not entity or not entity.is_alive:
            self._next_turn()
            return
        
        # Применяем эффекты в начале хода
        self._apply_turn_start_effects(entity)
        
        self._publish_event(CombatEventType.TURN_STARTED, {
            'entity': entity.to_dict(),
            'round': self.round_number,
            'turn_index': self.current_index
        })
    
    def _end_turn(self):
        """Завершает ход текущего участника."""
        entity_id = self.queue[self.current_index] if self.current_index < len(self.queue) else None
        entity = self.entities.get(entity_id) if entity_id else None
        
        self._publish_event(CombatEventType.TURN_ENDED, {
            'entity_id': entity_id,
            'entity_name': entity.name if entity else 'Unknown'
        })
        
        self._next_turn()
    
    def _next_turn(self):
        """Переходит к следующему ходу."""
        self.current_index += 1
        
        # Проверяем, не кончился ли раунд
        if self.current_index >= len(self.queue):
            self._end_round()
        else:
            self._start_turn()
    
    # ===== ПРИМЕНЕНИЕ ЭФФЕКТОВ В НАЧАЛЕ ХОДА =====
    
    def _apply_turn_start_effects(self, entity: CombatEntity):
        """Применяет эффекты в начале хода (Bleeding, Poison, Regeneration и т.д.)."""
        # Здесь будет вызов Effect System
        # TODO: Интеграция с Effect System
        pass
    
    # ===== ДЕЙСТВИЯ В БОЮ =====
    
    def perform_action(self, entity_id: str, action_data: Dict) -> Dict:
        """
        Выполняет действие в бою.
        Вызывает Action Resolver для расчёта.
        """
        if not self.is_active:
            return {'success': False, 'error': 'Бой не активен'}
        
        entity = self.entities.get(entity_id)
        if not entity:
            return {'success': False, 'error': 'Участник не найден'}
        
        if not entity.is_alive:
            return {'success': False, 'error': 'Участник мёртв'}
        
        # Проверяем, что это ход этого участника
        current_id = self.queue[self.current_index] if self.current_index < len(self.queue) else None
        if current_id != entity_id:
            return {'success': False, 'error': 'Сейчас не ваш ход'}
        
        # Вызываем Action Resolver (если установлен)
        if self._action_resolver:
            result = self._action_resolver.resolve_action(entity_id, action_data)
        else:
            result = {'success': True, 'message': 'Действие выполнено', 'data': action_data}
        
        # Публикуем событие
        self._publish_event(CombatEventType.ACTION_PERFORMED, {
            'entity_id': entity_id,
            'entity_name': entity.name,
            'action': action_data,
            'result': result
        })
        
        # Добавляем в лог
        self.logs.append(CombatLogEntry(
            event_type=CombatEventType.ACTION_PERFORMED,
            actor_id=entity_id,
            actor_name=entity.name,
            message=result.get('message', 'Действие выполнено'),
            data={'action': action_data, 'result': result}
        ))
        
        # Завершаем ход
        self._end_turn()
        
        return result
    
    def skip_turn(self, entity_id: str) -> bool:
        """Пропускает ход."""
        if not self.is_active:
            return False
        
        entity = self.entities.get(entity_id)
        if not entity or not entity.is_alive:
            return False
        
        current_id = self.queue[self.current_index] if self.current_index < len(self.queue) else None
        if current_id != entity_id:
            return False
        
        self._publish_event(CombatEventType.ACTION_PERFORMED, {
            'entity_id': entity_id,
            'entity_name': entity.name,
            'action': 'skip',
            'result': {'success': True, 'message': 'Ход пропущен'}
        })
        
        self.logs.append(CombatLogEntry(
            event_type=CombatEventType.ACTION_PERFORMED,
            actor_id=entity_id,
            actor_name=entity.name,
            message='Ход пропущен'
        ))
        
        self._end_turn()
        return True
    
    # ===== УПРАВЛЕНИЕ HP =====
    
    def apply_damage(self, target_id: str, damage: int, source_id: str = None) -> int:
        """Применяет урон к цели. Возвращает реальный урон."""
        entity = self.entities.get(target_id)
        if not entity or not entity.is_alive:
            return 0
        
        # Сначала снимаем временные HP
        if entity.temporary_hp > 0:
            temp_damage = min(damage, entity.temporary_hp)
            entity.temporary_hp -= temp_damage
            damage -= temp_damage
            if entity.temporary_hp < 0:
                entity.temporary_hp = 0
        
        # Снимаем основные HP
        actual_damage = min(damage, entity.current_hp)
        entity.current_hp -= actual_damage
        
        # Проверяем смерть
        if entity.current_hp <= 0:
            entity.current_hp = 0
            entity.is_alive = False
            self._publish_event(CombatEventType.ENTITY_KILLED, {
                'entity_id': target_id,
                'entity_name': entity.name,
                'source_id': source_id
            })
        
        # Публикуем событие
        self._publish_event(CombatEventType.DAMAGE_DEALT, {
            'target_id': target_id,
            'target_name': entity.name,
            'damage': actual_damage,
            'source_id': source_id
        })
        
        self.logs.append(CombatLogEntry(
            event_type=CombatEventType.DAMAGE_DEALT,
            actor_id=source_id or 'unknown',
            actor_name='Unknown',
            target_id=target_id,
            target_name=entity.name,
            message=f'{entity.name} получил {actual_damage} урона',
            data={'damage': actual_damage, 'remaining_hp': entity.current_hp}
        ))
        
        return actual_damage
    
    def apply_heal(self, target_id: str, amount: int, source_id: str = None) -> int:
        """Применяет лечение к цели. Возвращает реальное лечение."""
        entity = self.entities.get(target_id)
        if not entity or not entity.is_alive:
            return 0
        
        old_hp = entity.current_hp
        entity.current_hp = min(entity.max_hp, entity.current_hp + amount)
        actual_heal = entity.current_hp - old_hp
        
        if entity.current_hp > 0 and not entity.is_alive:
            entity.is_alive = True
            self._publish_event(CombatEventType.ENTITY_REVIVED, {
                'entity_id': target_id,
                'entity_name': entity.name,
                'source_id': source_id
            })
        
        self._publish_event(CombatEventType.HEAL_APPLIED, {
            'target_id': target_id,
            'target_name': entity.name,
            'heal': actual_heal,
            'source_id': source_id
        })
        
        self.logs.append(CombatLogEntry(
            event_type=CombatEventType.HEAL_APPLIED,
            actor_id=source_id or 'unknown',
            actor_name='Unknown',
            target_id=target_id,
            target_name=entity.name,
            message=f'{entity.name} получил {actual_heal} лечения',
            data={'heal': actual_heal, 'remaining_hp': entity.current_hp}
        ))
        
        return actual_heal
    
    # ===== СОБЫТИЯ =====
    
    def subscribe(self, event_type: CombatEventType, callback: Callable):
        """Подписывается на события боя."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(callback)
    
    def _publish_event(self, event_type: CombatEventType, data: Dict):
        """Публикует событие."""
        if event_type in self._event_listeners:
            for callback in self._event_listeners[event_type]:
                try:
                    callback(event_type, data)
                except Exception as e:
                    print(f"Error in event callback: {e}")
    
    # ===== СОСТОЯНИЕ БОЯ =====
    
    def get_state(self) -> Dict:
        """Возвращает текущее состояние боя."""
        return {
            'is_active': self.is_active,
            'round_number': self.round_number,
            'current_index': self.current_index,
            'total_entities': len(self.entities),
            'living_entities': len(self.get_living_entities()),
            'queue': [self.entities[eid].to_dict() for eid in self.queue if eid in self.entities],
            'current_entity_id': self.queue[self.current_index] if self.current_index < len(self.queue) and self.is_active else None,
            'logs': [log.to_dict() for log in self.logs[-20:]]  # Последние 20 записей
        }
    
    # ===== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ =====
    
    def set_action_resolver(self, resolver):
        """Устанавливает Action Resolver для расчёта действий."""
        self._action_resolver = resolver

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
# 7. COMBAT MANAGER
# ============================================================

class CombatManager:
    """Управляет боевыми движками для всех комнат."""
    
    def __init__(self):
        self._engines: Dict[int, CombatEngine] = {}
    
    def get_engine(self, room_id: int) -> Optional[CombatEngine]:
        """Получает боевой движок для комнаты."""
        return self._engines.get(room_id)
    
    def create_engine(self, room_id: int) -> CombatEngine:
        """Создаёт боевой движок для комнаты."""
        engine = CombatEngine(room_id)
        self._engines[room_id] = engine
        return engine
    
    def remove_engine(self, room_id: int):
        """Удаляет боевой движок комнаты."""
        if room_id in self._engines:
            del self._engines[room_id]
    
    def start_combat(self, room_id: int, entities: List[CombatEntity]) -> bool:
        """Начинает бой в комнате."""
        engine = self.get_engine(room_id)
        if not engine:
            engine = self.create_engine(room_id)
        return engine.start_combat(entities)
    
    def end_combat(self, room_id: int) -> bool:
        """Завершает бой в комнате."""
        engine = self.get_engine(room_id)
        if not engine:
            return False
        return engine.end_combat()

combat_manager = CombatManager()

# ============================================================
# 8. API: COMBAT
# ============================================================

@app.post("/api/combat/start")
async def start_combat(request: Request, data: dict):
    """Начинает бой в комнате."""
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
        return {"success": False, "message": "Только GM может начать бой"}
    
    # Получаем участников
    entities_data = data.get('entities', [])
    entities = []
    for e in entities_data:
        entity = CombatEntity(
            character_id=e.get('character_id', 0),
            name=e.get('name', 'Неизвестный'),
            entity_type=CombatEntityType(e.get('entity_type', 'npc')),
            initiative=e.get('initiative', random.randint(1, 20)),
            current_hp=e.get('current_hp', 20),
            max_hp=e.get('max_hp', 20),
            armor_class=e.get('armor_class', 10),
            x=e.get('x', 0),
            y=e.get('y', 0),
            token_id=e.get('token_id', 0)
        )
        entities.append(entity)
    
    if not entities:
        session.close()
        return {"success": False, "message": "Нет участников для боя"}
    
    # Начинаем бой
    success = combat_manager.start_combat(room.id, entities)
    
    if success:
        # Обновляем состояние комнаты
        room.state = RoomState.COMBAT
        session.commit()
        session.close()
        
        # Уведомляем всех в комнате
        engine = combat_manager.get_engine(room.id)
        await broadcast_to_room(room.id, {
            'type': 'combat_started',
            'state': engine.get_state() if engine else {}
        })
        
        return {
            'success': True,
            'state': engine.get_state() if engine else {}
        }
    
    session.close()
    return {"success": False, "message": "Не удалось начать бой"}

@app.post("/api/combat/end")
async def end_combat(request: Request, data: dict):
    """Завершает бой в комнате."""
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
    
    success = combat_manager.end_combat(room.id)
    
    if success:
        room.state = RoomState.EXPLORATION
        session.commit()
        session.close()
        
        await broadcast_to_room(room.id, {
            'type': 'combat_ended',
            'message': 'Бой завершён'
        })
        
        return {'success': True, 'message': 'Бой завершён'}
    
    session.close()
    return {"success": False, "message": "Не удалось завершить бой"}

@app.get("/api/combat/state/{room_id}")
async def get_combat_state(room_id: str):
    """Получает состояние боя в комнате."""
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    engine = combat_manager.get_engine(room.id)
    session.close()
    
    if not engine:
        return {"success": False, "message": "Бой не активен"}
    
    return {
        'success': True,
        'state': engine.get_state()
    }

@app.post("/api/combat/action")
async def combat_action(request: Request, data: dict):
    """Выполняет действие в бою."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id_str = data.get('room_id')
    entity_id = data.get('entity_id')
    action_data = data.get('action', {})
    
    if not room_id_str or not entity_id:
        return {"success": False, "message": "Не указаны room_id или entity_id"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    engine = combat_manager.get_engine(room.id)
    if not engine:
        session.close()
        return {"success": False, "message": "Бой не активен"}
    
    result = engine.perform_action(entity_id, action_data)
    session.close()
    
    # Уведомляем всех в комнате
    await broadcast_to_room(room.id, {
        'type': 'combat_action',
        'entity_id': entity_id,
        'action': action_data,
        'result': result,
        'state': engine.get_state()
    })
    
    return result

@app.post("/api/combat/skip_turn")
async def skip_turn(request: Request, data: dict):
    """Пропускает ход в бою."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    room_id_str = data.get('room_id')
    entity_id = data.get('entity_id')
    
    if not room_id_str or not entity_id:
        return {"success": False, "message": "Не указаны room_id или entity_id"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id_str).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    engine = combat_manager.get_engine(room.id)
    if not engine:
        session.close()
        return {"success": False, "message": "Бой не активен"}
    
    success = engine.skip_turn(entity_id)
    session.close()
    
    if success:
        await broadcast_to_room(room.id, {
            'type': 'combat_turn_skipped',
            'entity_id': entity_id,
            'state': engine.get_state()
        })
        return {'success': True}
    
    return {"success": False, "message": "Не удалось пропустить ход"}

# ============================================================
# 9. WEBSOCKET HELPER
# ============================================================

async def broadcast_to_room(room_id: int, message: dict):
    """Отправляет сообщение всем в комнате."""
    for ws in connections.get(room_id, []):
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass

# ============================================================
# 10. БЫСТРЫЙ СТАРТ ДЛЯ ТЕСТИРОВАНИЯ
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
# 11. WEBSOCKET
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
                
                elif msg_type == 'combat_action':
                    # Обработка боевого действия через WebSocket
                    entity_id = msg.get('entity_id')
                    action_data = msg.get('action', {})
                    
                    if entity_id:
                        engine = combat_manager.get_engine(room.id)
                        if engine:
                            result = engine.perform_action(entity_id, action_data)
                            await broadcast_to_room(room.id, {
                                'type': 'combat_action_result',
                                'entity_id': entity_id,
                                'action': action_data,
                                'result': result,
                                'state': engine.get_state()
                            })
                
                elif msg_type == 'combat_skip_turn':
                    entity_id = msg.get('entity_id')
                    if entity_id:
                        engine = combat_manager.get_engine(room.id)
                        if engine:
                            success = engine.skip_turn(entity_id)
                            if success:
                                await broadcast_to_room(room.id, {
                                    'type': 'combat_turn_skipped',
                                    'entity_id': entity_id,
                                    'state': engine.get_state()
                                })
                
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        if room.id in connections:
            if websocket in connections[room.id]:
                connections[room.id].remove(websocket)
            if not connections[room.id]:
                del connections[room.id]

# ============================================================
# 12. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
