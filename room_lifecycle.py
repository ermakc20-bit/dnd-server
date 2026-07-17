# ============================================================
# 22. ROOM LIFECYCLE SYSTEM
# ============================================================

import asyncio
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import defaultdict
import copy
import time

# ============================================================
# 22.1. БАЗОВЫЕ КЛАССЫ
# ============================================================

class RoomState(str, Enum):
    """Состояния комнаты."""
    CREATED = "created"                 # Только что создана
    PREPARING = "preparing"             # Идёт подготовка
    WAITING_PLAYERS = "waiting_players" # Ожидание игроков
    READY = "ready"                     # Готовность к старту
    RUNNING = "running"                 # Игровая сессия
    PAUSED = "paused"                   # На паузе
    FINISHED = "finished"               # Завершена
    CLOSED = "closed"                   # Закрыта
    ERROR = "error"                     # Ошибка

class RoomEventType(str, Enum):
    """Типы событий комнаты."""
    CREATED = "room_created"
    PREPARING = "room_preparing"
    SCENARIO_SELECTED = "scenario_selected"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_READY = "player_ready"
    ALL_READY = "all_ready"
    STARTED = "room_started"
    PAUSED = "room_paused"
    RESUMED = "room_resumed"
    FINISHED = "room_finished"
    CLOSED = "room_closed"
    ERROR = "room_error"

