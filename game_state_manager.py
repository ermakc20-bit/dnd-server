# ============================================================
# 23. GAME STATE MANAGER
# ============================================================

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import defaultdict
import functools

# ============================================================
# 23.1. БАЗОВЫЕ КЛАССЫ
# ============================================================

class GameState(str, Enum):
    """Глобальные состояния игровой комнаты."""
    LOBBY = "lobby"                       # Комната создана, ожидание игроков
    CHARACTER_SELECTION = "character_selection"  # Выбор персонажей
    LOADING_SCENARIO = "loading_scenario"        # Загрузка сценария
    EXPLORATION = "exploration"           # Основной игровой режим
    DIALOGUE = "dialogue"                 # Режим диалога
    SKILL_CHECK = "skill_check"           # Проверка навыков
    COMBAT = "combat"                     # Боевой режим
    CUTSCENE = "cutscene"                 # Кат-сцена
    PAUSED = "paused"                     # Пауза
    SCENARIO_COMPLETED = "scenario_completed"  # Сценарий завершён
    ROOM_CLOSED = "room_closed"           # Комната закрыта
    ERROR = "error"                       # Ошибка

class StateTransitionType(str, Enum):
    """Типы переходов между состояниями."""
    NORMAL = "normal"          # Обычный переход
    FORCED = "forced"          # Принудительный (GM)
    SYSTEM = "system"          # Системный (автоматический)
    ERROR = "error"            # Переход из-за ошибки
    ROLLBACK = "rollback"      # Откат к предыдущему

class StateChangePriority(str, Enum):
    """Приоритет запроса на смену состояния."""
    CRITICAL = "critical"      # Критический (системный)
    HIGH = "high"              # Высокий (GM)
    NORMAL = "normal"          # Обычный (игровой)
    LOW = "low"                # Низкий (фоновый)

@dataclass
class StateChangeRequest:
    """Запрос на смену состояния."""
    target_state: GameState
    source: str
    priority: StateChangePriority = StateChangePriority.NORMAL
    data: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    requires_validation: bool = True
    
    def to_dict(self) -> dict:
        return {
            'target_state': self.target_state.value,
            'source': self.source,
            'priority': self.priority.value,
            'data': self.data,
            'correlation_id': self.correlation_id,
            'timestamp': self.timestamp.isoformat(),
            'requires_validation': self.requires_validation
        }

@dataclass
class StateTransition:
    """Запись о переходе между состояниями."""
    from_state: GameState
    to_state: GameState
    transition_type: StateTransitionType
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    duration: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            'from_state': self.from_state.value,
            'to_state': self.to_state.value,
            'transition_type': self.transition_type.value,
            'source': self.source,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'duration': self.duration
        }

# ============================================================
# 23.2. STATE VALIDATOR
# ============================================================

