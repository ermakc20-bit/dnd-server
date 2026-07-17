# ============================================================
# 20. UNIVERSAL EVENT SYSTEM
# ============================================================

import asyncio
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set, Union
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import defaultdict
import functools

# ============================================================
# 20.1. БАЗОВЫЕ КЛАССЫ
# ============================================================

class EventPriority(Enum):
    """Приоритет событий."""
    CRITICAL = 0    # Критические (сохранение, валидация)
    HIGH = 1        # Высокий (GM команды, системные)
    NORMAL = 2      # Обычный (игровые действия)
    LOW = 3         # Низкий (логи, аналитика)
    BACKGROUND = 4  # Фоновые (синхронизация)

class EventStatus(Enum):
    """Статус обработки события."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

@dataclass
class GameEvent:
    """Базовый класс игрового события."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    room_id: int = 0
    source: str = ""
    target: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    status: EventStatus = EventStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Преобразует событие в словарь."""
        return {
            'event_id': self.event_id,
            'type': self.type,
            'room_id': self.room_id,
            'source': self.source,
            'target': self.target,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'priority': self.priority.name,
            'status': self.status.value,
            'retry_count': self.retry_count,
            'correlation_id': self.correlation_id,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GameEvent':
        """Создает событие из словаря."""
        event = cls(
            event_id=data.get('event_id', str(uuid.uuid4())),
            type=data.get('type', ''),
            room_id=data.get('room_id', 0),
            source=data.get('source', ''),
            target=data.get('target', ''),
            data=data.get('data', {}),
            priority=EventPriority[data.get('priority', 'NORMAL')],
            correlation_id=data.get('correlation_id')
        )
        if data.get('timestamp'):
            event.timestamp = datetime.fromisoformat(data['timestamp'])
        if data.get('status'):
            event.status = EventStatus(data['status'])
        event.retry_count = data.get('retry_count', 0)
        event.metadata = data.get('metadata', {})
        return event

# ============================================================
# 20.2. EVENT BUS
# ============================================================

class EventBus:
    """
    Центральная шина событий.
    Обеспечивает публикацию и подписку на события.
    """
    
    def __init__(self, name: str = "default"):
        self.name = name
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._subscribers_by_priority: Dict[str, Dict[EventPriority, List[Callable]]] = defaultdict(lambda: defaultdict(list))
        self._queue: asyncio.Queue = asyncio.Queue()
        self._is_running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger(f"event_bus.{name}")
        self._event_history: List[GameEvent] = []
        self._max_history_size = 1000
        self._filters: Dict[str, Callable] = {}
        self._interceptors: List[Callable] = []
        self._error_handlers: List[Callable] = []
        self._processing_lock = asyncio.Lock()
        
    # ===== ПОДПИСКА =====
    
    def subscribe(
        self,
        event_type: str,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL
    ) -> None:
        """
        Подписывает обработчик на событие.
        
        Args:
            event_type: Тип события
            callback: Асинхронная функция-обработчик
            priority: Приоритет обработчика
        """
        if not asyncio.iscoroutinefunction(callback):
            # Оборачиваем синхронную функцию в асинхронную
            @functools.wraps(callback)
            async def async_wrapper(event: GameEvent):
                return callback(event)
            callback = async_wrapper
            
        self._subscribers[event_type].append(callback)
        self._subscribers_by_priority[event_type][priority].append(callback)
        self._logger.debug(f"Subscribed to {event_type}")
    
    def subscribe_many(
        self,
        event_types: List[str],
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL
    ) -> None:
        """
        Подписывает обработчик на несколько типов событий.
        """
        for event_type in event_types:
            self.subscribe(event_type, callback, priority)
    
    def subscribe_global(
        self,
        callback: Callable,
        priority: EventPriority = EventPriority.NORMAL
    ) -> None:
        """
        Подписывает обработчик на все события.
        """
        self.subscribe("*", callback, priority)
    
    def unsubscribe(
        self,
        event_type: str,
        callback: Callable
    ) -> bool:
        """
        Отписывает обработчик.
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
                # Удаляем из списков по приоритетам
                for priority in self._subscribers_by_priority[event_type]:
                    if callback in self._subscribers_by_priority[event_type][priority]:
                        self._subscribers_by_priority[event_type][priority].remove(callback)
                return True
            except ValueError:
                return False
        return False
    
    def unsubscribe_all(self, callback: Callable) -> int:
        """
        Отписывает обработчик от всех событий.
        """
        count = 0
        for event_type in list(self._subscribers.keys()):
            if self.unsubscribe(event_type, callback):
                count += 1
        return count
    
    # ===== ФИЛЬТРЫ =====
    
    def add_filter(self, filter_name: str, filter_func: Callable) -> None:
        """
        Добавляет фильтр для событий.
        Фильтр может модифицировать или отклонять события.
        """
        self._filters[filter_name] = filter_func
    
    def remove_filter(self, filter_name: str) -> None:
        """
        Удаляет фильтр.
        """
        if filter_name in self._filters:
            del self._filters[filter_name]
    
    def add_interceptor(self, interceptor: Callable) -> None:
        """
        Добавляет перехватчик для всех событий.
        """
        self._interceptors.append(interceptor)
    
    def remove_interceptor(self, interceptor: Callable) -> None:
        """
        Удаляет перехватчик.
        """
        if interceptor in self._interceptors:
            self._interceptors.remove(interceptor)
    
    # ===== ПУБЛИКАЦИЯ =====
    
    async def publish(self, event: GameEvent) -> bool:
        """
        Публикует событие в шину.
        
        Returns:
            True если событие было принято, False если отклонено
        """
        # Применяем фильтры
        for filter_name, filter_func in self._filters.items():
            try:
                result = await filter_func(event) if asyncio.iscoroutinefunction(filter_func) else filter_func(event)
                if result is False:
                    self._logger.debug(f"Event {event.event_id} rejected by filter {filter_name}")
                    return False
                if isinstance(result, GameEvent):
                    event = result
            except Exception as e:
                self._logger.error(f"Filter {filter_name} error: {e}")
                return False
        
        # Применяем перехватчики
        for interceptor in self._interceptors:
            try:
                if asyncio.iscoroutinefunction(interceptor):
                    event = await interceptor(event) or event
                else:
                    event = interceptor(event) or event
            except Exception as e:
                self._logger.error(f"Interceptor error: {e}")
        
        # Добавляем в очередь
        await self._queue.put(event)
        
        # Сохраняем в историю
        if len(self._event_history) >= self._max_history_size:
            self._event_history.pop(0)
        self._event_history.append(event)
        
        self._logger.debug(f"Event {event.event_id} published: {event.type}")
        return True
    
    async def publish_many(self, events: List[GameEvent]) -> List[bool]:
        """
        Публикует несколько событий.
        """
        results = []
        for event in events:
            results.append(await self.publish(event))
        return results
    
    def publish_sync(self, event: GameEvent) -> bool:
        """
        Синхронная публикация события.
        """
        return asyncio.run(self.publish(event))
    
    # ===== ОБРАБОТКА =====
    
    async def _process_event(self, event: GameEvent) -> None:
        """
        Обрабатывает событие.
        """
        async with self._processing_lock:
            event.status = EventStatus.PROCESSING
            
            # Получаем обработчики
            handlers = []
            
            # Глобальные обработчики
            if "*" in self._subscribers:
                handlers.extend(self._subscribers["*"])
            
            # Специфичные обработчики
            if event.type in self._subscribers:
                handlers.extend(self._subscribers[event.type])
            
            if not handlers:
                event.status = EventStatus.COMPLETED
                self._logger.debug(f"No handlers for event {event.type}")
                return
            
            # Сортируем по приоритету
            handlers.sort(key=lambda h: self._get_handler_priority(h, event.type))
            
            # Обрабатываем
            for handler in handlers:
                try:
                    result = await handler(event)
                    if result is False:
                        # Обработчик прервал цепочку
                        self._logger.debug(f"Handler stopped chain for event {event.event_id}")
                        break
                except Exception as e:
                    self._logger.error(f"Handler error: {e}")
                    # Уведомляем обработчики ошибок
                    for error_handler in self._error_handlers:
                        try:
                            if asyncio.iscoroutinefunction(error_handler):
                                await error_handler(event, e)
                            else:
                                error_handler(event, e)
                        except:
                            pass
                    
                    # Повторная обработка
                    if event.retry_count < event.max_retries:
                        event.retry_count += 1
                        event.status = EventStatus.RETRYING
                        self._logger.warning(f"Retrying event {event.event_id} ({event.retry_count}/{event.max_retries})")
                        await self._queue.put(event)
                        return
            
            event.status = EventStatus.COMPLETED
    
    def _get_handler_priority(self, handler: Callable, event_type: str) -> int:
        """
        Определяет приоритет обработчика.
        """
        for priority, handlers in self._subscribers_by_priority[event_type].items():
            if handler in handlers:
                return priority.value
        return EventPriority.NORMAL.value
    
    async def _worker(self) -> None:
        """
        Воркер для обработки очереди.
        """
        while self._is_running:
            try:
                event = await self._queue.get()
                await self._process_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Worker error: {e}")
    
    async def start(self) -> None:
        """
        Запускает обработку событий.
        """
        if not self._is_running:
            self._is_running = True
            self._worker_task = asyncio.create_task(self._worker())
            self._logger.info(f"Event bus {self.name} started")
    
    async def stop(self) -> None:
        """
        Останавливает обработку событий.
        """
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        self._logger.info(f"Event bus {self.name} stopped")
    
    # ===== ОШИБКИ =====
    
    def add_error_handler(self, handler: Callable) -> None:
        """
        Добавляет обработчик ошибок.
        """
        self._error_handlers.append(handler)
    
    def remove_error_handler(self, handler: Callable) -> None:
        """
        Удаляет обработчик ошибок.
        """
        if handler in self._error_handlers:
            self._error_handlers.remove(handler)
    
    # ===== ИСТОРИЯ =====
    
    def get_history(
        self,
        event_type: Optional[str] = None,
        room_id: Optional[int] = None,
        limit: int = 100
    ) -> List[GameEvent]:
        """
        Получает историю событий.
        """
        events = self._event_history[-limit:] if limit > 0 else self._event_history
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        if room_id:
            events = [e for e in events if e.room_id == room_id]
        
        return events
    
    def clear_history(self) -> None:
        """
        Очищает историю событий.
        """
        self._event_history.clear()
    
    # ===== СТАТУС =====
    
    def get_status(self) -> dict:
        """
        Возвращает статус шины.
        """
        return {
            'name': self.name,
            'is_running': self._is_running,
            'queue_size': self._queue.qsize(),
            'subscribers_count': len(self._subscribers),
            'history_size': len(self._event_history),
            'filters_count': len(self._filters),
            'interceptors_count': len(self._interceptors)
        }