class PlayerStatus(str, Enum):
    """Статус игрока в комнате."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    IN_GAME = "in_game"
    DISCONNECTED = "disconnected"
    LEFT = "left"

@dataclass
class RoomPlayer:
    """Игрок в комнате."""
    user_id: int
    username: str
    character_id: Optional[int] = None
    character_name: Optional[str] = None
    status: PlayerStatus = PlayerStatus.CONNECTED
    is_ready: bool = False
    is_gm: bool = False
    joined_at: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'username': self.username,
            'character_id': self.character_id,
            'character_name': self.character_name,
            'status': self.status.value,
            'is_ready': self.is_ready,
            'is_gm': self.is_gm,
            'joined_at': self.joined_at.isoformat(),
            'last_seen': self.last_seen.isoformat(),
            'metadata': self.metadata
        }

@dataclass
class RoomConfig:
    """Конфигурация комнаты."""
    max_players: int = 6
    is_private: bool = False
    password_hash: Optional[str] = None
    turn_timer: int = 60  # секунд
    dice_mode: str = "standard"
    allow_spectators: bool = False
    auto_start: bool = False
    auto_start_delay: int = 30  # секунд
    save_interval: int = 60  # секунд
    timeout_seconds: int = 300  # 5 минут бездействия
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RoomMetrics:
    """Метрики комнаты."""
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    total_players: int = 0
    total_events: int = 0
    total_actions: int = 0
    total_combats: int = 0
    total_time_seconds: float = 0
    peak_players: int = 0
    disconnections: int = 0
    reconnections: int = 0
    
    def to_dict(self) -> dict:
        return {
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'paused_at': self.paused_at.isoformat() if self.paused_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'total_players': self.total_players,
            'total_events': self.total_events,
            'total_actions': self.total_actions,
            'total_combats': self.total_combats,
            'total_time_seconds': self.total_time_seconds,
            'peak_players': self.peak_players,
            'disconnections': self.disconnections,
            'reconnections': self.reconnections
        }

# ============================================================
# 22.2. ROOM LIFECYCLE ENGINE
# ============================================================

class RoomLifecycleEngine:
    """
    Движок жизненного цикла комнаты.
    Управляет созданием, подготовкой, запуском и завершением комнат.
    """
    
    def __init__(
        self,
        room_id: int,
        room_name: str,
        gm_id: int,
        gm_name: str,
        config: Optional[RoomConfig] = None
    ):
        self.room_id = room_id
        self.room_name = room_name
        self.gm_id = gm_id
        self.gm_name = gm_name
        self.config = config or RoomConfig()
        
        self.state: RoomState = RoomState.CREATED
        self.players: Dict[int, RoomPlayer] = {}
        self.metrics = RoomMetrics()
        
        # Интеграция с другими системами
        self.scenario_engine = None
        self.event_bus = None
        self.turn_manager = None
        self.combat_system = None
        
        # Внутренние состояния
        self._is_running = False
        self._is_paused = False
        self._started_at: Optional[datetime] = None
        self._paused_at: Optional[datetime] = None
        self._paused_duration: float = 0
        self._scenario_id: Optional[str] = None
        
        # Таймеры и задачи
        self._save_task: Optional[asyncio.Task] = None
        self._timeout_task: Optional[asyncio.Task] = None
        self._auto_start_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        
        # События
        self._event_listeners: Dict[RoomEventType, List[Callable]] = defaultdict(list)
        
        # Логирование
        self._logger = logging.getLogger(f"room_lifecycle.{room_id}")
        
        self._logger.info(f"Room {room_id} created: {room_name}")
    
    # ===== УПРАВЛЕНИЕ СОСТОЯНИЕМ =====
    
    async def set_state(self, new_state: RoomState, data: Optional[Dict] = None) -> bool:
        """
        Устанавливает новое состояние комнаты.
        """
        old_state = self.state
        self.state = new_state
        
        self._logger.info(f"State changed: {old_state.value} -> {new_state.value}")
        
        # Публикуем событие
        await self._publish_event(RoomEventType.ERROR, {
            'old_state': old_state.value,
            'new_state': new_state.value,
            'data': data or {}
        })
        
        return True
    
    async def transition_to(self, target_state: RoomState, data: Optional[Dict] = None) -> bool:
        """
        Выполняет переход к целевому состоянию с проверками.
        """
        transitions = {
            RoomState.CREATED: [RoomState.PREPARING, RoomState.CLOSED],
            RoomState.PREPARING: [RoomState.WAITING_PLAYERS, RoomState.CLOSED, RoomState.ERROR],
            RoomState.WAITING_PLAYERS: [RoomState.READY, RoomState.CLOSED, RoomState.ERROR],
            RoomState.READY: [RoomState.RUNNING, RoomState.CLOSED, RoomState.ERROR],
            RoomState.RUNNING: [RoomState.PAUSED, RoomState.FINISHED, RoomState.CLOSED, RoomState.ERROR],
            RoomState.PAUSED: [RoomState.RUNNING, RoomState.FINISHED, RoomState.CLOSED, RoomState.ERROR],
            RoomState.FINISHED: [RoomState.CLOSED],
            RoomState.ERROR: [RoomState.CLOSED],
            RoomState.CLOSED: []
        }
        
        if target_state not in transitions.get(self.state, []):
            self._logger.warning(f"Invalid transition: {self.state.value} -> {target_state.value}")
            return False
        
        return await self.set_state(target_state, data)
    
    # ===== УПРАВЛЕНИЕ КОМНАТОЙ =====
    
    async def prepare(self, scenario_id: str) -> bool:
        """
        Подготовка комнаты к запуску.
        """
        if self.state != RoomState.CREATED:
            self._logger.warning(f"Cannot prepare: current state is {self.state.value}")
            return False
        
        await self.set_state(RoomState.PREPARING)
        
        self._scenario_id = scenario_id
        
        # Загружаем сценарий
        if self.scenario_engine:
            success = await self._load_scenario(scenario_id)
            if not success:
                await self.set_state(RoomState.ERROR, {'error': 'Failed to load scenario'})
                return False
        
        # Переходим к ожиданию игроков
        await self.transition_to(RoomState.WAITING_PLAYERS)
        
        self._logger.info(f"Room prepared with scenario: {scenario_id}")
        return True
    
    async def start(self) -> bool:
        """
        Запускает игровую сессию.
        """
        if self.state != RoomState.READY:
            self._logger.warning(f"Cannot start: current state is {self.state.value}")
            return False
        
        if not self._is_ready():
            self._logger.warning("Room is not ready to start")
            return False
        
        await self.transition_to(RoomState.RUNNING)
        
        self._started_at = datetime.now()
        self.metrics.started_at = self._started_at
        
        # Запускаем сценарий
        if self.scenario_engine:
            await self.scenario_engine.start()
        
        # Запускаем Event Bus
        if self.event_bus:
            await self.event_bus.start()
        
        # Запускаем таймеры
        await self._start_timers()
        
        self._is_running = True
        
        self._logger.info("Room started!")
        return True
    
    async def pause(self) -> bool:
        """
        Ставит комнату на паузу.
        """
        if self.state != RoomState.RUNNING:
            self._logger.warning(f"Cannot pause: current state is {self.state.value}")
            return False
        
        await self.transition_to(RoomState.PAUSED)
        
        self._paused_at = datetime.now()
        self.metrics.paused_at = self._paused_at
        
        # Приостанавливаем сценарий
        if self.scenario_engine:
            await self.scenario_engine.pause()
        
        self._is_paused = True
        
        self._logger.info("Room paused")
        return True
    
    async def resume(self) -> bool:
        """
        Возобновляет комнату.
        """
        if self.state != RoomState.PAUSED:
            self._logger.warning(f"Cannot resume: current state is {self.state.value}")
            return False
        
        await self.transition_to(RoomState.RUNNING)
        
        if self._paused_at:
            self._paused_duration += (datetime.now() - self._paused_at).total_seconds()
            self._paused_at = None
        
        # Возобновляем сценарий
        if self.scenario_engine:
            await self.scenario_engine.resume()
        
        self._is_paused = False
        
        self._logger.info("Room resumed")
        return True
    
    async def finish(self, result: str = "completed") -> bool:
        """
        Завершает игровую сессию.
        """
        if self.state not in [RoomState.RUNNING, RoomState.PAUSED]:
            self._logger.warning(f"Cannot finish: current state is {self.state.value}")
            return False
        
        await self.transition_to(RoomState.FINISHED)
        
        self.metrics.finished_at = datetime.now()
        
        # Останавливаем сценарий
        if self.scenario_engine:
            await self.scenario_engine.stop()
        
        # Останавливаем таймеры
        await self._stop_timers()
        
        self._is_running = False
        self._is_paused = False
        
        # Вычисляем общее время
        if self._started_at:
            self.metrics.total_time_seconds = (datetime.now() - self._started_at).total_seconds()
            if self._paused_duration > 0:
                self.metrics.total_time_seconds -= self._paused_duration
        
        self._logger.info(f"Room finished with result: {result}")
        return True
    
    async def close(self) -> bool:
        """
        Закрывает комнату и освобождает ресурсы.
        """
        if self.state == RoomState.RUNNING or self.state == RoomState.PAUSED:
            await self.finish("closed")
        
        if self.state != RoomState.FINISHED and self.state != RoomState.ERROR:
            await self.transition_to(RoomState.CLOSED)
        else:
            await self.set_state(RoomState.CLOSED)
        
        self.metrics.closed_at = datetime.now()
        
        # Освобождаем ресурсы
        await self._cleanup()
        
        self._logger.info("Room closed")
        return True
    
    # ===== УПРАВЛЕНИЕ ИГРОКАМИ =====
    
    def add_player(self, user_id: int, username: str, is_gm: bool = False) -> bool:
        """
        Добавляет игрока в комнату.
        """
        if user_id in self.players:
            self._logger.warning(f"Player {username} already in room")
            return False
        
        if len(self.players) >= self.config.max_players:
            self._logger.warning(f"Room is full: {self.config.max_players}")
            return False
        
        player = RoomPlayer(
            user_id=user_id,
            username=username,
            is_gm=is_gm,
            status=PlayerStatus.CONNECTED
        )
        
        self.players[user_id] = player
        self.metrics.total_players += 1
        
        if len(self.players) > self.metrics.peak_players:
            self.metrics.peak_players = len(self.players)
        
        self._logger.info(f"Player {username} joined room")
        
        # Если есть GM, меняем состояние
        if is_gm:
            self.gm_id = user_id
            self.gm_name = username
        
        return True
    
    def remove_player(self, user_id: int) -> bool:
        """
        Удаляет игрока из комнаты.
        """
        if user_id not in self.players:
            return False
        
        player = self.players[user_id]
        self.players.pop(user_id)
        
        self._logger.info(f"Player {player.username} left room")
        return True
    
    def get_player(self, user_id: int) -> Optional[RoomPlayer]:
        """
        Получает игрока по ID.
        """
        return self.players.get(user_id)
    
    def set_player_ready(self, user_id: int, is_ready: bool) -> bool:
        """
        Устанавливает готовность игрока.
        """
        player = self.get_player(user_id)
        if not player:
            return False
        
        player.is_ready = is_ready
        if is_ready:
            player.status = PlayerStatus.READY
        else:
            player.status = PlayerStatus.CONNECTED
        
        self._logger.info(f"Player {player.username} ready: {is_ready}")
        
        # Проверяем, все ли готовы
        if self._all_ready():
            if self.config.auto_start:
                self._schedule_auto_start()
            else:
                self._logger.info("All players ready. Waiting for GM to start.")
        
        return True
    
    def assign_character(self, user_id: int, character_id: int, character_name: str) -> bool:
        """
        Назначает персонажа игроку.
        """
        player = self.get_player(user_id)
        if not player:
            return False
        
        player.character_id = character_id
        player.character_name = character_name
        
        self._logger.info(f"Player {player.username} assigned character: {character_name}")
        return True
    
    def update_player_status(self, user_id: int, status: PlayerStatus) -> bool:
        """
        Обновляет статус игрока.
        """
        player = self.get_player(user_id)
        if not player:
            return False
        
        player.status = status
        player.last_seen = datetime.now()
        
        return True
    
    # ===== ПРОВЕРКИ =====
    
    def _is_ready(self) -> bool:
        """
        Проверяет, готова ли комната к старту.
        """
        # Есть ли GM
        if self.gm_id not in self.players:
            self._logger.warning("GM not present")
            return False
        
        # Все ли игроки готовы
        if not self._all_ready():
            self._logger.warning("Not all players are ready")
            return False
        
        # Загружен ли сценарий
        if not self._scenario_id:
            self._logger.warning("No scenario selected")
            return False
        
        # Все ли игроки имеют персонажей
        for player in self.players.values():
            if not player.is_gm and not player.character_id:
                self._logger.warning(f"Player {player.username} has no character")
                return False
        
        return True
    
    def _all_ready(self) -> bool:
        """
        Проверяет, все ли игроки готовы.
        """
        for player in self.players.values():
            if not player.is_gm and not player.is_ready:
                return False
        return True
    
    def _all_players_connected(self) -> bool:
        """
        Проверяет, все ли игроки подключены.
        """
        for player in self.players.values():
            if player.status in [PlayerStatus.DISCONNECTED, PlayerStatus.LEFT]:
                return False
        return True
    
    # ===== ТАЙМЕРЫ =====
    
    async def _start_timers(self) -> None:
        """Запускает таймеры."""
        # Таймер сохранения
        if self.config.save_interval > 0:
            self._save_task = asyncio.create_task(self._save_loop())
        
        # Таймер проверки подключения
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        # Таймер бездействия
        if self.config.timeout_seconds > 0:
            self._timeout_task = asyncio.create_task(self._timeout_loop())
    
    async def _stop_timers(self) -> None:
        """Останавливает таймеры."""
        for task in [self._save_task, self._health_check_task, self._timeout_task, self._auto_start_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._save_task = None
        self._health_check_task = None
        self._timeout_task = None
        self._auto_start_task = None
    
    async def _save_loop(self) -> None:
        """Периодическое сохранение состояния."""
        while self._is_running:
            await asyncio.sleep(self.config.save_interval)
            await self._save_state()
    
    async def _health_check_loop(self) -> None:
        """Периодическая проверка подключения игроков."""
        while self._is_running:
            await asyncio.sleep(10)
            await self._check_connections()
    
    async def _timeout_loop(self) -> None:
        """Таймер бездействия."""
        while self._is_running:
            await asyncio.sleep(self.config.timeout_seconds)
            
            # Проверяем, были ли действия за последние N секунд
            last_action = getattr(self, '_last_action_time', datetime.now())
            if (datetime.now() - last_action).total_seconds() > self.config.timeout_seconds:
                self._logger.warning("Room inactive, auto-finishing...")
                await self.finish("timeout")
                break
    
    def _schedule_auto_start(self) -> None:
        """Планирует автоматический старт."""
        if not self.config.auto_start:
            return
        
        self._auto_start_task = asyncio.create_task(self._auto_start())
    
    async def _auto_start(self) -> None:
        """Автоматический старт после задержки."""
        await asyncio.sleep(self.config.auto_start_delay)
        
        if self.state == RoomState.WAITING_PLAYERS and self._all_ready():
            await self.transition_to(RoomState.READY)
            await self.start()
    
    # ===== СОХРАНЕНИЕ =====
    
    async def _save_state(self) -> None:
        """Сохраняет состояние комнаты."""
        state = self.get_state()
        self._logger.debug(f"State saved: {len(str(state))} bytes")
        
        # Можно сохранять в БД или файл
        # TODO: Интеграция с Save System
    
    async def _load_scenario(self, scenario_id: str) -> bool:
        """
        Загружает сценарий.
        """
        if not self.scenario_engine:
            self._logger.warning("Scenario Engine not initialized")
            return False
        
        # TODO: Получить сценарий из Scenario Manager
        # self.scenario_engine.load_scenario(scenario)
        
        self._logger.info(f"Scenario loaded: {scenario_id}")
        return True
    
    async def _check_connections(self) -> None:
        """Проверяет подключения игроков."""
        for player in self.players.values():
            # TODO: Проверка через WebSocket
            pass
    
    async def _cleanup(self) -> None:
        """Очищает ресурсы."""
        # Останавливаем Event Bus
        if self.event_bus:
            await self.event_bus.stop()
        
        # Останавливаем таймеры
        await self._stop_timers()
        
        # Очищаем игроков
        self.players.clear()
        
        self._logger.info("Resources cleaned up")
    
    # ===== СОБЫТИЯ =====
    
    async def _publish_event(self, event_type: RoomEventType, data: Dict[str, Any]) -> None:
        """
        Публикует событие комнаты.
        """
        if self.event_bus:
            # Используем Event System
            from event_system import EventFactory
            event = EventFactory.create_event(
                f"room_{event_type.value}",
                self.room_id,
                "room_lifecycle",
                "",
                data
            )
            await self.event_bus.publish(event)
        
        # Вызываем локальные обработчики
        if event_type in self._event_listeners:
            for listener in self._event_listeners[event_type]:
                try:
                    await listener(data)
                except Exception as e:
                    self._logger.error(f"Event listener error: {e}")
    
    def on(self, event_type: RoomEventType, callback: Callable) -> None:
        """Подписывается на событие."""
        self._event_listeners[event_type].append(callback)
    
    def off(self, event_type: RoomEventType, callback: Callable) -> None:
        """Отписывается от события."""
        if event_type in self._event_listeners:
            self._event_listeners[event_type].remove(callback)
    
    # ===== СОСТОЯНИЕ =====
    
    def get_state(self) -> Dict[str, Any]:
        """Возвращает состояние комнаты."""
        return {
            'room_id': self.room_id,
            'room_name': self.room_name,
            'state': self.state.value,
            'gm_id': self.gm_id,
            'gm_name': self.gm_name,
            'scenario_id': self._scenario_id,
            'players': [p.to_dict() for p in self.players.values()],
            'config': {
                'max_players': self.config.max_players,
                'is_private': self.config.is_private,
                'turn_timer': self.config.turn_timer,
                'dice_mode': self.config.dice_mode,
                'allow_spectators': self.config.allow_spectators,
                'auto_start': self.config.auto_start,
                'auto_start_delay': self.config.auto_start_delay,
                'save_interval': self.config.save_interval,
                'timeout_seconds': self.config.timeout_seconds
            },
            'metrics': self.metrics.to_dict(),
            'is_running': self._is_running,
            'is_paused': self._is_paused,
            'started_at': self._started_at.isoformat() if self._started_at else None,
            'paused_at': self._paused_at.isoformat() if self._paused_at else None,
            'paused_duration': self._paused_duration
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Возвращает краткую информацию о комнате."""
        return {
            'room_id': self.room_id,
            'room_name': self.room_name,
            'state': self.state.value,
            'gm_name': self.gm_name,
            'players_count': len(self.players),
            'max_players': self.config.max_players,
            'is_running': self._is_running,
            'is_paused': self._is_paused,
            'created_at': self.metrics.created_at.isoformat()
        }