class StateValidator:
    """
    Валидатор переходов между состояниями.
    Проверяет корректность переходов согласно правилам.
    """
    
    # Правила переходов: from_state -> [allowed_to_states]
    TRANSITION_RULES = {
        GameState.LOBBY: [
            GameState.CHARACTER_SELECTION,
            GameState.LOADING_SCENARIO,
            GameState.PAUSED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.CHARACTER_SELECTION: [
            GameState.LOADING_SCENARIO,
            GameState.PAUSED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.LOADING_SCENARIO: [
            GameState.EXPLORATION,
            GameState.PAUSED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.EXPLORATION: [
            GameState.DIALOGUE,
            GameState.SKILL_CHECK,
            GameState.COMBAT,
            GameState.CUTSCENE,
            GameState.PAUSED,
            GameState.SCENARIO_COMPLETED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.DIALOGUE: [
            GameState.EXPLORATION,
            GameState.SKILL_CHECK,
            GameState.COMBAT,
            GameState.CUTSCENE,
            GameState.PAUSED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.SKILL_CHECK: [
            GameState.EXPLORATION,
            GameState.DIALOGUE,
            GameState.COMBAT,
            GameState.PAUSED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.COMBAT: [
            GameState.EXPLORATION,
            GameState.DIALOGUE,
            GameState.CUTSCENE,
            GameState.PAUSED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.CUTSCENE: [
            GameState.EXPLORATION,
            GameState.DIALOGUE,
            GameState.COMBAT,
            GameState.PAUSED,
            GameState.SCENARIO_COMPLETED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.PAUSED: [
            GameState.LOBBY,
            GameState.CHARACTER_SELECTION,
            GameState.LOADING_SCENARIO,
            GameState.EXPLORATION,
            GameState.DIALOGUE,
            GameState.SKILL_CHECK,
            GameState.COMBAT,
            GameState.CUTSCENE,
            GameState.SCENARIO_COMPLETED,
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.SCENARIO_COMPLETED: [
            GameState.ROOM_CLOSED,
            GameState.ERROR
        ],
        GameState.ROOM_CLOSED: [],
        GameState.ERROR: [
            GameState.ROOM_CLOSED,
            GameState.PAUSED
        ]
    }
    
    # Состояния, в которых можно ставить на паузу
    PAUSABLE_STATES = [
        GameState.LOBBY,
        GameState.CHARACTER_SELECTION,
        GameState.LOADING_SCENARIO,
        GameState.EXPLORATION,
        GameState.DIALOGUE,
        GameState.SKILL_CHECK,
        GameState.COMBAT,
        GameState.CUTSCENE
    ]
    
    @classmethod
    def is_valid_transition(
        cls,
        from_state: GameState,
        to_state: GameState,
        force: bool = False
    ) -> bool:
        """
        Проверяет, допустим ли переход.
        """
        if force:
            return True
        
        if from_state == to_state:
            return True
        
        allowed = cls.TRANSITION_RULES.get(from_state, [])
        return to_state in allowed
    
    @classmethod
    def get_allowed_transitions(cls, from_state: GameState) -> List[GameState]:
        """
        Возвращает список допустимых состояний для перехода.
        """
        return cls.TRANSITION_RULES.get(from_state, [])
    
    @classmethod
    def can_pause(cls, current_state: GameState) -> bool:
        """
        Проверяет, можно ли поставить на паузу.
        """
        return current_state in cls.PAUSABLE_STATES
    
    @classmethod
    def is_terminal(cls, state: GameState) -> bool:
        """
        Проверяет, является ли состояние терминальным.
        """
        return state in [GameState.SCENARIO_COMPLETED, GameState.ROOM_CLOSED]

# ============================================================
# 23.3. GAME STATE MANAGER
# ============================================================

class GameStateManager:
    """
    Менеджер глобального состояния игры.
    Единственный источник истины о состоянии комнаты.
    """
    
    def __init__(self, room_id: int):
        self.room_id = room_id
        self.current_state: GameState = GameState.LOBBY
        self.previous_state: Optional[GameState] = None
        self.state_history: List[StateTransition] = []
        self._is_initialized = False
        self._pending_requests: List[StateChangeRequest] = []
        self._lock = asyncio.Lock()
        
        # Интеграция с другими системами
        self.event_bus = None
        self.scenario_engine = None
        self.combat_system = None
        self.ui_framework = None
        
        # События и подписки
        self._listeners: Dict[GameState, List[Callable]] = defaultdict(list)
        self._global_listeners: List[Callable] = []
        self._transition_listeners: List[Callable] = []
        
        # Метрики
        self._state_metrics: Dict[GameState, int] = defaultdict(int)
        self._transition_metrics: Dict[str, int] = defaultdict(int)
        self._last_state_change: Optional[datetime] = None
        self._state_durations: Dict[GameState, float] = defaultdict(float)
        
        # Логирование
        self._logger = logging.getLogger(f"game_state_manager.{room_id}")
        
        self._logger.info(f"Game State Manager initialized for room {room_id}")
    
    # ===== УПРАВЛЕНИЕ СОСТОЯНИЕМ =====
    
    async def initialize(self) -> bool:
        """
        Инициализирует менеджер.
        """
        if self._is_initialized:
            return True
        
        self._is_initialized = True
        self._logger.info("Game State Manager initialized")
        return True
    
    async def change_state(
        self,
        new_state: GameState,
        source: str,
        data: Optional[Dict[str, Any]] = None,
        priority: StateChangePriority = StateChangePriority.NORMAL,
        force: bool = False
    ) -> bool:
        """
        Изменяет глобальное состояние игры.
        """
        async with self._lock:
            # Проверяем валидность перехода
            if not StateValidator.is_valid_transition(self.current_state, new_state, force):
                self._logger.warning(
                    f"Invalid transition: {self.current_state.value} -> {new_state.value}"
                )
                return False
            
            # Сохраняем предыдущее состояние
            self.previous_state = self.current_state
            old_state = self.current_state
            
            # Запоминаем время
            if self._last_state_change:
                duration = (datetime.now() - self._last_state_change).total_seconds()
                self._state_durations[old_state] += duration
            
            # Меняем состояние
            self.current_state = new_state
            self._last_state_change = datetime.now()
            
            # Обновляем метрики
            self._state_metrics[new_state] += 1
            self._transition_metrics[f"{old_state.value}->{new_state.value}"] += 1
            
            # Создаём запись о переходе
            transition = StateTransition(
                from_state=old_state,
                to_state=new_state,
                transition_type=StateTransitionType.NORMAL if not force else StateTransitionType.FORCED,
                source=source,
                data=data or {},
                duration=duration if self._last_state_change else 0
            )
            self.state_history.append(transition)
            
            # Ограничиваем историю
            if len(self.state_history) > 1000:
                self.state_history = self.state_history[-1000:]
            
            self._logger.info(
                f"State changed: {old_state.value} -> {new_state.value} "
                f"(source: {source})"
            )
            
            # Публикуем событие
            await self._publish_state_change(old_state, new_state, transition)
            
            # Вызываем слушателей
            await self._notify_listeners(old_state, new_state, transition)
            
            return True
    
    async def request_change_state(
        self,
        request: StateChangeRequest
    ) -> bool:
        """
        Обрабатывает запрос на смену состояния.
        """
        # Проверяем приоритеты
        if request.priority == StateChangePriority.CRITICAL:
            # Критические запросы выполняются немедленно
            return await self.change_state(
                request.target_state,
                request.source,
                request.data,
                request.priority,
                force=True
            )
        
        # Обычные запросы проходят валидацию
        return await self.change_state(
            request.target_state,
            request.source,
            request.data,
            request.priority
        )
    
    async def rollback(self) -> bool:
        """
        Откатывает к предыдущему состоянию.
        """
        if not self.previous_state:
            return False
        
        old_state = self.current_state
        target_state = self.previous_state
        
        # Проверяем возможность отката
        if not StateValidator.is_valid_transition(old_state, target_state, force=True):
            return False
        
        self.previous_state = None
        return await self.change_state(
            target_state,
            "system_rollback",
            {'from_rollback': True},
            StateChangePriority.HIGH,
            force=True
        )
    
    # ===== ПРОВЕРКИ =====
    
    def is_state(self, state: GameState) -> bool:
        """Проверяет, находится ли комната в указанном состоянии."""
        return self.current_state == state
    
    def is_in_state(self, *states: GameState) -> bool:
        """Проверяет, находится ли комната в одном из состояний."""
        return self.current_state in states
    
    def can_transition_to(self, target_state: GameState) -> bool:
        """Проверяет, возможен ли переход в указанное состояние."""
        return StateValidator.is_valid_transition(self.current_state, target_state)
    
    def get_allowed_transitions(self) -> List[GameState]:
        """Возвращает список допустимых состояний для перехода."""
        return StateValidator.get_allowed_transitions(self.current_state)
    
    def can_pause(self) -> bool:
        """Проверяет, можно ли поставить на паузу."""
        return StateValidator.can_pause(self.current_state)
    
    def is_terminal(self) -> bool:
        """Проверяет, является ли состояние терминальным."""
        return StateValidator.is_terminal(self.current_state)
    
    # ===== УТИЛИТЫ =====
    
    async def pause(self, source: str = "gm") -> bool:
        """
        Ставит игру на паузу.
        """
        if not self.can_pause():
            return False
        
        if self.is_state(GameState.PAUSED):
            return True
        
        return await self.change_state(
            GameState.PAUSED,
            source,
            {'action': 'pause'},
            StateChangePriority.HIGH
        )
    
    async def resume(self, source: str = "gm") -> bool:
        """
        Возобновляет игру после паузы.
        """
        if not self.is_state(GameState.PAUSED):
            return False
        
        if not self.previous_state:
            # По умолчанию возвращаемся в Exploration
            return await self.change_state(
                GameState.EXPLORATION,
                source,
                {'action': 'resume'},
                StateChangePriority.HIGH
            )
        
        return await self.rollback()
    
    async def go_to_exploration(self, source: str = "system") -> bool:
        """
        Возвращает к исследованию.
        """
        if self.current_state == GameState.EXPLORATION:
            return True
        
        return await self.change_state(
            GameState.EXPLORATION,
            source,
            {'action': 'return_to_exploration'},
            StateChangePriority.NORMAL
        )
    
    # ===== СОБЫТИЯ =====
    
    def on_state(self, state: GameState, callback: Callable) -> None:
        """
        Подписывается на событие входа в состояние.
        """
        self._listeners[state].append(callback)
    
    def on_any_state(self, callback: Callable) -> None:
        """
        Подписывается на все изменения состояния.
        """
        self._global_listeners.append(callback)
    
    def on_transition(self, callback: Callable) -> None:
        """
        Подписывается на переходы между состояниями.
        """
        self._transition_listeners.append(callback)
    
    def off_state(self, state: GameState, callback: Callable) -> None:
        """
        Отписывается от события состояния.
        """
        if state in self._listeners and callback in self._listeners[state]:
            self._listeners[state].remove(callback)
    
    def off_any_state(self, callback: Callable) -> None:
        """
        Отписывается от всех событий.
        """
        if callback in self._global_listeners:
            self._global_listeners.remove(callback)
    
    async def _notify_listeners(
        self,
        old_state: GameState,
        new_state: GameState,
        transition: StateTransition
    ) -> None:
        """
        Уведомляет слушателей о смене состояния.
        """
        # Глобальные слушатели
        for listener in self._global_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(old_state, new_state, transition)
                else:
                    listener(old_state, new_state, transition)
            except Exception as e:
                self._logger.error(f"Global listener error: {e}")
        
        # Слушатели нового состояния
        for listener in self._listeners.get(new_state, []):
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(old_state, new_state, transition)
                else:
                    listener(old_state, new_state, transition)
            except Exception as e:
                self._logger.error(f"State listener error: {e}")
        
        # Слушатели переходов
        for listener in self._transition_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(transition)
                else:
                    listener(transition)
            except Exception as e:
                self._logger.error(f"Transition listener error: {e}")
    
    async def _publish_state_change(
        self,
        old_state: GameState,
        new_state: GameState,
        transition: StateTransition
    ) -> None:
        """
        Публикует событие через Event System.
        """
        if not self.event_bus:
            return
        
        try:
            from event_system import EventFactory, EventPriority
            event = EventFactory.create_event(
                "game_state_changed",
                self.room_id,
                "game_state_manager",
                "",
                {
                    'old_state': old_state.value,
                    'new_state': new_state.value,
                    'transition_type': transition.transition_type.value,
                    'source': transition.source,
                    'data': transition.data,
                    'duration': transition.duration
                },
                priority=EventPriority.HIGH
            )
            await self.event_bus.publish(event)
        except Exception as e:
            self._logger.error(f"Failed to publish state change event: {e}")
    
    # ===== МЕТРИКИ =====
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Возвращает метрики менеджера.
        """
        current_duration = 0
        if self._last_state_change:
            current_duration = (datetime.now() - self._last_state_change).total_seconds()
            current_duration += self._state_durations[self.current_state]
        
        return {
            'current_state': self.current_state.value,
            'previous_state': self.previous_state.value if self.previous_state else None,
            'total_transitions': len(self.state_history),
            'state_counts': {k.value: v for k, v in self._state_metrics.items()},
            'transition_counts': dict(self._transition_metrics),
            'state_durations': {k.value: v for k, v in self._state_durations.items()},
            'current_duration': current_duration,
            'last_change': self._last_state_change.isoformat() if self._last_state_change else None
        }
    
    # ===== ИСТОРИЯ =====
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Возвращает историю переходов.
        """
        return [
            t.to_dict()
            for t in self.state_history[-limit:]
        ]
    
    def get_history_by_state(self, state: GameState, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Возвращает историю переходов, связанных с состоянием.
        """
        result = []
        for t in reversed(self.state_history):
            if t.from_state == state or t.to_state == state:
                result.append(t.to_dict())
                if len(result) >= limit:
                    break
        return result
    
    def get_current_context(self) -> Dict[str, Any]:
        """
        Возвращает контекст текущего состояния.
        """
        return {
            'state': self.current_state.value,
            'can_pause': self.can_pause(),
            'is_terminal': self.is_terminal(),
            'allowed_transitions': [s.value for s in self.get_allowed_transitions()],
            'previous_state': self.previous_state.value if self.previous_state else None,
            'history_size': len(self.state_history)
        }
    
    # ===== СОСТОЯНИЕ =====
    
    def get_state(self) -> Dict[str, Any]:
        """
        Возвращает полное состояние менеджера.
        """
        return {
            'room_id': self.room_id,
            'current_state': self.current_state.value,
            'previous_state': self.previous_state.value if self.previous_state else None,
            'history': self.get_history(limit=10),
            'metrics': self.get_metrics(),
            'context': self.get_current_context(),
            'is_initialized': self._is_initialized,
            'pending_requests': [
                r.to_dict() for r in self._pending_requests[:10]
            ]
        }

# ============================================================
# 23.4. GAME STATE MANAGER FACTORY
# ============================================================

class GameStateManagerFactory:
    """
    Фабрика для создания менеджеров состояния.
    """
    
    def __init__(self):
        self._managers: Dict[int, GameStateManager] = {}
        self._logger = logging.getLogger("game_state_manager_factory")
    
    def get_manager(self, room_id: int) -> GameStateManager:
        """
        Получает менеджер для комнаты.
        """
        if room_id not in self._managers:
            manager = GameStateManager(room_id)
            self._managers[room_id] = manager
            self._logger.info(f"Created manager for room {room_id}")
        return self._managers[room_id]
    
    def remove_manager(self, room_id: int) -> bool:
        """
        Удаляет менеджер комнаты.
        """
        if room_id in self._managers:
            del self._managers[room_id]
            self._logger.info(f"Removed manager for room {room_id}")
            return True
        return False
    
    def get_all_managers(self) -> Dict[int, GameStateManager]:
        """
        Возвращает все менеджеры.
        """
        return self._managers
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Возвращает статистику по менеджерам.
        """
        stats = {
            'total_managers': len(self._managers),
            'states': defaultdict(int)
        }
        
        for manager in self._managers.values():
            stats['states'][manager.current_state.value] += 1
        
        return {
            'total_managers': len(self._managers),
            'state_distribution': dict(stats['states'])
        }

# ============================================================
# 23.5. DECORATORS
# ============================================================

def state_guard(*allowed_states: GameState):
    """
    Декоратор для защиты функций от вызова в неправильном состоянии.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Получаем менеджер из self
            manager = getattr(self, 'state_manager', None)
            if not manager:
                manager = getattr(self, 'game_state_manager', None)
            
            if not manager:
                raise RuntimeError("State manager not found")
            
            if not manager.is_in_state(*allowed_states):
                raise RuntimeError(
                    f"Cannot execute {func.__name__} in state {manager.current_state.value}. "
                    f"Allowed states: {[s.value for s in allowed_states]}"
                )
            
            return await func(self, *args, **kwargs)
        return wrapper
    return decorator

def state_transition(target_state: GameState, priority: StateChangePriority = StateChangePriority.NORMAL):
    """
    Декоратор для автоматического перехода в состояние после выполнения функции.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Получаем менеджер
            manager = getattr(self, 'state_manager', None)
            if not manager:
                manager = getattr(self, 'game_state_manager', None)
            
            if not manager:
                raise RuntimeError("State manager not found")
            
            # Выполняем функцию
            result = await func(self, *args, **kwargs)
            
            # Переходим в состояние
            await manager.change_state(
                target_state,
                f"decorator_{func.__name__}",
                {'function': func.__name__},
                priority
            )
            
            return result
        return wrapper
    return decorator

# ============================================================
# 23.6. ТЕСТЫ
# ============================================================

async def test_game_state_manager():
    """Тестирование Game State Manager."""
    print("\n" + "="*60)
    print("🧪 ТЕСТИРОВАНИЕ GAME STATE MANAGER")
    print("="*60)
    
    # Создаём менеджер
    manager = GameStateManager(room_id=1)
    
    print(f"\n📊 Начальное состояние: {manager.current_state.value}")
    
    # Тест 1: Валидные переходы
    print("\n🔄 Тест 1: Валидные переходы")
    
    transitions = [
        (GameState.CHARACTER_SELECTION, "system"),
        (GameState.LOADING_SCENARIO, "system"),
        (GameState.EXPLORATION, "system"),
        (GameState.DIALOGUE, "scenario_engine"),
        (GameState.EXPLORATION, "system"),
        (GameState.COMBAT, "combat_system"),
        (GameState.EXPLORATION, "system"),
        (GameState.PAUSED, "gm"),
        (GameState.EXPLORATION, "gm"),
        (GameState.SCENARIO_COMPLETED, "scenario_engine"),
        (GameState.ROOM_CLOSED, "system")
    ]
    
    for state, source in transitions:
        success = await manager.change_state(state, source)
        print(f"   {state.value} ({source}): {'✅' if success else '❌'}")
    
    # Проверяем историю
    print(f"\n📚 История ({len(manager.state_history)} переходов)")
    
    # Проверяем метрики
    metrics = manager.get_metrics()
    print(f"\n📊 Метрики:")
    print(f"   Всего переходов: {metrics['total_transitions']}")
    print(f"   Текущее состояние: {metrics['current_state']}")
    
    # Тест 2: Невалидные переходы
    print("\n🔄 Тест 2: Невалидные переходы")
    
    # Возвращаемся в Lobby
    await manager.change_state(GameState.LOBBY, "system", force=True)
    print(f"   Принудительно в Lobby: ✅")
    
    # Пытаемся перейти в Combat напрямую
    success = await manager.change_state(GameState.COMBAT, "system")
    print(f"   LOBBY -> COMBAT (без подготовки): {'❌' if not success else '✅'}")
    
    # Пытаемся перейти в ROOM_CLOSED
    success = await manager.change_state(GameState.ROOM_CLOSED, "system")
    print(f"   LOBBY -> ROOM_CLOSED: {'✅' if success else '❌'}")
    
    # Тест 3: Пауза
    print("\n⏸️ Тест 3: Пауза")
    
    await manager.change_state(GameState.EXPLORATION, "system", force=True)
    print(f"   Перешли в EXPLORATION: ✅")
    
    # Ставим на паузу
    await manager.pause("gm")
    print(f"   Пауза: {manager.current_state.value}")
    
    # Возобновляем
    await manager.resume("gm")
    print(f"   Возобновление: {manager.current_state.value}")
    
    # Тест 4: Подписки
    print("\n📡 Тест 4: Подписки на события")
    
    events_received = []
    
    def on_exploration(old_state, new_state, transition):
        events_received.append(('exploration', new_state.value))
    
    def on_any_state(old_state, new_state, transition):
        events_received.append(('any', new_state.value))
    
    manager.on_state(GameState.EXPLORATION, on_exploration)
    manager.on_any_state(on_any_state)
    
    # Переходим в Exploration
    await manager.change_state(GameState.EXPLORATION, "test")
    
    print(f"   Получено событий: {len(events_received)}")
    for event_type, state in events_received:
        print(f"   {event_type}: {state}")
    
    # Тест 5: Контекст
    print("\n📋 Тест 5: Контекст состояния")
    context = manager.get_current_context()
    print(f"   Текущее состояние: {context['state']}")
    print(f"   Можно на паузу: {context['can_pause']}")
    print(f"   Терминальное: {context['is_terminal']}")
    print(f"   Допустимые переходы: {context['allowed_transitions']}")
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# 23.7. ГЛОБАЛЬНЫЙ ИНСТАНС
# ============================================================

game_state_manager_factory = GameStateManagerFactory()

# ============================================================
# 23.8. ЗАПУСК ТЕСТОВ
# ============================================================

if __name__ == "__main__":
    asyncio.run(test_game_state_manager())