# ============================================================
# 20.3. ПРЕДОПРЕДЕЛЁННЫЕ СОБЫТИЯ
# ============================================================

class EventTypes:
    """Константы типов событий."""
    
    # ===== КОМНАТА =====
    ROOM_CREATED = "RoomCreated"
    ROOM_STARTED = "RoomStarted"
    ROOM_FINISHED = "RoomFinished"
    ROOM_PAUSED = "RoomPaused"
    ROOM_RESUMED = "RoomResumed"
    PLAYER_JOINED = "PlayerJoined"
    PLAYER_LEFT = "PlayerLeft"
    PLAYER_READY = "PlayerReady"
    
    # ===== ПЕРСОНАЖИ =====
    CHARACTER_CREATED = "CharacterCreated"
    CHARACTER_SELECTED = "CharacterSelected"
    CHARACTER_SPAWNED = "CharacterSpawned"
    CHARACTER_REMOVED = "CharacterRemoved"
    CHARACTER_UPDATED = "CharacterUpdated"
    CHARACTER_MOVED = "CharacterMoved"
    CHARACTER_ATTACKED = "CharacterAttacked"
    CHARACTER_DAMAGED = "CharacterDamaged"
    CHARACTER_HEALED = "CharacterHealed"
    CHARACTER_DIED = "CharacterDied"
    CHARACTER_REVIVED = "CharacterRevived"
    
    # ===== БОЙ =====
    COMBAT_STARTED = "CombatStarted"
    COMBAT_FINISHED = "CombatFinished"
    INITIATIVE_CALCULATED = "InitiativeCalculated"
    TURN_STARTED = "TurnStarted"
    TURN_ENDED = "TurnEnded"
    ROUND_STARTED = "RoundStarted"
    ROUND_ENDED = "RoundEnded"
    PARTICIPANT_ADDED = "ParticipantAdded"
    PARTICIPANT_REMOVED = "ParticipantRemoved"
    
    # ===== КУБИКИ =====
    ROLL_REQUESTED = "RollRequested"
    ROLL_STARTED = "RollStarted"
    ROLL_FINISHED = "RollFinished"
    DICE_ANIMATION = "DiceAnimation"
    
    # ===== СПОСОБНОСТИ =====
    SKILL_ACTIVATED = "SkillActivated"
    SKILL_RESOLVED = "SkillResolved"
    SKILL_FAILED = "SkillFailed"
    COOLDOWN_STARTED = "CooldownStarted"
    COOLDOWN_FINISHED = "CooldownFinished"
    SKILL_UPGRADED = "SkillUpgraded"
    
    # ===== ЭФФЕКТЫ =====
    EFFECT_APPLIED = "EffectApplied"
    EFFECT_REMOVED = "EffectRemoved"
    EFFECT_UPDATED = "EffectUpdated"
    EFFECT_EXPIRED = "EffectExpired"
    EFFECT_STACKED = "EffectStacked"
    
    # ===== ИНВЕНТАРЬ =====
    ITEM_ADDED = "ItemAdded"
    ITEM_REMOVED = "ItemRemoved"
    ITEM_EQUIPPED = "ItemEquipped"
    ITEM_UNEQUIPPED = "ItemUnequipped"
    ITEM_USED = "ItemUsed"
    ITEM_DROPPED = "ItemDropped"
    ITEM_PICKED = "ItemPicked"
    ITEM_TRADED = "ItemTraded"
    
    # ===== ПРОВЕРКИ =====
    CHECK_STARTED = "CheckStarted"
    CHECK_SUCCEEDED = "CheckSucceeded"
    CHECK_FAILED = "CheckFailed"
    CHECK_CRITICAL = "CheckCritical"
    
    # ===== ПЕРЕДВИЖЕНИЕ =====
    DOOR_OPENED = "DoorOpened"
    DOOR_CLOSED = "DoorClosed"
    DOOR_LOCKED = "DoorLocked"
    DOOR_UNLOCKED = "DoorUnlocked"
    OBJECT_ACTIVATED = "ObjectActivated"
    OBJECT_DEACTIVATED = "ObjectDeactivated"
    ZONE_ENTERED = "ZoneEntered"
    ZONE_EXITED = "ZoneExited"
    
    # ===== ДИАЛОГ =====
    DIALOG_STARTED = "DialogStarted"
    DIALOG_ENDED = "DialogEnded"
    DIALOG_NODE = "DialogNode"
    DIALOG_CHOICE = "DialogChoice"
    
    # ===== СИСТЕМНЫЕ =====
    SYSTEM_ERROR = "SystemError"
    SYSTEM_WARNING = "SystemWarning"
    SYSTEM_INFO = "SystemInfo"
    SYSTEM_SAVE = "SystemSave"
    SYSTEM_LOAD = "SystemLoad"