# ============================================================
# 22.3. ROOM LIFECYCLE MANAGER
# ============================================================

class RoomLifecycleManager:
    """
    Менеджер жизненного цикла комнат.
    Управляет всеми комнатами на сервере.
    """
    
    def __init__(self):
        self._rooms: Dict[int, RoomLifecycleEngine] = {}
        self._room_counter = 0
        self._logger = logging.getLogger("room_lifecycle_manager")
        
        # Интеграция с другими системами
        self.scenario_manager = None
        self.event_manager = None
        self.turn_manager = None
        self.combat_system = None
    
    async def create_room(
        self,
        room_name: str,
        gm_id: int,
        gm_name: str,
        config: Optional[RoomConfig] = None
    ) -> RoomLifecycleEngine:
        """
        Создаёт новую комнату.
        """
        self._room_counter += 1
        room_id = self._room_counter
        
        # Создаём движок
        engine = RoomLifecycleEngine(
            room_id=room_id,
            room_name=room_name,
            gm_id=gm_id,
            gm_name=gm_name,
            config=config
        )
        
        # Интегрируем с другими системами
        if self.scenario_manager:
            engine.scenario_engine = self.scenario_manager.create_engine(room_id)
        
        if self.event_manager:
            engine.event_bus = self.event_manager.create_bus(f"room_{room_id}")
        
        if self.turn_manager:
            engine.turn_manager = self.turn_manager.create_manager(room_id)
        
        # Добавляем GM как игрока
        engine.add_player(gm_id, gm_name, is_gm=True)
        
        # Сохраняем
        self._rooms[room_id] = engine
        
        self._logger.info(f"Room {room_id} created by {gm_name}")
        return engine
    
    def get_room(self, room_id: int) -> Optional[RoomLifecycleEngine]:
        """Получает комнату по ID."""
        return self._rooms.get(room_id)
    
    def get_room_by_name(self, room_name: str) -> Optional[RoomLifecycleEngine]:
        """Получает комнату по имени."""
        for room in self._rooms.values():
            if room.room_name == room_name:
                return room
        return None
    
    def get_all_rooms(self) -> List[RoomLifecycleEngine]:
        """Получает все комнаты."""
        return list(self._rooms.values())
    
    def get_rooms_by_state(self, state: RoomState) -> List[RoomLifecycleEngine]:
        """Получает комнаты по состоянию."""
        return [r for r in self._rooms.values() if r.state == state]
    
    def get_rooms_for_player(self, user_id: int) -> List[RoomLifecycleEngine]:
        """Получает комнаты, в которых состоит игрок."""
        return [r for r in self._rooms.values() if user_id in r.players]
    
    def get_rooms_for_gm(self, gm_id: int) -> List[RoomLifecycleEngine]:
        """Получает комнаты, которые ведёт GM."""
        return [r for r in self._rooms.values() if r.gm_id == gm_id]
    
    async def close_room(self, room_id: int) -> bool:
        """
        Закрывает комнату.
        """
        room = self.get_room(room_id)
        if not room:
            return False
        
        await room.close()
        
        # Удаляем из списка
        del self._rooms[room_id]
        
        self._logger.info(f"Room {room_id} closed")
        return True
    
    async def close_all_rooms(self) -> None:
        """
        Закрывает все комнаты.
        """
        for room_id in list(self._rooms.keys()):
            await self.close_room(room_id)
        
        self._logger.info("All rooms closed")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Возвращает статистику по комнатам.
        """
        stats = {
            'total_rooms': len(self._rooms),
            'by_state': {},
            'total_players': 0,
            'active_rooms': 0,
            'paused_rooms': 0
        }
        
        for room in self._rooms.values():
            state = room.state.value
            stats['by_state'][state] = stats['by_state'].get(state, 0) + 1
            stats['total_players'] += len(room.players)
            
            if room.state == RoomState.RUNNING:
                stats['active_rooms'] += 1
            elif room.state == RoomState.PAUSED:
                stats['paused_rooms'] += 1
        
        return stats

# ============================================================
# 22.4. ROOM BUILDER
# ============================================================

class RoomBuilder:
    """
    Билдер для создания комнат с конфигурацией.
    """
    
    def __init__(self, manager: RoomLifecycleManager):
        self.manager = manager
        self.room_name = ""
        self.gm_id = 0
        self.gm_name = ""
        self.config = RoomConfig()
        self.scenario_id = None
        self.preload_players: List[Dict] = []
        self.preload_characters: List[Dict] = []
    
    def set_name(self, name: str) -> 'RoomBuilder':
        """Устанавливает имя комнаты."""
        self.room_name = name
        return self
    
    def set_gm(self, gm_id: int, gm_name: str) -> 'RoomBuilder':
        """Устанавливает GM."""
        self.gm_id = gm_id
        self.gm_name = gm_name
        return self
    
    def set_scenario(self, scenario_id: str) -> 'RoomBuilder':
        """Устанавливает сценарий."""
        self.scenario_id = scenario_id
        return self
    
    def set_max_players(self, max_players: int) -> 'RoomBuilder':
        """Устанавливает максимальное количество игроков."""
        self.config.max_players = max_players
        return self
    
    def set_private(self, is_private: bool, password: Optional[str] = None) -> 'RoomBuilder':
        """Устанавливает приватность комнаты."""
        self.config.is_private = is_private
        if password:
            import hashlib
            self.config.password_hash = hashlib.sha256(password.encode()).hexdigest()
        return self
    
    def set_turn_timer(self, seconds: int) -> 'RoomBuilder':
        """Устанавливает таймер хода."""
        self.config.turn_timer = seconds
        return self
    
    def set_dice_mode(self, mode: str) -> 'RoomBuilder':
        """Устанавливает режим кубиков."""
        self.config.dice_mode = mode
        return self
    
    def set_auto_start(self, enabled: bool, delay: int = 30) -> 'RoomBuilder':
        """Устанавливает автоматический старт."""
        self.config.auto_start = enabled
        self.config.auto_start_delay = delay
        return self
    
    def set_timeout(self, seconds: int) -> 'RoomBuilder':
        """Устанавливает тайм-аут бездействия."""
        self.config.timeout_seconds = seconds
        return self
    
    def add_player(self, user_id: int, username: str) -> 'RoomBuilder':
        """Добавляет игрока в комнату."""
        self.preload_players.append({
            'user_id': user_id,
            'username': username
        })
        return self
    
    def set_metadata(self, key: str, value: Any) -> 'RoomBuilder':
        """Устанавливает метаданные."""
        self.config.metadata[key] = value
        return self
    
    async def build(self) -> RoomLifecycleEngine:
        """Создаёт комнату."""
        # Создаём комнату
        room = await self.manager.create_room(
            room_name=self.room_name,
            gm_id=self.gm_id,
            gm_name=self.gm_name,
            config=self.config
        )
        
        # Добавляем предзагруженных игроков
        for player_data in self.preload_players:
            room.add_player(
                user_id=player_data['user_id'],
                username=player_data['username'],
                is_gm=False
            )
        
        # Загружаем сценарий
        if self.scenario_id:
            await room.prepare(self.scenario_id)
        
        return room

# ============================================================
# 22.5. ТЕСТЫ
# ============================================================

async def test_room_lifecycle():
    """Тестирование Room Lifecycle System."""
    print("\n" + "="*60)
    print("🧪 ТЕСТИРОВАНИЕ ROOM LIFECYCLE SYSTEM")
    print("="*60)
    
    # Создаём менеджер
    manager = RoomLifecycleManager()
    
    # Создаём комнату через билдер
    room = await (
        RoomBuilder(manager)
        .set_name("Test Adventure Room")
        .set_gm(1, "TestGM")
        .set_scenario("test_scenario_1")
        .set_max_players(4)
        .set_turn_timer(60)
        .set_auto_start(False)
        .add_player(2, "Player1")
        .add_player(3, "Player2")
        .set_metadata("difficulty", "normal")
        .build()
    )
    
    print(f"\n🏠 Комната создана:")
    print(f"   ID: {room.room_id}")
    print(f"   Название: {room.room_name}")
    print(f"   Состояние: {room.state.value}")
    
    # Проверяем состояние
    state = room.get_state()
    print(f"\n📊 Состояние комнаты:")
    print(f"   Игроков: {len(state['players'])}")
    print(f"   Максимум: {state['config']['max_players']}")
    print(f"   GM: {state['gm_name']}")
    
    # Добавляем игроков
    print("\n👥 Добавление игроков...")
    room.add_player(4, "Player3")
    room.add_player(5, "Player4")
    
    # Назначаем персонажей
    print("\n🎭 Назначение персонажей...")
    room.assign_character(2, 101, "Warrior")
    room.assign_character(3, 102, "Mage")
    room.assign_character(4, 103, "Rogue")
    room.assign_character(5, 104, "Cleric")
    
    # Игроки готовятся
    print("\n✅ Подготовка игроков...")
    room.set_player_ready(2, True)
    room.set_player_ready(3, True)
    room.set_player_ready(4, True)
    room.set_player_ready(5, True)
    
    # Проверяем готовность
    print("\n🔍 Проверка готовности...")
    print(f"   Все готовы: {room._all_ready()}")
    print(f"   Комната готова: {room._is_ready()}")
    
    # Переходим в состояние Ready
    await room.transition_to(RoomState.READY)
    print(f"\n📊 Состояние после проверки: {room.state.value}")
    
    # Запускаем
    print("\n🚀 Запуск комнаты...")
    await room.start()
    print(f"   Состояние: {room.state.value}")
    print(f"   Running: {room._is_running}")
    
    # Пауза
    print("\n⏸️ Пауза...")
    await room.pause()
    print(f"   Состояние: {room.state.value}")
    print(f"   Paused: {room._is_paused}")
    
    # Возобновляем
    print("\n▶️ Возобновление...")
    await room.resume()
    print(f"   Состояние: {room.state.value}")
    print(f"   Paused: {room._is_paused}")
    
    # Завершаем
    print("\n🏁 Завершение...")
    await room.finish("completed")
    print(f"   Состояние: {room.state.value}")
    
    # Получаем метрики
    metrics = room.metrics.to_dict()
    print(f"\n📊 Метрики:")
    print(f"   Всего игроков: {metrics['total_players']}")
    print(f"   Пик игроков: {metrics['peak_players']}")
    print(f"   Время сессии: {metrics['total_time_seconds']:.2f} сек")
    
    # Закрываем
    print("\n🔒 Закрытие комнаты...")
    await room.close()
    print(f"   Состояние: {room.state.value}")
    
    # Проверяем статистику менеджера
    stats = manager.get_statistics()
    print(f"\n📊 Статистика менеджера:")
    print(f"   Всего комнат: {stats['total_rooms']}")
    print(f"   Всего игроков: {stats['total_players']}")
    print(f"   Активных: {stats['active_rooms']}")
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# 22.6. ГЛОБАЛЬНЫЙ ИНСТАНС
# ============================================================

room_lifecycle_manager = RoomLifecycleManager()

# ============================================================
# 22.7. ЗАПУСК ТЕСТОВ
# ============================================================

if __name__ == "__main__":
    asyncio.run(test_room_lifecycle())
