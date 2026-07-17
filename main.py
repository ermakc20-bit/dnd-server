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
    EQUIPMENT_CHANGED = "equipment_changed"
    LOOT_ADDED = "loot_added"
    LOOT_REMOVED = "loot_removed"

class EquipmentSlot(str, Enum):
    HEAD = "head"
    BODY = "body"
    LEGS = "legs"
    HANDS = "hands"
    FEET = "feet"
    RING_1 = "ring_1"
    RING_2 = "ring_2"
    NECK = "neck"
    MAIN_HAND = "main_hand"
    OFF_HAND = "off_hand"
    BACK = "back"
    ACCESSORY = "accessory"
    CUSTOM = "custom"

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
    max_weight = Column(Float, default=100.0)
    max_slots = Column(Integer, default=50)
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
# 3. INVENTORY SYSTEM (ФИНАЛЬНАЯ ВЕРСИЯ)
# ============================================================

@dataclass
class InventoryItem:
    """Универсальный предмет инвентаря. Не зависит от сеттинга."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ''
    description: str = ''
    icon: str = ''
    type: str = 'misc'  # weapon, armor, consumable, tool, key, quest, container, misc, currency, document, artifact, ammo, spellbook, ingredient, custom
    weight: float = 0.0
    rarity: str = 'common'  # common, uncommon, rare, epic, legendary, artifact, custom
    stackable: bool = True
    quantity: int = 1
    max_quantity: int = 999
    actions: List[str] = field(default_factory=list)  # use, equip, drink, read, shoot, etc.
    effects: List[Dict] = field(default_factory=list)  # [{"type": "damage", "value": "2d6"}, {"type": "heal", "value": "1d8"}]
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)  # {"damage": "2d6", "range": 6, "ammo": 5}
    container_id: str = ''  # Для вложенных контейнеров
    position: int = 0  # Порядок в инвентаре
    equipped_slot: Optional[str] = None  # Если предмет экипирован
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'type': self.type,
            'weight': self.weight,
            'rarity': self.rarity,
            'stackable': self.stackable,
            'quantity': self.quantity,
            'max_quantity': self.max_quantity,
            'actions': self.actions,
            'effects': self.effects,
            'tags': self.tags,
            'metadata': self.metadata,
            'container_id': self.container_id,
            'position': self.position,
            'equipped_slot': self.equipped_slot
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'InventoryItem':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', ''),
            description=data.get('description', ''),
            icon=data.get('icon', ''),
            type=data.get('type', 'misc'),
            weight=data.get('weight', 0.0),
            rarity=data.get('rarity', 'common'),
            stackable=data.get('stackable', True),
            quantity=data.get('quantity', 1),
            max_quantity=data.get('max_quantity', 999),
            actions=data.get('actions', []),
            effects=data.get('effects', []),
            tags=data.get('tags', []),
            metadata=data.get('metadata', {}),
            container_id=data.get('container_id', ''),
            position=data.get('position', 0),
            equipped_slot=data.get('equipped_slot')
        )
    
    def can_stack_with(self, other: 'InventoryItem') -> bool:
        """Проверяет, можно ли объединить предметы."""
        if not self.stackable or not other.stackable:
            return False
        if self.name != other.name:
            return False
        if self.type != other.type:
            return False
        if self.metadata != other.metadata:
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
    
    def get_total_weight(self) -> float:
        """Возвращает общий вес предмета (вес * количество)."""
        return self.weight * self.quantity


class Inventory:
    """
    Универсальный инвентарь. Не зависит от сеттинга.
    Только хранение и управление предметами.
    """
    
    def __init__(self, owner_id: int = 0, owner_type: str = 'character'):
        self.owner_id = owner_id
        self.owner_type = owner_type
        self._items: Dict[str, InventoryItem] = {}
        self._container_items: Dict[str, List[str]] = {}  # container_id -> [item_ids]
        self._equipped_items: Dict[str, str] = {}  # slot -> item_id
        self._event_listeners: Dict[InventoryEventType, List[Callable]] = {}
    
    # ===== УПРАВЛЕНИЕ ПРЕДМЕТАМИ =====
    
    def add_item(self, item: InventoryItem, container_id: str = '') -> bool:
        """Добавляет предмет в инвентарь."""
        # Проверяем лимит веса
        if self.get_total_weight() + item.get_total_weight() > self.get_max_weight():
            self._publish_event(InventoryEventType.ITEM_ADDED, item, {'error': 'weight_limit_exceeded'})
            return False
        
        # Проверяем лимит слотов
        if len(self._items) >= self.get_max_slots():
            self._publish_event(InventoryEventType.ITEM_ADDED, item, {'error': 'slot_limit_exceeded'})
            return False
        
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
        
        # Если предмет экипирован, снимаем его
        if item.equipped_slot:
            self.unequip_item(item_id)
        
        if quantity is not None and quantity < item.quantity:
            # Удаляем часть стека
            removed = InventoryItem(
                name=item.name,
                description=item.description,
                icon=item.icon,
                type=item.type,
                weight=item.weight,
                rarity=item.rarity,
                stackable=item.stackable,
                quantity=quantity,
                max_quantity=item.max_quantity,
                actions=item.actions.copy(),
                effects=item.effects.copy(),
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
    
    # ===== ЭКИПИРОВКА =====
    
    def equip_item(self, item_id: str, slot: str) -> bool:
        """Экипирует предмет в указанный слот."""
        item = self._items.get(item_id)
        if not item:
            return False
        
        # Проверяем, что предмет можно экипировать
        if 'equip' not in item.actions:
            return False
        
        # Если слот занят, снимаем старый предмет
        if slot in self._equipped_items:
            old_item_id = self._equipped_items[slot]
            old_item = self._items.get(old_item_id)
            if old_item:
                old_item.equipped_slot = None
        
        # Экипируем новый предмет
        item.equipped_slot = slot
        self._equipped_items[slot] = item_id
        
        self._publish_event(InventoryEventType.EQUIPMENT_CHANGED, item)
        return True
    
    def unequip_item(self, item_id: str) -> bool:
        """Снимает предмет с экипировки."""
        item = self._items.get(item_id)
        if not item or not item.equipped_slot:
            return False
        
        slot = item.equipped_slot
        if slot in self._equipped_items:
            del self._equipped_items[slot]
        
        item.equipped_slot = None
        self._publish_event(InventoryEventType.EQUIPMENT_CHANGED, item)
        return True
    
    def get_equipped_items(self) -> Dict[str, InventoryItem]:
        """Получает все экипированные предметы."""
        result = {}
        for slot, item_id in self._equipped_items.items():
            item = self._items.get(item_id)
            if item:
                result[slot] = item
        return result
    
    # ===== ВЕС И ЛИМИТЫ =====
    
    def get_total_weight(self) -> float:
        """Вычисляет общий вес инвентаря."""
        return sum(item.get_total_weight() for item in self._items.values())
    
    def get_max_weight(self) -> float:
        """Возвращает максимальный вес (из Character)."""
        return getattr(self, '_max_weight', 100.0)
    
    def get_max_slots(self) -> int:
        """Возвращает максимальное количество слотов."""
        return getattr(self, '_max_slots', 50)
    
    def set_limits(self, max_weight: float, max_slots: int):
        """Устанавливает лимиты инвентаря."""
        self._max_weight = max_weight
        self._max_slots = max_slots
    
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
    
    def drop_item(self, item_id: str, quantity: int = None) -> Optional[InventoryItem]:
        """Выбрасывает предмет."""
        item = self.remove_item(item_id, quantity)
        if item:
            self._publish_event(InventoryEventType.ITEM_DROPPED, item)
        return item
    
    # ===== ПОИСК И ФИЛЬТРАЦИЯ =====
    
    def find_by_name(self, name: str) -> List[InventoryItem]:
        """Ищет предметы по имени."""
        name_lower = name.lower()
        return [item for item in self._items.values() if name_lower in item.name.lower()]
    
    def find_by_type(self, type_name: str) -> List[InventoryItem]:
        """Ищет предметы по типу."""
        return [item for item in self._items.values() if item.type == type_name]
    
    def find_by_tag(self, tag: str) -> List[InventoryItem]:
        """Ищет предметы по тегу."""
        return [item for item in self._items.values() if tag in item.tags]
    
    def find_by_action(self, action: str) -> List[InventoryItem]:
        """Ищет предметы по действию."""
        return [item for item in self._items.values() if action in item.actions]
    
    def filter_by_rarity(self, rarity: str) -> List[InventoryItem]:
        """Фильтрует по редкости."""
        return [item for item in self._items.values() if item.rarity == rarity]
    
    # ===== СОБЫТИЯ =====
    
    def subscribe(self, event_type: InventoryEventType, callback: Callable):
        """Подписывается на события инвентаря."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(callback)
    
    def _publish_event(self, event_type: InventoryEventType, item: InventoryItem, extra: dict = None):
        """Публикует событие."""
        if event_type in self._event_listeners:
            for callback in self._event_listeners[event_type]:
                try:
                    callback(event_type, item, extra or {})
                except Exception as e:
                    print(f"Error in inventory event callback: {e}")
    
    # ===== СЕРИАЛИЗАЦИЯ =====
    
    def to_dict(self) -> dict:
        """Преобразует инвентарь в словарь для JSON."""
        return {
            'owner_id': self.owner_id,
            'owner_type': self.owner_type,
            'items': [item.to_dict() for item in self._items.values()],
            'equipped': {slot: item_id for slot, item_id in self._equipped_items.items()},
            'total_weight': self.get_total_weight(),
            'max_weight': self.get_max_weight(),
            'max_slots': self.get_max_slots(),
            'item_count': len(self._items)
        }
    
    def load_from_dict(self, data: dict):
        """Загружает инвентарь из словаря."""
        self._items = {}
        self._container_items = {}
        self._equipped_items = {}
        
        for item_data in data.get('items', []):
            item = InventoryItem.from_dict(item_data)
            self._items[item.id] = item
            if item.container_id:
                if item.container_id not in self._container_items:
                    self._container_items[item.container_id] = []
                self._container_items[item.container_id].append(item.id)
            if item.equipped_slot:
                self._equipped_items[item.equipped_slot] = item.id
        
        self.set_limits(
            data.get('max_weight', 100.0),
            data.get('max_slots', 50)
        )


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
        inventory.set_limits(character.max_weight, character.max_slots)
        
        if character.inventory:
            inventory_data = json.loads(character.inventory)
            inventory.load_from_dict(inventory_data)
        
        self._inventories[character.id] = inventory
        return inventory
    
    def save_inventory(self, character: Character) -> bool:
        """Сохраняет инвентарь персонажа."""
        inventory = self._inventories.get(character.id)
        if not inventory:
            return False
        character.inventory = json.dumps(inventory.to_dict())
        return True
    
    def add_item(self, character: Character, item_data: dict) -> bool:
        """Добавляет предмет персонажу."""
        inventory = self.get_inventory(character.id)
        if not inventory:
            inventory = self.load_inventory(character)
        
        item = InventoryItem.from_dict(item_data)
        success = inventory.add_item(item)
        if success:
            self.save_inventory(character)
        return success
    
    def remove_item(self, character: Character, item_id: str, quantity: int = None) -> bool:
        """Удаляет предмет у персонажа."""
        inventory = self.get_inventory(character.id)
        if not inventory:
            return False
        
        item = inventory.remove_item(item_id, quantity)
        if item:
            self.save_inventory(character)
            return True
        return False
    
    def transfer_item(self, source: Character, target: Character, item_id: str, quantity: int = None) -> bool:
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
    
    def equip_item(self, character: Character, item_id: str, slot: str) -> bool:
        """Экипирует предмет."""
        inventory = self.get_inventory(character.id)
        if not inventory:
            return False
        
        success = inventory.equip_item(item_id, slot)
        if success:
            self.save_inventory(character)
        return success
    
    def unequip_item(self, character: Character, item_id: str) -> bool:
        """Снимает предмет с экипировки."""
        inventory = self.get_inventory(character.id)
        if not inventory:
            return False
        
        success = inventory.unequip_item(item_id)
        if success:
            self.save_inventory(character)
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
            'inventory': inventory.to_dict()
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
        
        success = inventory_manager.add_item(character, item_data)
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
    quantity = data.get('quantity')
    
    if not character_id or not item_id:
        return {"success": False, "message": "Не указаны character_id или item_id"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = inventory_manager.remove_item(character, item_id, quantity)
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
        
        success = inventory_manager.transfer_item(source, target, item_id, quantity)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Предмет передан'}
        return {"success": False, "message": "Не удалось передать предмет"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/inventory/equip")
async def equip_item(request: Request, data: dict):
    """Экипирует предмет."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    character_id = data.get('character_id')
    item_id = data.get('item_id')
    slot = data.get('slot')
    
    if not character_id or not item_id or not slot:
        return {"success": False, "message": "Не указаны все параметры"}
    
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        success = inventory_manager.equip_item(character, item_id, slot)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Предмет экипирован'}
        return {"success": False, "message": "Не удалось экипировать предмет"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/inventory/unequip")
async def unequip_item(request: Request, data: dict):
    """Снимает предмет с экипировки."""
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
        
        success = inventory_manager.unequip_item(character, item_id)
        session.commit()
        
        if success:
            return {'success': True, 'message': 'Предмет снят'}
        return {"success": False, "message": "Не удалось снять предмет"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/inventory/search")
async def search_items(character_id: int, query: str):
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
async def filter_items(character_id: int, item_type: str = None, rarity: str = None):
    """Фильтрует предметы по типу или редкости."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        inventory = inventory_manager.get_inventory(character_id)
        if not inventory:
            inventory = inventory_manager.load_inventory(character)
        
        result = inventory.get_all_items()
        if item_type:
            result = [item for item in result if item.type == item_type]
        if rarity:
            result = [item for item in result if item.rarity == rarity]
        
        return {
            'success': True,
            'items': [item.to_dict() for item in result]
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/inventory/equipment/{character_id}")
async def get_equipment(character_id: int):
    """Получает экипированные предметы."""
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        
        inventory = inventory_manager.get_inventory(character_id)
        if not inventory:
            inventory = inventory_manager.load_inventory(character)
        
        equipped = inventory.get_equipped_items()
        return {
            'success': True,
            'equipment': {slot: item.to_dict() for slot, item in equipped.items()}
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
                    character_id = msg.get('character_id')
                    item_data = msg.get('item')
                    
                    if character_id and item_data:
                        session2 = Session()
                        character = session2.query(Character).filter_by(id=character_id).first()
                        if character:
                            success = inventory_manager.add_item(character, item_data)
                            if success:
                                session2.commit()
                                await broadcast_to_room(room.id, {
                                    'type': 'inventory_updated',
                                    'character_id': character_id,
                                    'inventory': inventory_manager.get_inventory(character_id).to_dict()
                                })
                        session2.close()
                
                elif msg_type == 'inventory_remove':
                    character_id = msg.get('character_id')
                    item_id = msg.get('item_id')
                    
                    if character_id and item_id:
                        session2 = Session()
                        character = session2.query(Character).filter_by(id=character_id).first()
                        if character:
                            success = inventory_manager.remove_item(character, item_id)
                            if success:
                                session2.commit()
                                await broadcast_to_room(room.id, {
                                    'type': 'inventory_updated',
                                    'character_id': character_id,
                                    'inventory': inventory_manager.get_inventory(character_id).to_dict()
                                })
                        session2.close()
                
                elif msg_type == 'inventory_equip':
                    character_id = msg.get('character_id')
                    item_id = msg.get('item_id')
                    slot = msg.get('slot')
                    
                    if character_id and item_id and slot:
                        session2 = Session()
                        character = session2.query(Character).filter_by(id=character_id).first()
                        if character:
                            success = inventory_manager.equip_item(character, item_id, slot)
                            if success:
                                session2.commit()
                                await broadcast_to_room(room.id, {
                                    'type': 'inventory_updated',
                                    'character_id': character_id,
                                    'inventory': inventory_manager.get_inventory(character_id).to_dict()
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
