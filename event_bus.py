Universal Event Bus - Fully independent event system.
Knows nothing about characters, rooms, combat, skills, effects, inventory.
Only knows: event happened → subscribers get notified.
"""

import asyncio
import uuid
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set, Union, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque

# ============================================================
# ============================================================

class EventType(str, Enum):
    """Standard event types."""
    ROOM_CREATED = "room_created"
    ROOM_STARTED = "room_started"
    ROOM_PAUSED = "room_paused"
    ROOM_CLOSED = "room_closed"
    
    # Player events
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_READY = "player_ready"
    # Character events
    CHARACTER_CHANGED = "character_changed"
    CHARACTER_CREATED = "character_created"
    
    # Scene events
    SCENE_CHANGED = "scene_changed"
    SCENE_LOADED = "scene_loaded"
    # Action events
    ACTION_FINISHED = "action_finished"
    ACTION_FAILED = "action_failed"
    # Check events
    CHECK_FINISHED = "check_finished"
    CHECK_SUCCESS = "check_success"
    
    # Combat events
    COMBAT_STARTED = "combat_started"
    COMBAT_ENDED = "combat_ended"
    TURN_FINISHED = "turn_finished"
    ROUND_ENDED = "round_ended"
    
    # Dice events
    DICE_ANIMATION = "dice_animation"
    
    # Skill events
    SKILL_USED = "skill_used"
    SKILL_COOLDOWN = "skill_cooldown"
    
    # Item events
    ITEM_ADDED = "item_added"
    
    # NPC events
    NPC_REMOVED = "npc_removed"
    
    # Effect events
    EFFECT_ADDED = "effect_added"
    EFFECT_REMOVED = "effect_removed"
    
    # Map events
    MAP_CHANGED = "map_changed"
    MAP_LOADED = "map_loaded"
    TOKEN_CHANGED = "token_changed"
    
    # Chat events
    CHAT_MESSAGE = "chat_message"
    
    # System events
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_INFO = "system_info"
    
    # Save events
    SAVE_CREATED = "save_created"
    SAVE_LOADED = "save_loaded"
    SAVE_DELETED = "save_deleted"
    # Custom events (for user-defined events)
    CUSTOM = "custom"

# ============================================================
# ============================================================
class EventPriority(int, Enum):
    """Event priority levels."""
    NORMAL = 1
    LOW = 2

@dataclass
    """Universal event container."""
    event_type: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    target: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'target': self.target,
            'payload': self.payload,
            'priority': self.priority.value if hasattr(self.priority, 'value') else self.priority,
        }
    
    def from_dict(cls, data: dict) -> 'Event':
            id=data.get('id', str(uuid.uuid4())),
            event_type=data.get('event_type', ''),
            source=data.get('source', ''),
            payload=data.get('payload', {}),
            metadata=data.get('metadata', {}),
            is_sticky=data.get('is_sticky', False)
        )

# ============================================================
# ============================================================
class EventBus:
    """
    Universal Event Bus - Independent event system.
    Knows nothing about game mechanics.
    
    def __init__(self, name: str = "default", max_history: int = 1000):
        self.max_history = max_history
        # Subscribers: event_type -> list of (callback, filter_func, priority)
        self._subscribers: Dict[str, List[Tuple[Callable, Optional[Callable], int]]] = defaultdict(list)
        # Sticky events: event_type -> latest event
        
        # Event history
        
        # Event queue for async processing
        self._is_processing: bool = False
        self._processing_task: Optional[asyncio.Task] = None
        # Middleware
        
        # Statistics
            'total_events': 0,
            'total_subscribers': 0,
            'queue_size': 0
        
        # Logger
        self._logger = logging.getLogger(f"event_bus.{name}")
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    # ===== SUBSCRIPTION =====
    
        self,
        event_type: str,
        callback: Callable[[Event], Any],
        filter_func: Optional[Callable[[Event], bool]] = None,
    ) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to (use "*" for all events)
            callback: Function to call when event is published
            filter_func: Optional filter function (returns True to receive event)
        """
        # Sort by priority
        self._subscribers[event_type].sort(key=lambda x: x[2])
        self._logger.debug(f"Subscribed to {event_type}")
    
    def subscribe_all(
        self,
        filter_func: Optional[Callable[[Event], bool]] = None,
    ) -> None:
        """Subscribe to all events."""
    
    def unsubscribe(
        self,
        event_type: str,
    ) -> bool:
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            original_len = len(self._subscribers[event_type])
                (cb, flt, pri) for cb, flt, pri in self._subscribers[event_type]
            ]
            if len(self._subscribers[event_type]) < original_len:
                self._logger.debug(f"Unsubscribed from {event_type}")
        return False
    
    def unsubscribe_all(self, callback: Callable[[Event], Any]) -> int:
        """Unsubscribe from all events."""
        for event_type in list(self._subscribers.keys()):
            if self.unsubscribe(event_type, callback):
        return count
    
    def clear(self) -> None:
        """Clear all subscribers."""
        self._subscribers.clear()
        self._stats['total_subscribers'] = 0
        self._logger.info("All subscribers cleared")
    
    # ===== PUBLISHING =====
    
    def publish(self, event: Event) -> None:
        """
        Publish an event synchronously.
        # Apply middleware
        for middleware in self._middleware:
            try:
                event = middleware(event)
                    return
                self._logger.error(f"Middleware error: {e}")
                return
        # Store sticky event
            self._sticky_events[event.event_type] = event
        
        # Add to history
        self._add_to_history(event)
        # Update stats
        self._stats['total_events'] += 1
        
        # Find subscribers
        callbacks = []
        
        # Specific event type
        if event.event_type in self._subscribers:
        
        # All events
            callbacks.extend(self._subscribers["*"])
        # Execute callbacks
            try:
                # Apply filter if exists
                    continue
                
                # Execute callback
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(event))
                else:
                    
                self._logger.error(f"Callback error: {e}")
    
    async def publish_async(self, event: Event) -> None:
        """
        """
        # Apply middleware
            try:
                if asyncio.iscoroutinefunction(middleware):
                    event = await middleware(event)
                else:
                if event is None:
            except Exception as e:
                self._logger.error(f"Middleware error: {e}")
        
        # Store sticky event
        if event.is_sticky:
            self._sticky_events[event.event_type] = event
        # Add to queue
        await self._queue.put(event)
        
        # Start processing if not running
        if not self._is_processing:
            self._is_processing = True
            self._processing_task = asyncio.create_task(self._process_queue())
    
    async def _process_queue(self) -> None:
        """Process events from queue."""
            try:
                event = await self._queue.get()
                
                # Add to history
                self._add_to_history(event)
                
                # Update stats
                self._stats['total_events'] += 1
                self._stats['queue_size'] = self._queue.qsize()
                
                # Find subscribers
                callbacks = []
                    callbacks.extend(self._subscribers[event.event_type])
                if "*" in self._subscribers:
                    callbacks.extend(self._subscribers["*"])
                
                for callback, filter_func, priority in callbacks:
                    try:
                            continue
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event)
                        else:
                            callback(event)
                    except Exception as e:
                        self._logger.error(f"Callback error: {e}")
                self._queue.task_done()
            except asyncio.CancelledError:
                break
                self._logger.error(f"Queue processing error: {e}")
        self._is_processing = False
    
    def _add_to_history(self, event: Event) -> None:
        """Add event to history with size limit."""
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
    
    # ===== STICKY EVENTS =====
    
    def get_sticky(self, event_type: str) -> Optional[Event]:
        """Get the latest sticky event of a type."""
    
    def get_sticky_all(self) -> Dict[str, Event]:
        """Get all sticky events."""
        return dict(self._sticky_events)
    def clear_sticky(self) -> None:
        """Clear all sticky events."""
    
    
    def add_middleware(self, middleware: Callable) -> None:
        """Add middleware that processes events before publishing."""
        self._middleware.append(middleware)
    def remove_middleware(self, middleware: Callable) -> None:
        """Remove middleware."""
            self._middleware.remove(middleware)
    def clear_middleware(self) -> None:
        """Clear all middleware."""
    
    # ===== HISTORY =====
    
    def get_history(
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        events = self._history[-limit:] if limit > 0 else self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
            events = [e for e in events if e.source == source]
        return events
    
    def clear_history(self) -> None:
        """Clear event history."""
    
    # ===== STATISTICS =====
    def get_statistics(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'total_events': self._stats['total_events'],
            'events_by_type': dict(self._stats['events_by_type']),
            'queue_size': self._queue.qsize(),
            'history_size': len(self._history),
            'middleware_count': len(self._middleware)
    
    def get_subscribers(self) -> Dict[str, int]:
        """Get subscriber counts by event type."""
        return {k: len(v) for k, v in self._subscribers.items()}
    def listener_count(self, event_type: Optional[str] = None) -> int:
        """Get number of listeners for an event type."""
            return len(self._subscribers.get(event_type, []))
    
    # ===== SHUTDOWN =====
    
    async def shutdown(self) -> None:
        self._is_processing = False
        if self._processing_task:
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        self._logger.info("Event bus shutdown complete")
# ============================================================
# 26.4. EVENT BUS FACTORY

class EventBusFactory:
    """Factory for creating and managing event buses."""
    
    def __init__(self):
        self._buses: Dict[str, EventBus] = {}
    
    def create_bus(self, name: str, max_history: int = 1000) -> EventBus:
        if name in self._buses:
        bus = EventBus(name, max_history)
        self._buses[name] = bus
    
    def get_bus(self, name: Optional[str] = None) -> EventBus:
        """Get an event bus by name (creates default if not exists)."""
        bus_name = name or self._default_bus_name
            self._buses[bus_name] = EventBus(bus_name)
    
    def remove_bus(self, name: str) -> bool:
        """Remove an event bus."""
        if name in self._buses:
            return True
        return False
    def get_all_buses(self) -> Dict[str, EventBus]:
        return dict(self._buses)

# ============================================================
# 26.5. DECORATORS

def event_listener(event_type: str, filter_func: Optional[Callable] = None):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)
        
        # Store subscription info
            'event_type': event_type,
            'filter_func': filter_func
        return wrapper

# ============================================================
# 26.6. TESTS
# ============================================================
async def test_event_bus():
    """Test the event bus."""
    print("🧪 ТЕСТИРОВАНИЕ EVENT BUS")
    
    # Create bus
    bus = EventBus("test", max_history=10)
    
    # Test 1: Basic subscription and publishing
    print("\n📋 Тест 1: Подписка и публикация")
    
    received_events = []
    
    def on_test_event(event: Event):
        received_events.append(event)
        print(f"   Получено: {event.event_type} от {event.source}")
    bus.subscribe("test_event", on_test_event)
    event1 = Event(event_type="test_event", source="test_source", payload={"data": "Hello"})
    bus.publish(event1)
    print(f"   Получено событий: {len(received_events)}")
    
    # Test 2: Multiple subscribers
    
    received_count = 0
    
    def subscriber1(event: Event):
        received_count += 1
    
    def subscriber2(event: Event):
        nonlocal received_count
    
    bus.subscribe("multi_event", subscriber1)
    bus.subscribe("multi_event", subscriber2)
    event2 = Event(event_type="multi_event")
    
    print(f"   Получено подписчиками: {received_count}")
    assert received_count == 2
    
    print("\n📋 Тест 3: Отписка")
    
    def unsubscribe_test(event: Event):
        pass
    
    bus.subscribe("unsubscribe_test", unsubscribe_test)
    before = bus.listener_count("unsubscribe_test")
    bus.unsubscribe("unsubscribe_test", unsubscribe_test)
    after = bus.listener_count("unsubscribe_test")
    print(f"   До отписки: {before}, После: {after}")
    assert after == 0
    # Test 4: Event history
    
    for i in range(5):
    
    print(f"   Последние 3 события: {len(history)}")
    assert len(history) == 3
    # Test 5: Sticky events
    
    sticky_event = Event(event_type="sticky_test", is_sticky=True, payload={"status": "ready"})
    
    sticky = bus.get_sticky("sticky_test")
    print(f"   Sticky событие: {sticky is not None}")
    assert sticky is not None
    
    # Test 6: Async publishing
    print("\n📋 Тест 6: Асинхронная публикация")
    
    async_events = []
    
        async_events.append(event)
        print(f"   Async получено: {event.event_type}")
    bus.subscribe("async_test", async_handler)
    await bus.publish_async(Event(event_type="async_test"))
    await asyncio.sleep(0.1)  # Wait for async processing
    print(f"   Async событий получено: {len(async_events)}")
    assert len(async_events) == 1
    
    # Test 7: Priority
    print("\n📋 Тест 7: Приоритеты")
    execution_order = []
    
    def high_priority(event: Event):
        execution_order.append("HIGH")
    def normal_priority(event: Event):
        execution_order.append("NORMAL")
    def low_priority(event: Event):
    
    bus.subscribe("priority_test", high_priority, priority=EventPriority.HIGH)
    bus.subscribe("priority_test", normal_priority, priority=EventPriority.NORMAL)
    bus.subscribe("priority_test", low_priority, priority=EventPriority.LOW)
    bus.publish(Event(event_type="priority_test"))
    print(f"   Порядок выполнения: {execution_order}")
    
    # Test 8: Filter
    print("\n📋 Тест 8: Фильтрация")
    
    filtered_events = []
    
    def only_source_a(event: Event) -> bool:
        return event.source == "A"
    
    def filter_handler(event: Event):
        filtered_events.append(event)
    bus.subscribe("filter_test", filter_handler, filter_func=only_source_a)
    
    bus.publish(Event(event_type="filter_test", source="A"))
    bus.publish(Event(event_type="filter_test", source="B"))
    print(f"   Отфильтровано событий: {len(filtered_events)}")
    assert len(filtered_events) == 1
    # Test 9: Middleware
    
    def add_metadata(event: Event) -> Event:
        return event
    bus.add_middleware(add_metadata)
    
    middleware_event = Event(event_type="middleware_test")
    bus.publish(middleware_event)
    
    print(f"   Middleware добавил метаданные: {'processed_by' in middleware_event.metadata}")
    assert middleware_event.metadata.get('processed_by') == 'middleware'
    
    print("\n📋 Тест 10: Статистика")
    
    stats = bus.get_statistics()
    print(f"   Всего событий: {stats['total_events']}")
    print(f"   В истории: {stats['history_size']}")
    
    # Cleanup
    await bus.shutdown()
    print("\n✅ Все тесты пройдены!")
    print("="*60)
# ============================================================
# ============================================================

event_bus_factory = EventBusFactory()
default_bus = event_bus_factory.get_bus()
# ============================================================
# 26.8. MAIN
# ============================================================

if __name__ == "__main__":
    asyncio.run(test_event_bus())