# ============================================================
# 20.4. EVENT FACTORIES
# ============================================================

class EventFactory:
    """Фабрика для создания событий."""
    
    @staticmethod
    def create_event(
        event_type: str,
        room_id: int,
        source: str,
        target: str = "",
        data: Dict[str, Any] = None,
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: str = None
    ) -> GameEvent:
        """Создает событие."""
        return GameEvent(
            type=event_type,
            room_id=room_id,
            source=source,
            target=target,
            data=data or {},
            priority=priority,
            correlation_id=correlation_id or str(uuid.uuid4())
        )
    
    # ===== КОМНАТА =====
    
    @staticmethod
    def room_created(room_id: int, creator_id: str, data: dict) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.ROOM_CREATED,
            room_id,
            creator_id,
            "",
            data
        )
    
    @staticmethod
    def player_joined(room_id: int, player_id: str, player_name: str) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.PLAYER_JOINED,
            room_id,
            player_id,
            "",
            {'player_name': player_name}
        )
    
    @staticmethod
    def player_left(room_id: int, player_id: str, player_name: str) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.PLAYER_LEFT,
            room_id,
            player_id,
            "",
            {'player_name': player_name}
        )
    
    # ===== БОЙ =====
    
    @staticmethod
    def combat_started(room_id: int, initiator: str, participants: List[str]) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.COMBAT_STARTED,
            room_id,
            initiator,
            "",
            {'participants': participants},
            priority=EventPriority.HIGH
        )
    
    @staticmethod
    def turn_started(room_id: int, character_id: str, turn_number: int) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.TURN_STARTED,
            room_id,
            character_id,
            "",
            {'turn_number': turn_number},
            priority=EventPriority.HIGH
        )
    
    # ===== ПЕРСОНАЖИ =====
    
    @staticmethod
    def character_damaged(
        room_id: int,
        target_id: str,
        source_id: str,
        damage: int,
        damage_type: str
    ) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.CHARACTER_DAMAGED,
            room_id,
            source_id,
            target_id,
            {
                'damage': damage,
                'damage_type': damage_type
            },
            priority=EventPriority.HIGH
        )
    
    @staticmethod
    def character_moved(
        room_id: int,
        character_id: str,
        from_position: tuple,
        to_position: tuple
    ) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.CHARACTER_MOVED,
            room_id,
            character_id,
            "",
            {
                'from_position': from_position,
                'to_position': to_position
            },
            priority=EventPriority.NORMAL
        )
    
    # ===== КУБИКИ =====
    
    @staticmethod
    def roll_finished(
        room_id: int,
        roller_id: str,
        dice_type: str,
        result: int,
        total: int,
        advantage: bool = False
    ) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.ROLL_FINISHED,
            room_id,
            roller_id,
            "",
            {
                'dice_type': dice_type,
                'result': result,
                'total': total,
                'advantage': advantage
            },
            priority=EventPriority.NORMAL
        )
    
    # ===== ЭФФЕКТЫ =====
    
    @staticmethod
    def effect_applied(
        room_id: int,
        caster_id: str,
        target_id: str,
        effect_name: str,
        duration: int
    ) -> GameEvent:
        return EventFactory.create_event(
            EventTypes.EFFECT_APPLIED,
            room_id,
            caster_id,
            target_id,
            {
                'effect_name': effect_name,
                'duration': duration
            },
            priority=EventPriority.NORMAL
        )

