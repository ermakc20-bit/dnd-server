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

class InventoryEventType(str, Enum):
    ITEM_ADDED = "item_added"
    ITEM_REMOVED = "item_removed"
    ITEM_MOVED = "item_moved"
    ITEM_USED = "item_used"
    ITEM_DROPPED = "item_dropped"
    ITEM_TRANSFERRED = "item_transferred"
    INVENTORY_OPENED = "inventory_opened"
    INVENTORY_CLOSED = "inventory_closed"
    STACK_SPLIT = "stack_split"
    STACK_MERGED = "stack_merged"

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
# 3. INVENTORY SYSTEM
# ============================================================

@dataclass
class InventoryItem:
    """Универсальный предмет инвентаря."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ''
    description: str = ''
    icon: str = ''
    category: str = 'Misc'
    weight: float = 0.0
    quantity: int = 1
    max_quantity: int = 999
    stackable: bool = True
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    container_id: str = ''  # Для вложенных контейнеров
    position: int = 0  # Порядок в инвентаре
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'category': self.category,
            'weight': self.weight,
            'quantity': self.quantity,
            'max_quantity': self.max_quantity,
            'stackable': self.stackable,
            'tags': self.tags,
            'metadata': self.metadata,
            'container_id': self.container_id,
            'position': self.position
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'InventoryItem':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', ''),
            description=data.get('description', ''),
            icon=data.get('icon', ''),
            category=data.get('category', 'Misc'),
            weight=data.get('weight', 0.0),
            quantity=data.get('quantity', 1),
            max_quantity=data.get('max_quantity', 999),
            stackable=data.get('stackable', True),
            tags=data.get('tags', []),
            metadata=data.get('metadata', {}),
            container_id=data.get('container_id', ''),
            position=data.get('position', 0)
        )
    
    def can_stack_with(self, other: 'InventoryItem') -> bool:
        """Проверяет, можно ли объединить предметы."""
        if not self.stackable or not other.stackable:
            return False
        if self.name != other.name:
            return False
        if self.category != other.category:
            return False
        return True
    
    def stack_with(self, other: 'InventoryItem') -> int:
        """Объединяет предметы. Возвращает количество перенесённых предметов."""
        if not self.can_stack_with(other):
            return 0
        space = self.max_quantity - self.quantity
        transfer = min(space, other.quantity)
        self.quantity += transfer
        other.quantity -= transfer
        return transfer


class Inventory:
    """
    Универсальный инвентарь.
    Не знает правил игровых систем.
    Только хранение и управление предметами.
    """
    
    def __init__(self, owner_id: int = 0, owner_type: str = 'character'):
        self.owner_id = owner_id
        self.owner_type = owner_type
        self._items: Dict[str, InventoryItem] = {}
        self._container_items: Dict[str, List[str]] = {}  # container_id -> [item_ids]
        self._event_listeners: Dict[InventoryEventType, List[Callable]] = {}
    
    # ===== УПРАВЛЕНИЕ ПРЕДМЕТАМИ =====
    
    def add_item(self, item: InventoryItem, container_id: str = '') -> bool:
        """Добавляет предмет в инвентарь."""
        # Проверяем, можно ли добавить в стек
        if item.stackable:
            for existing in self._items.values():
                if existing.can_stack_with(item) and existing.container_id == container_id:
                    existing.quantity += item.quantity
                    self._publish_event(InventoryEventType.ITEM_ADDED, item)
                    return True
        
        # Добавляем новый предмет
        item.container_id = container_id
        item.position = len(self._items)
        self._items[item.id] = item
        
        if container_id:
            if container_id not in self._container_items:
                self._container_items[container_id] = []
            self._container_items[container_id].append(item.id)
        
        self._publish_event(InventoryEventType.ITEM_ADDED, item)
        return True
    
    def remove_item(self, item_id: str, quantity: int = None) -> Optional[InventoryItem]:
        """Удаляет предмет из инвентаря."""
        item = self._items.get(item_id)
        if not item:
            return None
        
        if quantity is not None and quantity < item.quantity:
            # Удаляем часть стека
            removed = InventoryItem(
                name=item.name,
                description=item.description,
                icon=item.icon,
                category=item.category,
                weight=item.weight,
                quantity=quantity,
                max_quantity=item.max_quantity,
                stackable=item.stackable,
                tags=item.tags.copy(),
                metadata=item.metadata.copy()
            )
            item.quantity -= quantity
            self._publish_event(InventoryEventType.ITEM_REMOVED, removed)
            return removed
        else:
            # Удаляем весь предмет
            if item.container_id in self._container_items:
                if item.id in self._container_items[item.container_id]:
                    self._container_items[item.container_id].remove(item.id)
            
            del self._items[item_id]
            self._publish_event(InventoryEventType.ITEM_REMOVED, item)
            return item
    
    def get_item(self, item_id: str) -> Optional[InventoryItem]:
        """Получает предмет по ID."""
        return self._items.get(item_id)
    
    def get_items(self, container_id: str = '') -> List[InventoryItem]:
        """Получает все предметы в контейнере."""
        if container_id:
            item_ids = self._container_items.get(container_id, [])
            return [self._items[iid] for iid in item_ids if iid in self._items]
        return list(self._items.values())
    
    def get_all_items(self) -> List[InventoryItem]:
        """Получает все предметы."""
        return list(self._items.values())
    
    # ===== ПЕРЕМЕЩЕНИЕ ПРЕДМЕТОВ =====
    
    def move_item(self, item_id: str, target_container_id: str) -> bool:
        """Перемещает предмет в другой контейнер."""
        item = self._items.get(item_id)
        if not item:
            return False
        
        # Удаляем из старого контейнера
        if item.container_id in self._container_items:
            if item.id in self._container_items[item.container_id]:
                self._container_items[item.container_id].remove(item.id)
        
        # Добавляем в новый контейнер
        item.container_id = target_container_id
        if target_container_id:
            if target_container_id not in self._container_items:
                self._container_items[target_container_id] = []
            self._container_items[target_container_id].append(item.id)
        
        self._publish_event(InventoryEventType.ITEM_MOVED, item)
        return True
    
    def transfer_item(self, item_id: str, target_inventory: 'Inventory', quantity: int = None) -> bool:
        """Передаёт предмет другому инвентарю."""
        item = self.remove_item(item_id, quantity)
        if not item:
            return False
        
        success = target_inventory.add_item(item)
        if success:
            self._publish_event(InventoryEventType.ITEM_TRANSFERRED, item)
        else:
            # Возвращаем предмет обратно
            self.add_item(item)
        
        return success
    
    # ===== ПОИСК И ФИЛЬТРАЦИЯ =====
    
    def find_by_name(self, name: str) -> List[InventoryItem]:
        """Ищет предметы по имени."""
        name_lower = name.lower()
        return [item for item in self._items.values() if name_lower in item.name.lower()]
    
    def find_by_category(self, category: str) -> List[InventoryItem]:
        """Ищет предметы по категории."""
        return [item for item in self._items.values() if item.category == category]
    
    def find_by_tag(self, tag: str) -> List[InventoryItem]:
        """Ищет предметы по тегу."""
        return [item for item in self._items.values() if tag in item.tags]
    
    def find_by_metadata(self, key: str, value: Any) -> List[InventoryItem]:
        """Ищет предметы по метаданным."""
        return [
            item for item in self._items.values()
            if item.metadata.get(key) == value
        ]
    
    def filter(self, category: str = None, tags: List[str] = None, 
               min_weight: float = None, max_weight: float = None) -> List[InventoryItem]:
        """Фильтрует предметы по параметрам."""
        result = list(self._items.values())
        
        if category:
            result = [item for item in result if item.category == category]
        
        if tags:
            result = [item for item in result if any(tag in item.tags for tag in tags)]
        
        if min_weight is not None:
            result = [item for item in result if item.weight >= min_weight]
        
        if max_weight is not None:
            result = [item for item in result if item.weight <= max_weight]
        
        return result
    
    # ===== СТЕКИ =====
    
    def split_stack(self, item_id: str, quantity: int) -> Optional[InventoryItem]:
        """Разделяет стек предметов."""
        item = self._items.get(item_id)
        if not item or not item.stackable:
            return None
        
        if quantity <= 0 or quantity >= item.quantity:
            return None
        
        new_item = InventoryItem(
            name=item.name,
            description=item.description,
            icon=item.icon,
            category=item.category,
            weight=item.weight,
            quantity=quantity,
            max_quantity=item.max_quantity,
            stackable=item.stackable,
            tags=item.tags.copy(),
            metadata=item.metadata.copy(),
            container_id=item.container_id
        )
        
        item.quantity -= quantity
        self._items[new_item.id] = new_item
        
        if item.container_id in self._container_items:
            self._container_items[item.container_id].append(new_item.id)
        
        self._publish_event(InventoryEventType.STACK_SPLIT, new_item)
        return new_item
    
    def merge_stacks(self, source_id: str, target_id: str) -> int:
        """Объединяет два стека предметов."""
        source = self._items.get(source_id)
        target = self._items.get(target_id)
        
        if not source or not target:
            return 0
        
        if not source.can_stack_with(target):
            return 0
        
        transferred = target.stack_with(source)
        if transferred > 0:
            if source.quantity <= 0:
                self.remove_item(source.id)
            self._publish_event(InventoryEventType.STACK_MERGED, target)
        
        return transferred
    
    # ===== ВЕС =====
    
    def get_total_weight(self) -> float:
        """Вычисляет общий вес инвентаря."""
        return sum(item.weight * item.quantity for item in self._items.values())
    
    # ===== ИНТЕГРАЦИЯ С CHARACTER =====
    
    def load_from_character(self, character: Character):
        """Загружает инвентарь из Character."""
        self._items = {}
        self._container_items = {}
        
        inventory_data = json.loads(character.inventory) if character.inventory else []
        for item_data in inventory_data:
            item = InventoryItem.from_dict(item_data)
            self._items[item.id] = item
            if item.container_id:
                if item.container_id not in self._container_items:
                    self._container_items[item.container_id] = []
                self._container_items[item.container_id].append(item.id)
    
    def save_to_character(self, character: Character):
        """Сохраняет инвентарь в Character."""
        character.inventory = json.dumps([item.to_dict() for item in self._items.values()])
    
    # ===== СОБЫТИЯ =====
    
    def subscribe(self, event_type: InventoryEventType, callback: Callable):
        """Подписывается на события инвентаря."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(callback)
    
    def _publish_event(self, event_type: InventoryEventType, item: InventoryItem):
        """Публикует событие."""
        if event_type in self._event_listeners:
            for callback in self._event_listeners[event_type]:
                try:
                    callback(event_type, item)
                except Exception as e:
                    print(f"Error in inventory event callback: {e}")

# ============================================================
# 4. INVENTORY MANAGER
# ============================================================

class InventoryManager:
    """Управляет инвентарями всех персонажей."""
    
    def __init__(self):
        self._inventories: Dict[int, Inventory] = {}  # character_id -> Inventory
    
    def get_inventory(self, character_id: int) -> Optional[Inventory]:
        """Получает инвентарь персонажа."""
        return self._inventories.get(character_id)
    
    def load_inventory(self, character: Character) -> Inventory:
        """Загружает инвентарь персонажа."""
        inventory = Inventory(owner_id=character.id, owner_type='character')
        inventory.load_from_character(character)
        self._inventories[character.id] = inventory
        return inventory
    
    def save_inventory(self, character: Character) -> bool:
        """Сохраняет инвентарь персонажа."""
        inventory = self._inventories.get(character.id)
        if not inventory:
            return False
        inventory.save_to_character(character)
        return True
    
    def add_item_to_character(self, character: Character, item_data: dict) -> bool:
        """Добавляет предмет персонажу."""
        inventory = self.get_inventory(character.id)
        if not inventory:
            inventory = self.load_inventory(character)
        
        item = InventoryItem.from_dict(item_data)
        success = inventory.add_item(item)
        if success:
            self.save_inventory(character)
        return success
    
    def remove_item_from_character(self, character: Character, item_id: str) -> bool:
        """Удаляет предмет у персонажа."""
        inventory = self.get_inventory(character.id)
        if not inventory:
            return False
        
        item = inventory.remove_item(item_id)
        if item:
            self.save_inventory(character)
            return True
        return False
    
    def transfer_item_between_characters(self, source: Character, target: Character, 
                                         item_id: str, quantity: int = None) -> bool:
        """Передаёт предмет между персонажами."""
        source_inv = self.get_inventory(source.id)
        target_inv = self.get_inventory(target.id)
        
        if not source_inv:
            source_inv = self.load_inventory(source)
        if not target_inv:
            target_inv = self.load_inventory(target)
        
        item = source_inv.get_item(item_id)
        if not item:
            return False
        
        success = source_inv.transfer_item(item_id, target_inv, quantity)
        if success:
            self.save_inventory(source)
            self.save_inventory(target)
        return success