# ============================================================
# 20.5. EVENT MANAGER
# ============================================================

class EventManager:
    """
    Управление событиями на уровне приложения.
    Центральная точка доступа к Event Bus.
    """
    
    def __init__(self):
        self._buses: Dict[str, EventBus] = {}
        self._default_bus_name = "default"
        self._event_factory = EventFactory()
        self._logger = logging.getLogger("event_manager")
    
    def create_bus(self, name: str) -> EventBus:
        """Создает новую шину событий."""
        if name in self._buses:
            raise ValueError(f"Bus {name} already exists")
        bus = EventBus(name)
        self._buses[name] = bus
        return bus
    
    def get_bus(self, name: str = None) -> EventBus:
        """Получает шину событий."""
        bus_name = name or self._default_bus_name
        if bus_name not in self._buses:
            self._buses[bus_name] = EventBus(bus_name)
        return self._buses[bus_name]
    
    def set_default_bus(self, name: str) -> None:
        """Устанавливает шину по умолчанию."""
        if name in self._buses:
            self._default_bus_name = name
    
    async def start_all(self) -> None:
        """Запускает все шины."""
        for bus in self._buses.values():
            await bus.start()
        self._logger.info("All event buses started")
    
    async def stop_all(self) -> None:
        """Останавливает все шины."""
        for bus in self._buses.values():
            await bus.stop()
        self._logger.info("All event buses stopped")
    
    def get_factory(self) -> EventFactory:
        """Возвращает фабрику событий."""
        return self._event_factory
    
    # ===== УТИЛИТЫ =====
    
    def get_status(self) -> dict:
        """Возвращает статус всех шин."""
        return {
            'total_buses': len(self._buses),
            'buses': {name: bus.get_status() for name, bus in self._buses.items()}
        }
    
    def get_history(
        self,
        bus_name: str = None,
        event_type: str = None,
        room_id: int = None,
        limit: int = 100
    ) -> List[GameEvent]:
        """Получает историю событий из шины."""
        bus = self.get_bus(bus_name)
        return bus.get_history(event_type, room_id, limit)