inventory_manager = InventoryManager()

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
# 8. API: INVENTORY
# ============================================================

@app.post("/api/inventory/load/{character_id}")
async def load_inventory(character_id: int):
    """Загружает инвентарь персонажа."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        inventory = inventory_manager.load_inventory(character)
        return {
            'success': True,
            'items': [item.to_dict() for item in inventory.get_all_items()]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/inventory/add")
async def add_item(request: Request, data: dict):
    """Добавляет предмет персонажу."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    item_data = data.get('item')
    
    if not character_id or not item_data:
        return {"success": False, "message": "Не указаны character_id или item"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = inventory_manager.add_item_to_character(character, item_data)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Предмет добавлен'}
        return {"success": False, "message": "Не удалось добавить предмет"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/inventory/remove")
async def remove_item(request: Request, data: dict):
    """Удаляет предмет у персонажа."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    item_id = data.get('item_id')
    
    if not character_id or not item_id:
        return {"success": False, "message": "Не указаны character_id или item_id"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = inventory_manager.remove_item_from_character(character, item_id)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Предмет удалён'}
        return {"success": False, "message": "Предмет не найден"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/inventory/transfer")
async def transfer_item(request: Request, data: dict):
    """Передаёт предмет между персонажами."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    source_id = data.get('source_id')
    target_id = data.get('target_id')
    item_id = data.get('item_id')
    quantity = data.get('quantity')
    
    if not source_id or not target_id or not item_id:
        return {"success": False, "message": "Не указаны все параметры"}
    
    session = Session()
    try:
        source = session.query(Character).filter_by(id=source_id).first()
        target = session.query(Character).filter_by(id=target_id).first()
        
        if not source or not target:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = inventory_manager.transfer_item_between_characters(source, target, item_id, quantity)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Предмет передан'}
        return {"success": False, "message": "Не удалось передать предмет"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/inventory/use")
async def use_item(request: Request, data: dict):
    """Использует предмет (вызывает Game Action System)."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    # Здесь будет вызов Game Action System
    # Пока возвращаем заглушку
    return {
        'success': True,
        'message': 'Предмет использован',
        'action_required': True
    }

@app.get("/api/inventory/search")
async def search_items(request: Request, character_id: int, query: str):
    """Ищет предметы в инвентаре."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        inventory = inventory_manager.get_inventory(character_id)
        if not inventory:
            inventory = inventory_manager.load_inventory(character)
        
        results = inventory.find_by_name(query)
        return {
            'success': True,
            'results': [item.to_dict() for item in results]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/inventory/filter")
async def filter_items(request: Request, character_id: int, category: str = None):
    """Фильтрует предметы по категории."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        inventory = inventory_manager.get_inventory(character_id)
        if not inventory:
            inventory = inventory_manager.load_inventory(character)
        
        results = inventory.find_by_category(category) if category else inventory.get_all_items()
        return {
            'success': True,
            'items': [item.to_dict() for item in results]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

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
                
                elif msg_type == 'inventory_add':
                    # Добавление предмета через WebSocket
                    character_id = msg.get('character_id')
                    item_data = msg.get('item')
                    
                    if character_id and item_data:
                        session2 = Session()
                        character = session2.query(Character).filter_by(id=character_id).first()
                        if character:
                            success = inventory_manager.add_item_to_character(character, item_data)
                            if success:
                                session2.commit()
                                await broadcast_to_room(room.id, {
                                    'type': 'inventory_updated',
                                    'character_id': character_id,
                                    'items': inventory_manager.get_inventory(character_id).get_all_items()
                                })
                        session2.close()
                
                elif msg_type == 'inventory_remove':
                    character_id = msg.get('character_id')
                    item_id = msg.get('item_id')
                    
                    if character_id and item_id:
                        session2 = Session()
                        character = session2.query(Character).filter_by(id=character_id).first()
                        if character:
                            success = inventory_manager.remove_item_from_character(character, item_id)
                            if success:
                                session2.commit()
                                await broadcast_to_room(room.id, {
                                    'type': 'inventory_updated',
                                    'character_id': character_id,
                                    'items': inventory_manager.get_inventory(character_id).get_all_items()
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
# 11. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