# ============================================================
# 20.6. EVENT DECORATORS
# ============================================================

def handle_event(event_type: str, priority: EventPriority = EventPriority.NORMAL):
    """
    Декоратор для автоматической подписки на событие.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper._event_subscription = {
            'type': event_type,
            'priority': priority
        }
        return wrapper
    return decorator

def event_listener(bus_name: str = None):
    """
    Декоратор для регистрации класса как слушателя событий.
    """
    def decorator(cls):
        original_init = cls.__init__
        
        @functools.wraps(original_init)
        def new_init(self, *args, **kwargs):
            # Вызываем оригинальный __init__
            original_init(self, *args, **kwargs)
            
            # Находим все методы с подписками
            for attr_name in dir(self):
                method = getattr(self, attr_name)
                if hasattr(method, '_event_subscription'):
                    subscription = method._event_subscription
                    event_type = subscription['type']
                    priority = subscription['priority']
                    
                    # Получаем шину
                    event_manager = kwargs.get('event_manager')
                    if event_manager is None:
                        # Пытаемся найти в глобальном контексте
                        import sys
                        for frame in sys._current_frames().values():
                            if 'event_manager' in frame.f_locals:
                                event_manager = frame.f_locals['event_manager']
                                break
                    
                    if event_manager:
                        bus = event_manager.get_bus(bus_name)
                        bus.subscribe(event_type, method, priority)
        
        cls.__init__ = new_init
        return cls
    return decorator

# ============================================================
# 20.7. EVENT LOGGER
# ============================================================

class EventLogger:
    """Логирует события в базу данных."""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._logger = logging.getLogger("event_logger")
        self._enabled = True
    
    def enable(self) -> None:
        """Включает логирование."""
        self._enabled = True
    
    def disable(self) -> None:
        """Выключает логирование."""
        self._enabled = False
    
    async def log_event(self, event: GameEvent) -> None:
        """
        Логирует событие в БД.
        """
        if not self._enabled:
            return
        
        try:
            # Импортируем модели здесь, чтобы избежать циклических импортов
            from sqlalchemy import Table, Column, Integer, String, DateTime, JSON, Text
            from sqlalchemy import MetaData
            
            # Создаем таблицу для логов
            metadata = MetaData()
            event_log = Table(
                'event_logs',
                metadata,
                Column('id', Integer, primary_key=True),
                Column('event_id', String(36), nullable=False),
                Column('type', String(50), nullable=False),
                Column('room_id', Integer, nullable=False),
                Column('source', String(100)),
                Column('target', String(100)),
                Column('data', JSON),
                Column('timestamp', DateTime),
                Column('priority', String(20)),
                Column('status', String(20)),
                Column('retry_count', Integer)
            )
            
            # Создаем таблицу, если её нет
            from sqlalchemy import create_engine
            engine = create_engine('sqlite:///dnd_game.db')
            metadata.create_all(engine)
            
            # Вставляем запись
            session = self.session_factory()
            session.execute(
                event_log.insert().values(
                    event_id=event.event_id,
                    type=event.type,
                    room_id=event.room_id,
                    source=event.source,
                    target=event.target,
                    data=event.data,
                    timestamp=event.timestamp,
                    priority=event.priority.name,
                    status=event.status.value,
                    retry_count=event.retry_count
                )
            )
            session.commit()
            session.close()
            
        except Exception as e:
            self._logger.error(f"Failed to log event: {e}")

# ============================================================
# 20.8. EVENT REPLAY
# ============================================================

class EventReplay:
    """Воспроизведение событий."""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._logger = logging.getLogger("event_replay")
    
    async def replay_events(self, events: List[GameEvent], speed_multiplier: float = 1.0) -> None:
        """
        Воспроизводит последовательность событий.
        
        Args:
            events: Список событий для воспроизведения
            speed_multiplier: Множитель скорости (1.0 = реальное время)
        """
        if not events:
            return
        
        # Сортируем по времени
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        
        # Вычисляем задержки
        delays = []
        prev_time = sorted_events[0].timestamp
        for event in sorted_events[1:]:
            delay = (event.timestamp - prev_time).total_seconds() / speed_multiplier
            delays.append(max(0, delay))
            prev_time = event.timestamp
        
        # Воспроизводим
        for i, event in enumerate(sorted_events):
            await self.event_bus.publish(event)
            
            if i < len(delays):
                await asyncio.sleep(delays[i])
        
        self._logger.info(f"Replayed {len(events)} events")
    
    async def replay_from_history(
        self,
        room_id: int,
        limit: int = 100,
        speed_multiplier: float = 1.0
    ) -> None:
        """
        Воспроизводит события из истории.
        """
        events = self.event_bus.get_history(room_id=room_id, limit=limit)
        await self.replay_events(events, speed_multiplier)

# ============================================================
# 20.9. EVENT METRICS
# ============================================================

class EventMetrics:
    """Сбор метрик событий."""
    
    def __init__(self):
        self._counts: Dict[str, int] = defaultdict(int)
        self._errors: Dict[str, int] = defaultdict(int)
        self._processing_time: Dict[str, List[float]] = defaultdict(list)
        self._start_time: Optional[datetime] = None
        self._logger = logging.getLogger("event_metrics")
    
    def record_event(self, event: GameEvent) -> None:
        """Записывает событие."""
        self._counts[event.type] += 1
    
    def record_error(self, event_type: str) -> None:
        """Записывает ошибку."""
        self._errors[event_type] += 1
    
    def record_processing_time(self, event_type: str, duration: float) -> None:
        """Записывает время обработки."""
        self._processing_time[event_type].append(duration)
        
        # Ограничиваем размер списка
        if len(self._processing_time[event_type]) > 1000:
            self._processing_time[event_type] = self._processing_time[event_type][-1000:]
    
    def get_metrics(self) -> dict:
        """Возвращает метрики."""
        metrics = {
            'total_events': sum(self._counts.values()),
            'total_errors': sum(self._errors.values()),
            'event_counts': dict(self._counts),
            'error_counts': dict(self._errors),
            'avg_processing_times': {}
        }
        
        for event_type, times in self._processing_time.items():
            if times:
                metrics['avg_processing_times'][event_type] = sum(times) / len(times)
        
        return metrics
    
    def reset(self) -> None:
        """Сбрасывает метрики."""
        self._counts.clear()
        self._errors.clear()
        self._processing_time.clear()
        self._logger.info("Metrics reset")

# ============================================================
# 20.10. ГЛОБАЛЬНЫЙ ИНСТАНС
# ============================================================

# Создаем глобальный экземпляр Event Manager
event_manager = EventManager()

# Создаем шину по умолчанию
default_bus = event_manager.create_bus("default")

# Создаем Event Logger
from sqlalchemy.orm import sessionmaker
event_logger = EventLogger(sessionmaker(bind=engine))

# Создаем Event Metrics
event_metrics = EventMetrics()

# Подключаем логгер к шине
@handle_event("*")
async def log_event_handler(event: GameEvent):
    """Обработчик для логирования всех событий."""
    await event_logger.log_event(event)
    event_metrics.record_event(event)

default_bus.subscribe("*", log_event_handler)

# ============================================================
# 20.11. ТЕСТЫ
# ============================================================

async def test_event_system():
    """
    Тестирование Event System.
    """
    print("\n" + "="*60)
    print("🧪 ТЕСТИРОВАНИЕ EVENT SYSTEM")
    print("="*60)
    
    # Создаем тестовую шину
    test_bus = EventBus("test")
    await test_bus.start()
    
    # Создаем обработчики
    events_received = []
    
    @handle_event("TestEvent")
    async def test_handler(event: GameEvent):
        events_received.append(event)
        print(f"✅ Получено событие: {event.type} от {event.source}")
        return True
    
    test_bus.subscribe("TestEvent", test_handler)
    test_bus.subscribe("AnotherEvent", test_handler)
    
    # Создаем события
    event1 = EventFactory.create_event(
        "TestEvent",
        1,
        "test_source",
        "test_target",
        {"message": "Hello World!"}
    )
    
    event2 = EventFactory.create_event(
        "AnotherEvent",
        1,
        "test_source2",
        "",
        {"value": 42}
    )
    
    # Публикуем
    print("\n📤 Публикация событий...")
    await test_bus.publish(event1)
    await test_bus.publish(event2)
    
    # Ждем обработки
    await asyncio.sleep(0.5)
    
    # Проверяем
    print(f"\n📊 Получено событий: {len(events_received)}")
    assert len(events_received) == 2
    
    # Проверяем историю
    history = test_bus.get_history()
    print(f"📚 История: {len(history)} событий")
    
    # Проверяем статус
    status = test_bus.get_status()
    print(f"📈 Статус шины: {json.dumps(status, indent=2, default=str)}")
    
    # Тестируем с приоритетами
    print("\n🔄 Тестирование приоритетов...")
    order = []
    
    async def handler1(event):
        order.append(1)
    
    async def handler2(event):
        order.append(2)
    
    async def handler3(event):
        order.append(3)
    
    test_bus.subscribe("PriorityTest", handler3, EventPriority.LOW)
    test_bus.subscribe("PriorityTest", handler1, EventPriority.HIGH)
    test_bus.subscribe("PriorityTest", handler2, EventPriority.NORMAL)
    
    priority_event = EventFactory.create_event(
        "PriorityTest",
        1,
        "test",
        "",
        {}
    )
    
    await test_bus.publish(priority_event)
    await asyncio.sleep(0.1)
    
    print(f"📋 Порядок обработки: {order}")
    # Ожидаем: [1, 2, 3] (HIGH, NORMAL, LOW)
    
    # Останавливаем шину
    await test_bus.stop()
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# 20.12. ИНТЕГРАЦИЯ В ОСНОВНОЕ ПРИЛОЖЕНИЕ
# ============================================================

# Добавляем в FastAPI приложение
@app.on_event("startup")
async def startup_event():
    """Запускает Event System при старте приложения."""
    await default_bus.start()
    print("✅ Event System запущена")
    
    # Регистрируем базовые обработчики
    @default_bus.subscribe(EventTypes.ROOM_CREATED)
    async def on_room_created(event: GameEvent):
        print(f"🏠 Комната создана: {event.data}")
    
    @default_bus.subscribe(EventTypes.PLAYER_JOINED)
    async def on_player_joined(event: GameEvent):
        print(f"👤 Игрок присоединился: {event.data.get('player_name')}")
    
    @default_bus.subscribe(EventTypes.COMBAT_STARTED)
    async def on_combat_started(event: GameEvent):
        print(f"⚔️ Бой начался! Участников: {len(event.data.get('participants', []))}")
    
    print("✅ Обработчики событий зарегистрированы")

@app.on_event("shutdown")
async def shutdown_event():
    """Останавливает Event System при завершении приложения."""
    await default_bus.stop()
    print("✅ Event System остановлена")

# ============================================================
# 20.13. API ДЛЯ РАБОТЫ С СОБЫТИЯМИ
# ============================================================

@app.get("/api/events/status")
async def get_event_status(request: Request):
    """Получает статус Event System."""
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return {"success": False, "message": "Только GM может просматривать статус событий"}
    
    return {
        'success': True,
        'status': event_manager.get_status()
    }

@app.get("/api/events/history/{room_id}")
async def get_event_history(
    request: Request,
    room_id: int,
    event_type: Optional[str] = None,
    limit: int = 100
):
    """Получает историю событий комнаты."""
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    
    session = Session()
    room = session.query(GameRoom).filter_by(id=room_id).first()
    if not room:
        session.close()
        return {"success": False, "message": "Комната не найдена"}
    
    if room.gm_id != user.id:
        session.close()
        return {"success": False, "message": "Только GM может просматривать историю"}
    
    session.close()
    
    events = event_manager.get_history(room_id=room_id, event_type=event_type, limit=limit)
    
    return {
        'success': True,
        'events': [event.to_dict() for event in events],
        'count': len(events)
    }

@app.post("/api/events/publish")
async def publish_event(request: Request, data: dict):
    """Публикует событие (для отладки)."""
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return {"success": False, "message": "Только GM может публиковать события"}
    
    event_type = data.get('type')
    room_id = data.get('room_id')
    source = data.get('source', 'system')
    event_data = data.get('data', {})
    
    if not event_type or not room_id:
        return {"success": False, "message": "Не указаны type или room_id"}
    
    event = EventFactory.create_event(
        event_type,
        room_id,
        source,
        "",
        event_data
    )
    
    await default_bus.publish(event)
    
    return {
        'success': True,
        'event_id': event.event_id
    }

# ============================================================
# 20.14. ЗАПУСК ТЕСТОВ
# ============================================================

if __name__ == "__main__":
    # Запускаем тесты
    asyncio.run(test_event_system())
    
    # Запускаем основное приложение
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
