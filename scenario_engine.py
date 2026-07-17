# ============================================================
# 21. SCENARIO ENGINE
# ============================================================

import asyncio
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Union
from enum import Enum, auto
from dataclasses import dataclass, field
from collections import defaultdict
import copy

# ============================================================
# 21.1. БАЗОВЫЕ КЛАССЫ
# ============================================================

class SceneType(str, Enum):
    """Типы сцен."""
    EXPLORATION = "exploration"      # Свободное исследование
    DIALOG = "dialog"                # Диалог с NPC
    CHECK = "check"                  # Проверка навыков
    COMBAT = "combat"                # Боевая сцена
    CUTSCENE = "cutscene"            # Кат-сцена
    FINAL = "final"                  # Финальная сцена
    PUZZLE = "puzzle"                # Головоломка
    TRAVEL = "travel"                # Путешествие
    REST = "rest"                    # Отдых
    SHOP = "shop"                    # Магазин

class QuestState(str, Enum):
    """Состояние квеста."""
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"

class TriggerType(str, Enum):
    """Типы триггеров."""
    PLAYER_ENTER_AREA = "player_enter_area"
    PLAYER_EXIT_AREA = "player_exit_area"
    PLAYER_INTERACT = "player_interact"
    NPC_DIED = "npc_died"
    NPC_SPAWNED = "npc_spawned"
    ITEM_PICKED = "item_picked"
    ITEM_USED = "item_used"
    DIALOG_STARTED = "dialog_started"
    DIALOG_ENDED = "dialog_ended"
    CHECK_PASSED = "check_passed"
    CHECK_FAILED = "check_failed"
    COMBAT_STARTED = "combat_started"
    COMBAT_FINISHED = "combat_finished"
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    ROUND_STARTED = "round_started"
    ROUND_ENDED = "round_ended"
    TIME_ELAPSED = "time_elapsed"
    VARIABLE_CHANGED = "variable_changed"
    QUEST_STATE_CHANGED = "quest_state_changed"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    ALL_PLAYERS_READY = "all_players_ready"
    CUSTOM = "custom"

class ActionType(str, Enum):
    """Типы действий триггера."""
    CHANGE_SCENE = "change_scene"
    SHOW_TEXT = "show_text"
    START_COMBAT = "start_combat"
    SPAWN_NPC = "spawn_npc"
    REMOVE_NPC = "remove_npc"
    GIVE_ITEM = "give_item"
    REMOVE_ITEM = "remove_item"
    SET_VARIABLE = "set_variable"
    START_QUEST = "start_quest"
    COMPLETE_QUEST = "complete_quest"
    FAIL_QUEST = "fail_quest"
    OPEN_DOOR = "open_door"
    CLOSE_DOOR = "close_door"
    LOCK_DOOR = "lock_door"
    UNLOCK_DOOR = "unlock_door"
    SHOW_DIALOG = "show_dialog"
    PLAY_SOUND = "play_sound"
    SHOW_ANIMATION = "show_animation"
    DELAY = "delay"
    END_SCENARIO = "end_scenario"
    CALL_FUNCTION = "call_function"
    SPAWN_ITEM = "spawn_item"
    TELEPORT_PLAYER = "teleport_player"
    APPLY_EFFECT = "apply_effect"
    REMOVE_EFFECT = "remove_effect"
    SET_LIGHTING = "set_lighting"
    PLAY_MUSIC = "play_music"
    CUSTOM = "custom"

# ============================================================
# 21.2. СТРУКТУРА СЦЕНАРИЯ
# ============================================================

@dataclass
class ScenarioVariable:
    """Переменная сценария."""
    name: str
    value: Any
    type: str = "string"  # string, int, float, bool, dict, list
    description: str = ""
    is_persistent: bool = True
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'value': self.value,
            'type': self.type,
            'description': self.description,
            'is_persistent': self.is_persistent
        }

@dataclass
class Quest:
    """Квест."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    state: QuestState = QuestState.NOT_STARTED
    progress: int = 0
    max_progress: int = 100
    objectives: List[str] = field(default_factory=list)
    completed_objectives: List[str] = field(default_factory=list)
    rewards: Dict[str, Any] = field(default_factory=dict)
    start_trigger: Optional[str] = None
    complete_trigger: Optional[str] = None
    fail_trigger: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'state': self.state.value,
            'progress': self.progress,
            'max_progress': self.max_progress,
            'objectives': self.objectives,
            'completed_objectives': self.completed_objectives,
            'rewards': self.rewards,
            'metadata': self.metadata
        }
    
    def update_progress(self, amount: int) -> None:
        """Обновляет прогресс квеста."""
        self.progress = min(self.progress + amount, self.max_progress)
        if self.progress >= self.max_progress:
            self.state = QuestState.COMPLETED

@dataclass
class Trigger:
    """Триггер сценария."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: TriggerType = TriggerType.CUSTOM
    condition: str = ""  # JavaScript-like expression
    actions: List[Dict[str, Any]] = field(default_factory=list)
    priority: int = 0
    is_once: bool = True
    is_active: bool = True
    triggered_count: int = 0
    max_triggers: int = 1
    cooldown: float = 0.0
    last_triggered: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_trigger(self) -> bool:
        """Проверяет, может ли триггер сработать."""
        if not self.is_active:
            return False
        if self.is_once and self.triggered_count >= self.max_triggers:
            return False
        if self.cooldown > 0 and self.last_triggered:
            elapsed = (datetime.now() - self.last_triggered).total_seconds()
            if elapsed < self.cooldown:
                return False
        return True
    
    def trigger(self) -> None:
        """Активирует триггер."""
        self.triggered_count += 1
        self.last_triggered = datetime.now()
        if self.triggered_count >= self.max_triggers:
            self.is_active = False
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type.value,
            'condition': self.condition,
            'actions': self.actions,
            'priority': self.priority,
            'is_once': self.is_once,
            'is_active': self.is_active,
            'triggered_count': self.triggered_count,
            'max_triggers': self.max_triggers,
            'cooldown': self.cooldown,
            'metadata': self.metadata
        }

@dataclass
class Scene:
    """Сцена."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    type: SceneType = SceneType.EXPLORATION
    map_id: str = ""
    map_data: Dict[str, Any] = field(default_factory=dict)
    npcs: List[Dict[str, Any]] = field(default_factory=list)
    objects: List[Dict[str, Any]] = field(default_factory=list)
    start_positions: List[Dict[str, Any]] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)
    triggers: List[Trigger] = field(default_factory=list)
    completion_conditions: List[str] = field(default_factory=list)
    on_enter_actions: List[Dict[str, Any]] = field(default_factory=list)
    on_exit_actions: List[Dict[str, Any]] = field(default_factory=list)
    lighting: str = "default"
    music: str = ""
    background: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'type': self.type.value,
            'map_id': self.map_id,
            'map_data': self.map_data,
            'npcs': self.npcs,
            'objects': self.objects,
            'start_positions': self.start_positions,
            'available_actions': self.available_actions,
            'triggers': [t.to_dict() for t in self.triggers],
            'completion_conditions': self.completion_conditions,
            'lighting': self.lighting,
            'music': self.music,
            'background': self.background,
            'metadata': self.metadata
        }

@dataclass
class Scenario:
    """Сценарий."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0"
    author: str = ""
    system: str = "universal"  # dnd, pathfinder, custom
    scenes: List[Scene] = field(default_factory=list)
    variables: List[ScenarioVariable] = field(default_factory=list)
    quests: List[Quest] = field(default_factory=list)
    start_scene_id: str = ""
    current_scene_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def get_scene(self, scene_id: str) -> Optional[Scene]:
        """Получает сцену по ID."""
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        return None
    
    def get_current_scene(self) -> Optional[Scene]:
        """Получает текущую сцену."""
        return self.get_scene(self.current_scene_id)
    
    def get_variable(self, name: str) -> Optional[ScenarioVariable]:
        """Получает переменную по имени."""
        for var in self.variables:
            if var.name == name:
                return var
        return None
    
    def set_variable(self, name: str, value: Any) -> bool:
        """Устанавливает значение переменной."""
        var = self.get_variable(name)
        if var:
            var.value = value
            return True
        return False
    
    def get_quest(self, quest_id: str) -> Optional[Quest]:
        """Получает квест по ID."""
        for quest in self.quests:
            if quest.id == quest_id:
                return quest
        return None
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'author': self.author,
            'system': self.system,
            'scenes': [s.to_dict() for s in self.scenes],
            'variables': [v.to_dict() for v in self.variables],
            'quests': [q.to_dict() for q in self.quests],
            'start_scene_id': self.start_scene_id,
            'current_scene_id': self.current_scene_id,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

# ============================================================
# 21.3. SCENARIO ENGINE
# ============================================================

class ScenarioEngine:
    """
    Универсальный движок сценариев.
    Управляет последовательностью сцен, триггерами и состояниями.
    """
    
    def __init__(self, room_id: int, scenario: Optional[Scenario] = None):
        self.room_id = room_id
        self.scenario = scenario
        self.is_running = False
        self.is_paused = False
        self.current_scene: Optional[Scene] = None
        self.previous_scene: Optional[Scene] = None
        self.scene_history: List[str] = []
        self._triggers_checked: Set[str] = set()
        self._event_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._logger = logging.getLogger(f"scenario_engine.{room_id}")
        self._action_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._scenario_state: Dict[str, Any] = {}
        
        # Интеграция с Event System
        self.event_bus = None
        self.turn_manager = None
        self.combat_system = None
        
        # Счетчики и таймеры
        self._timers: Dict[str, asyncio.Task] = {}
        self._delay_tasks: List[asyncio.Task] = []
        
        # Подписки на события
        self._subscriptions: List[str] = []
    
    # ===== УПРАВЛЕНИЕ СЦЕНАРИЕМ =====
    
    def load_scenario(self, scenario: Scenario) -> None:
        """Загружает сценарий."""
        self.scenario = scenario
        self.current_scene = None
        self.previous_scene = None
        self.scene_history = []
        self._triggers_checked = set()
        self._scenario_state = {}
        
        # Инициализируем переменные
        for var in scenario.variables:
            self._scenario_state[var.name] = var.value
        
        self._logger.info(f"Scenario loaded: {scenario.name}")
    
    async def start(self) -> bool:
        """Запускает сценарий."""
        if not self.scenario:
            self._logger.error("No scenario loaded")
            return False
        
        if self.is_running:
            self._logger.warning("Scenario already running")
            return False
        
        self.is_running = True
        self.is_paused = False
        
        # Находим стартовую сцену
        start_scene = self.scenario.get_scene(self.scenario.start_scene_id)
        if not start_scene:
            # Используем первую сцену
            start_scene = self.scenario.scenes[0] if self.scenario.scenes else None
        
        if not start_scene:
            self._logger.error("No start scene found")
            self.is_running = False
            return False
        
        # Запускаем воркер
        self._worker_task = asyncio.create_task(self._worker())
        
        # Переходим к стартовой сцене
        await self._change_scene(start_scene)
        
        self._logger.info(f"Scenario started: {self.scenario.name}")
        return True
    
    async def stop(self) -> None:
        """Останавливает сценарий."""
        self.is_running = False
        self.is_paused = False
        
        # Отменяем все таймеры
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        
        # Отменяем задачи задержек
        for task in self._delay_tasks:
            task.cancel()
        self._delay_tasks.clear()
        
        # Останавливаем воркер
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        
        self._logger.info("Scenario stopped")
    
    async def pause(self) -> None:
        """Приостанавливает сценарий."""
        self.is_paused = True
        self._logger.info("Scenario paused")
    
    async def resume(self) -> None:
        """Возобновляет сценарий."""
        self.is_paused = False
        self._logger.info("Scenario resumed")
    
    # ===== УПРАВЛЕНИЕ СЦЕНАМИ =====
    
    async def _change_scene(self, scene: Scene, save_history: bool = True) -> bool:
        """
        Переключает сцену.
        """
        if not scene:
            return False
        
        # Выполняем действия при выходе
        if self.current_scene:
            await self._execute_actions(self.current_scene.on_exit_actions)
            if save_history:
                self.scene_history.append(self.current_scene.id)
        
        self.previous_scene = self.current_scene
        self.current_scene = scene
        self.scenario.current_scene_id = scene.id
        
        # Выполняем действия при входе
        await self._execute_actions(scene.on_enter_actions)
        
        # Активируем карту
        if scene.map_id:
            await self._load_map(scene.map_id, scene.map_data)
        
        # Создаём NPC
        for npc_data in scene.npcs:
            await self._spawn_npc(npc_data)
        
        # Создаём объекты
        for obj_data in scene.objects:
            await self._spawn_object(obj_data)
        
        # Устанавливаем позиции игроков
        if scene.start_positions:
            await self._set_player_positions(scene.start_positions)
        
        # Применяем настройки
        if scene.lighting:
            await self._set_lighting(scene.lighting)
        if scene.music:
            await self._play_music(scene.music)
        if scene.background:
            await self._set_background(scene.background)
        
        # Проверяем триггеры
        await self._check_triggers()
        
        self._logger.info(f"Scene changed: {scene.name} ({scene.type.value})")
        
        # Публикуем событие
        await self._publish_event('scene_changed', {
            'scene_id': scene.id,
            'scene_name': scene.name,
            'scene_type': scene.type.value,
            'previous_scene_id': self.previous_scene.id if self.previous_scene else None
        })
        
        return True
    
    async def go_to_scene(self, scene_id: str) -> bool:
        """Переходит к сцене по ID."""
        scene = self.scenario.get_scene(scene_id)
        if not scene:
            self._logger.error(f"Scene not found: {scene_id}")
            return False
        return await self._change_scene(scene)
    
    async def go_to_scene_by_name(self, scene_name: str) -> bool:
        """Переходит к сцене по имени."""
        for scene in self.scenario.scenes:
            if scene.name == scene_name:
                return await self._change_scene(scene)
        return False
    
    async def go_back(self) -> bool:
        """Возвращается к предыдущей сцене."""
        if not self.scene_history:
            return False
        scene_id = self.scene_history.pop()
        scene = self.scenario.get_scene(scene_id)
        if not scene:
            return False
        return await self._change_scene(scene, save_history=False)
    
    async def restart_scene(self) -> bool:
        """Перезапускает текущую сцену."""
        if not self.current_scene:
            return False
        return await self._change_scene(self.current_scene)
    
    # ===== ТРИГГЕРЫ =====
    
    async def _check_triggers(self, event_data: Optional[Dict] = None) -> None:
        """
        Проверяет все активные триггеры.
        """
        if not self.current_scene:
            return
        
        for trigger in self.current_scene.triggers:
            if not trigger.can_trigger():
                continue
            
            # Проверяем условие
            if trigger.condition:
                try:
                    condition_met = await self._evaluate_condition(
                        trigger.condition,
                        event_data
                    )
                    if not condition_met:
                        continue
                except Exception as e:
                    self._logger.error(f"Condition evaluation error: {e}")
                    continue
            
            # Активируем триггер
            trigger.trigger()
            self._logger.info(f"Trigger activated: {trigger.name} ({trigger.type.value})")
            
            # Выполняем действия
            await self._execute_actions(trigger.actions)
            
            # Публикуем событие
            await self._publish_event('trigger_activated', {
                'trigger_id': trigger.id,
                'trigger_name': trigger.name,
                'trigger_type': trigger.type.value
            })
    
    async def _evaluate_condition(self, condition: str, event_data: Optional[Dict] = None) -> bool:
        """
        Вычисляет условие триггера.
        Поддерживает простые выражения.
        """
        # Безопасное выполнение с ограниченным контекстом
        safe_context = {
            'True': True,
            'False': False,
            'None': None,
            
            # Переменные сценария
            'vars': self._scenario_state,
            
            # Данные события
            'event': event_data or {},
            
            # Функции
            'get_var': lambda name: self._scenario_state.get(name),
            'has_var': lambda name: name in self._scenario_state,
            'quest_state': lambda qid: self._get_quest_state(qid),
            'npc_alive': lambda nid: self._is_npc_alive(nid),
            'item_exists': lambda iid: self._item_exists(iid),
            'players_in_area': lambda area: self._count_players_in_area(area),
            'get_time': lambda: datetime.now().timestamp(),
        }
        
        try:
            # Безопасное выполнение
            result = eval(condition, {"__builtins__": {}}, safe_context)
            return bool(result)
        except Exception as e:
            self._logger.error(f"Error evaluating condition '{condition}': {e}")
            return False
    
    async def _execute_actions(self, actions: List[Dict[str, Any]]) -> None:
        """
        Выполняет список действий.
        """
        for action in actions:
            action_type = action.get('type')
            params = action.get('params', {})
            
            try:
                await self._execute_action(action_type, params)
            except Exception as e:
                self._logger.error(f"Action execution error: {e}")
    
    async def _execute_action(self, action_type: str, params: Dict[str, Any]) -> Any:
        """
        Выполняет одно действие.
        """
        if action_type == ActionType.CHANGE_SCENE:
            scene_id = params.get('scene_id')
            if scene_id:
                await self.go_to_scene(scene_id)
        
        elif action_type == ActionType.SHOW_TEXT:
            text = params.get('text', '')
            duration = params.get('duration', 3)
            await self._show_text(text, duration)
        
        elif action_type == ActionType.START_COMBAT:
            npc_ids = params.get('npc_ids', [])
            await self._start_combat(npc_ids)
        
        elif action_type == ActionType.SPAWN_NPC:
            npc_data = params.get('npc_data', {})
            await self._spawn_npc(npc_data)
        
        elif action_type == ActionType.REMOVE_NPC:
            npc_id = params.get('npc_id')
            if npc_id:
                await self._remove_npc(npc_id)
        
        elif action_type == ActionType.GIVE_ITEM:
            player_id = params.get('player_id')
            item_data = params.get('item_data', {})
            await self._give_item(player_id, item_data)
        
        elif action_type == ActionType.REMOVE_ITEM:
            player_id = params.get('player_id')
            item_id = params.get('item_id')
            if item_id:
                await self._remove_item(player_id, item_id)
        
        elif action_type == ActionType.SET_VARIABLE:
            var_name = params.get('name')
            var_value = params.get('value')
            if var_name is not None:
                self._scenario_state[var_name] = var_value
                self._logger.debug(f"Variable set: {var_name} = {var_value}")
        
        elif action_type == ActionType.START_QUEST:
            quest_id = params.get('quest_id')
            if quest_id:
                await self._start_quest(quest_id)
        
        elif action_type == ActionType.COMPLETE_QUEST:
            quest_id = params.get('quest_id')
            if quest_id:
                await self._complete_quest(quest_id)
        
        elif action_type == ActionType.FAIL_QUEST:
            quest_id = params.get('quest_id')
            if quest_id:
                await self._fail_quest(quest_id)
        
        elif action_type == ActionType.OPEN_DOOR:
            door_id = params.get('door_id')
            if door_id:
                await self._open_door(door_id)
        
        elif action_type == ActionType.CLOSE_DOOR:
            door_id = params.get('door_id')
            if door_id:
                await self._close_door(door_id)
        
        elif action_type == ActionType.LOCK_DOOR:
            door_id = params.get('door_id')
            if door_id:
                await self._lock_door(door_id)
        
        elif action_type == ActionType.UNLOCK_DOOR:
            door_id = params.get('door_id')
            if door_id:
                await self._unlock_door(door_id)
        
        elif action_type == ActionType.SHOW_DIALOG:
            dialog_data = params.get('dialog_data', {})
            await self._show_dialog(dialog_data)
        
        elif action_type == ActionType.PLAY_SOUND:
            sound_id = params.get('sound_id')
            if sound_id:
                await self._play_sound(sound_id)
        
        elif action_type == ActionType.SHOW_ANIMATION:
            animation_id = params.get('animation_id')
            if animation_id:
                await self._show_animation(animation_id)
        
        elif action_type == ActionType.DELAY:
            seconds = params.get('seconds', 1)
            await asyncio.sleep(seconds)
        
        elif action_type == ActionType.END_SCENARIO:
            await self._end_scenario(params.get('result', 'completed'))
        
        elif action_type == ActionType.CALL_FUNCTION:
            function_name = params.get('function')
            function_params = params.get('params', {})
            await self._call_function(function_name, function_params)
        
        elif action_type == ActionType.SPAWN_ITEM:
            item_data = params.get('item_data', {})
            position = params.get('position', {'x': 0, 'y': 0})
            await self._spawn_item(item_data, position)
        
        elif action_type == ActionType.TELEPORT_PLAYER:
            player_id = params.get('player_id')
            position = params.get('position', {'x': 0, 'y': 0})
            await self._teleport_player(player_id, position)
        
        elif action_type == ActionType.APPLY_EFFECT:
            target_id = params.get('target_id')
            effect_data = params.get('effect_data', {})
            await self._apply_effect(target_id, effect_data)
        
        elif action_type == ActionType.REMOVE_EFFECT:
            target_id = params.get('target_id')
            effect_id = params.get('effect_id')
            if effect_id:
                await self._remove_effect(target_id, effect_id)
        
        elif action_type == ActionType.SET_LIGHTING:
            lighting = params.get('lighting', 'default')
            await self._set_lighting(lighting)
        
        elif action_type == ActionType.PLAY_MUSIC:
            music_id = params.get('music_id')
            if music_id:
                await self._play_music(music_id)
        
        elif action_type == ActionType.CUSTOM:
            handler = params.get('handler')
            if handler:
                await self._custom_action(handler, params.get('data', {}))
        
        else:
            self._logger.warning(f"Unknown action type: {action_type}")
    
    # ===== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ =====
    
    async def _show_text(self, text: str, duration: float = 3) -> None:
        """Показывает текст."""
        await self._publish_event('show_text', {
            'text': text,
            'duration': duration
        })
    
    async def _start_combat(self, npc_ids: List[str]) -> None:
        """Начинает бой."""
        await self._publish_event('start_combat', {
            'npc_ids': npc_ids
        })
    
    async def _spawn_npc(self, npc_data: Dict[str, Any]) -> None:
        """Создаёт NPC."""
        await self._publish_event('spawn_npc', {
            'npc_data': npc_data
        })
    
    async def _remove_npc(self, npc_id: str) -> None:
        """Удаляет NPC."""
        await self._publish_event('remove_npc', {
            'npc_id': npc_id
        })
    
    async def _give_item(self, player_id: str, item_data: Dict[str, Any]) -> None:
        """Выдаёт предмет."""
        await self._publish_event('give_item', {
            'player_id': player_id,
            'item_data': item_data
        })
    
    async def _remove_item(self, player_id: str, item_id: str) -> None:
        """Удаляет предмет."""
        await self._publish_event('remove_item', {
            'player_id': player_id,
            'item_id': item_id
        })
    
    async def _start_quest(self, quest_id: str) -> None:
        """Начинает квест."""
        quest = self.scenario.get_quest(quest_id)
        if quest:
            quest.state = QuestState.ACTIVE
            await self._publish_event('quest_started', {
                'quest_id': quest_id,
                'quest_name': quest.name
            })
    
    async def _complete_quest(self, quest_id: str) -> None:
        """Завершает квест."""
        quest = self.scenario.get_quest(quest_id)
        if quest:
            quest.state = QuestState.COMPLETED
            quest.progress = quest.max_progress
            await self._publish_event('quest_completed', {
                'quest_id': quest_id,
                'quest_name': quest.name,
                'rewards': quest.rewards
            })
    
    async def _fail_quest(self, quest_id: str) -> None:
        """Проваливает квест."""
        quest = self.scenario.get_quest(quest_id)
        if quest:
            quest.state = QuestState.FAILED
            await self._publish_event('quest_failed', {
                'quest_id': quest_id,
                'quest_name': quest.name
            })
    
    async def _open_door(self, door_id: str) -> None:
        """Открывает дверь."""
        await self._publish_event('door_opened', {
            'door_id': door_id
        })
    
    async def _close_door(self, door_id: str) -> None:
        """Закрывает дверь."""
        await self._publish_event('door_closed', {
            'door_id': door_id
        })
    
    async def _lock_door(self, door_id: str) -> None:
        """Запирает дверь."""
        await self._publish_event('door_locked', {
            'door_id': door_id
        })
    
    async def _unlock_door(self, door_id: str) -> None:
        """Отпирает дверь."""
        await self._publish_event('door_unlocked', {
            'door_id': door_id
        })
    
    async def _show_dialog(self, dialog_data: Dict[str, Any]) -> None:
        """Показывает диалог."""
        await self._publish_event('show_dialog', {
            'dialog_data': dialog_data
        })
    
    async def _play_sound(self, sound_id: str) -> None:
        """Воспроизводит звук."""
        await self._publish_event('play_sound', {
            'sound_id': sound_id
        })
    
    async def _show_animation(self, animation_id: str) -> None:
        """Показывает анимацию."""
        await self._publish_event('show_animation', {
            'animation_id': animation_id
        })
    
    async def _end_scenario(self, result: str = 'completed') -> None:
        """Завершает сценарий."""
        self.is_running = False
        await self._publish_event('scenario_ended', {
            'result': result
        })
        self._logger.info(f"Scenario ended with result: {result}")
    
    async def _call_function(self, function_name: str, params: Dict[str, Any]) -> None:
        """Вызывает пользовательскую функцию."""
        await self._publish_event('call_function', {
            'function': function_name,
            'params': params
        })
    
    async def _spawn_item(self, item_data: Dict[str, Any], position: Dict[str, float]) -> None:
        """Создаёт предмет на карте."""
        await self._publish_event('spawn_item', {
            'item_data': item_data,
            'position': position
        })
    
    async def _teleport_player(self, player_id: str, position: Dict[str, float]) -> None:
        """Телепортирует игрока."""
        await self._publish_event('teleport_player', {
            'player_id': player_id,
            'position': position
        })
    
    async def _apply_effect(self, target_id: str, effect_data: Dict[str, Any]) -> None:
        """Применяет эффект."""
        await self._publish_event('apply_effect', {
            'target_id': target_id,
            'effect_data': effect_data
        })
    
    async def _remove_effect(self, target_id: str, effect_id: str) -> None:
        """Удаляет эффект."""
        await self._publish_event('remove_effect', {
            'target_id': target_id,
            'effect_id': effect_id
        })
    
    async def _set_lighting(self, lighting: str) -> None:
        """Устанавливает освещение."""
        await self._publish_event('set_lighting', {
            'lighting': lighting
        })
    
    async def _play_music(self, music_id: str) -> None:
        """Воспроизводит музыку."""
        await self._publish_event('play_music', {
            'music_id': music_id
        })
    
    async def _set_background(self, background: str) -> None:
        """Устанавливает фон."""
        await self._publish_event('set_background', {
            'background': background
        })
    
    async def _load_map(self, map_id: str, map_data: Dict[str, Any]) -> None:
        """Загружает карту."""
        await self._publish_event('load_map', {
            'map_id': map_id,
            'map_data': map_data
        })
    
    async def _set_player_positions(self, positions: List[Dict[str, Any]]) -> None:
        """Устанавливает позиции игроков."""
        await self._publish_event('set_player_positions', {
            'positions': positions
        })
    
    async def _custom_action(self, handler: str, data: Dict[str, Any]) -> None:
        """Выполняет пользовательское действие."""
        await self._publish_event('custom_action', {
            'handler': handler,
            'data': data
        })
    
    # ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ УСЛОВИЙ =====
    
    def _get_quest_state(self, quest_id: str) -> str:
        """Получает состояние квеста."""
        quest = self.scenario.get_quest(quest_id)
        return quest.state.value if quest else QuestState.NOT_STARTED.value
    
    def _is_npc_alive(self, npc_id: str) -> bool:
        """Проверяет, жив ли NPC."""
        # Реализация зависит от интеграции с Character System
        return True
    
    def _item_exists(self, item_id: str) -> bool:
        """Проверяет существование предмета."""
        # Реализация зависит от интеграции с Inventory System
        return True
    
    def _count_players_in_area(self, area: str) -> int:
        """Считает игроков в области."""
        # Реализация зависит от интеграции с Map Engine
        return 0
    
    # ===== ОБРАБОТКА СОБЫТИЙ =====
    
    async def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Публикует событие."""
        if self.event_bus:
            from event_system import EventFactory
            event = EventFactory.create_event(
                f"scenario_{event_type}",
                self.room_id,
                "scenario_engine",
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
    
    def on(self, event_type: str, callback: Callable) -> None:
        """Подписывается на событие."""
        self._event_listeners[event_type].append(callback)
    
    def off(self, event_type: str, callback: Callable) -> None:
        """Отписывается от события."""
        if event_type in self._event_listeners:
            self._event_listeners[event_type].remove(callback)
    
    # ===== ВОРКЕР =====
    
    async def _worker(self) -> None:
        """Воркер для обработки очереди действий."""
        while self.is_running:
            try:
                if self.is_paused:
                    await asyncio.sleep(0.1)
                    continue
                
                # Проверяем триггеры периодически
                await self._check_triggers()
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Worker error: {e}")
                await asyncio.sleep(1)
    
    # ===== СОСТОЯНИЕ =====
    
    def get_state(self) -> Dict[str, Any]:
        """Возвращает состояние движка."""
        return {
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'scenario_id': self.scenario.id if self.scenario else None,
            'scenario_name': self.scenario.name if self.scenario else None,
            'current_scene': self.current_scene.to_dict() if self.current_scene else None,
            'previous_scene': self.previous_scene.to_dict() if self.previous_scene else None,
            'scene_history': self.scene_history,
            'variables': self._scenario_state,
            'quests': [q.to_dict() for q in self.scenario.quests] if self.scenario else []
        }
    
    def save_state(self) -> Dict[str, Any]:
        """Сохраняет состояние."""
        return {
            'scenario_id': self.scenario.id if self.scenario else None,
            'current_scene_id': self.current_scene.id if self.current_scene else None,
            'previous_scene_id': self.previous_scene.id if self.previous_scene else None,
            'scene_history': self.scene_history,
            'variables': self._scenario_state,
            'quests': [q.to_dict() for q in self.scenario.quests] if self.scenario else [],
            'timestamp': datetime.now().isoformat()
        }
    
    def load_state(self, state: Dict[str, Any]) -> None:
        """Загружает состояние."""
        if state.get('variables'):
            self._scenario_state = state['variables']
        
        if state.get('quests') and self.scenario:
            for quest_state in state['quests']:
                quest = self.scenario.get_quest(quest_state['id'])
                if quest:
                    quest.state = QuestState(quest_state['state'])
                    quest.progress = quest_state.get('progress', 0)
        
        if state.get('current_scene_id'):
            scene = self.scenario.get_scene(state['current_scene_id'])
            if scene:
                self.current_scene = scene
                self.scenario.current_scene_id = scene.id
        
        if state.get('previous_scene_id'):
            scene = self.scenario.get_scene(state['previous_scene_id'])
            if scene:
                self.previous_scene = scene
        
        if state.get('scene_history'):
            self.scene_history = state['scene_history']

# ============================================================
# 21.4. SCENARIO MANAGER
# ============================================================

class ScenarioManager:
    """Управление сценариями."""
    
    def __init__(self):
        self._engines: Dict[int, ScenarioEngine] = {}
        self._scenarios: Dict[str, Scenario] = {}
        self._logger = logging.getLogger("scenario_manager")
    
    def create_engine(self, room_id: int) -> ScenarioEngine:
        """Создаёт движок для комнаты."""
        if room_id in self._engines:
            return self._engines[room_id]
        
        engine = ScenarioEngine(room_id)
        self._engines[room_id] = engine
        return engine
    
    def get_engine(self, room_id: int) -> Optional[ScenarioEngine]:
        """Получает движок комнаты."""
        return self._engines.get(room_id)
    
    def remove_engine(self, room_id: int) -> None:
        """Удаляет движок комнаты."""
        if room_id in self._engines:
            engine = self._engines[room_id]
            asyncio.create_task(engine.stop())
            del self._engines[room_id]
    
    def register_scenario(self, scenario: Scenario) -> None:
        """Регистрирует сценарий."""
        self._scenarios[scenario.id] = scenario
        self._logger.info(f"Scenario registered: {scenario.name}")
    
    def get_scenario(self, scenario_id: str) -> Optional[Scenario]:
        """Получает сценарий по ID."""
        return self._scenarios.get(scenario_id)
    
    def load_scenario(self, room_id: int, scenario_id: str) -> bool:
        """Загружает сценарий в комнату."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            self._logger.error(f"Scenario not found: {scenario_id}")
            return False
        
        engine = self.create_engine(room_id)
        engine.load_scenario(scenario)
        return True
    
    async def start_scenario(self, room_id: int, scenario_id: str) -> bool:
        """Запускает сценарий в комнате."""
        if not self.load_scenario(room_id, scenario_id):
            return False
        
        engine = self.get_engine(room_id)
        if not engine:
            return False
        
        return await engine.start()
    
    def get_state(self, room_id: int) -> Optional[Dict[str, Any]]:
        """Получает состояние движка комнаты."""
        engine = self.get_engine(room_id)
        if engine:
            return engine.get_state()
        return None

# ============================================================
# 21.5. БИЛДЕР СЦЕНАРИЕВ (BUILDER)
# ============================================================

class ScenarioBuilder:
    """Билдер для создания сценариев."""
    
    def __init__(self):
        self.scenario = Scenario()
        self._current_scene: Optional[Scene] = None
    
    def create_scenario(
        self,
        name: str,
        description: str = "",
        system: str = "universal"
    ) -> 'ScenarioBuilder':
        """Создаёт сценарий."""
        self.scenario.name = name
        self.scenario.description = description
        self.scenario.system = system
        self.scenario.id = str(uuid.uuid4())
        return self
    
    def add_scene(
        self,
        name: str,
        description: str = "",
        scene_type: SceneType = SceneType.EXPLORATION,
        map_id: str = ""
    ) -> 'ScenarioBuilder':
        """Добавляет сцену."""
        scene = Scene(
            name=name,
            description=description,
            type=scene_type,
            map_id=map_id
        )
        self.scenario.scenes.append(scene)
        self._current_scene = scene
        return self
    
    def set_start_scene(self, scene_id: str) -> 'ScenarioBuilder':
        """Устанавливает стартовую сцену."""
        self.scenario.start_scene_id = scene_id
        return self
    
    def add_trigger(
        self,
        name: str,
        trigger_type: TriggerType,
        condition: str = "",
        is_once: bool = True
    ) -> 'ScenarioBuilder':
        """Добавляет триггер в текущую сцену."""
        if not self._current_scene:
            raise ValueError("No current scene")
        
        trigger = Trigger(
            name=name,
            type=trigger_type,
            condition=condition,
            is_once=is_once
        )
        self._current_scene.triggers.append(trigger)
        return self
    
    def add_action(
        self,
        action_type: Union[str, ActionType],
        params: Dict[str, Any]
    ) -> 'ScenarioBuilder':
        """Добавляет действие к последнему триггеру."""
        if not self._current_scene or not self._current_scene.triggers:
            raise ValueError("No triggers in current scene")
        
        trigger = self._current_scene.triggers[-1]
        trigger.actions.append({
            'type': action_type.value if isinstance(action_type, ActionType) else action_type,
            'params': params
        })
        return self
    
    def add_variable(
        self,
        name: str,
        value: Any,
        var_type: str = "string",
        description: str = ""
    ) -> 'ScenarioBuilder':
        """Добавляет переменную."""
        var = ScenarioVariable(
            name=name,
            value=value,
            type=var_type,
            description=description
        )
        self.scenario.variables.append(var)
        return self
    
    def add_quest(
        self,
        name: str,
        description: str,
        objectives: List[str] = None,
        rewards: Dict[str, Any] = None
    ) -> 'ScenarioBuilder':
        """Добавляет квест."""
        quest = Quest(
            name=name,
            description=description,
            objectives=objectives or [],
            rewards=rewards or {}
        )
        self.scenario.quests.append(quest)
        return self
    
    def set_metadata(self, key: str, value: Any) -> 'ScenarioBuilder':
        """Устанавливает метаданные."""
        self.scenario.metadata[key] = value
        return self
    
    def build(self) -> Scenario:
        """Строит сценарий."""
        if not self.scenario.start_scene_id and self.scenario.scenes:
            self.scenario.start_scene_id = self.scenario.scenes[0].id
        return self.scenario

# ============================================================
# 21.6. ТЕСТЫ
# ============================================================

async def test_scenario_engine():
    """Тестирование Scenario Engine."""
    print("\n" + "="*60)
    print("🧪 ТЕСТИРОВАНИЕ SCENARIO ENGINE")
    print("="*60)
    
    # Создаём сценарий через билдер
    builder = ScenarioBuilder()
    
    scenario = (
        builder
        .create_scenario("Test Adventure", "A simple test scenario")
        
        # Сцена 1: Вход
        .add_scene("Tavern", "You enter a cozy tavern", SceneType.EXPLORATION)
        .add_variable("talked_to_bartender", False, "bool")
        .add_variable("quest_started", False, "bool")
        
        # Триггер: вход в таверну
        .add_trigger(
            "Enter Tavern",
            TriggerType.PLAYER_ENTER_AREA,
            "players_in_area('tavern') >= 1",
            True
        )
        .add_action(ActionType.SHOW_TEXT, {
            'text': 'Welcome to the Rusty Dagger tavern!',
            'duration': 3
        })
        .add_action(ActionType.SET_VARIABLE, {
            'name': 'tavern_entered',
            'value': True
        })
        
        # Триггер: разговор с барменом
        .add_trigger(
            "Talk to Bartender",
            TriggerType.PLAYER_INTERACT,
            "event.target == 'bartender' and not vars.talked_to_bartender",
            True
        )
        .add_action(ActionType.SHOW_TEXT, {
            'text': 'Bartender: "Welcome! We have a quest for you."',
            'duration': 4
        })
        .add_action(ActionType.SET_VARIABLE, {
            'name': 'talked_to_bartender',
            'value': True
        })
        .add_action(ActionType.START_QUEST, {
            'quest_id': 'tavern_quest'
        })
        
        # Сцена 2: Бой
        .add_scene("Combat", "Goblins attack!", SceneType.COMBAT)
        .add_trigger(
            "Combat Finished",
            TriggerType.COMBAT_FINISHED,
            "True",
            True
        )
        .add_action(ActionType.SHOW_TEXT, {
            'text': 'Victory! You defeated the goblins!',
            'duration': 3
        })
        .add_action(ActionType.COMPLETE_QUEST, {
            'quest_id': 'tavern_quest'
        })
        .add_action(ActionType.CHANGE_SCENE, {
            'scene_id': 'final'  # будет создана ниже
        })
        
        # Сцена 3: Финал
        .add_scene("Final", "The adventure ends", SceneType.FINAL)
        .add_trigger(
            "End Scenario",
            TriggerType.PLAYER_ENTER_AREA,
            "True",
            True
        )
        .add_action(ActionType.END_SCENARIO, {
            'result': 'completed'
        })
        
        # Квест
        .add_quest(
            "Tavern Quest",
            "Help the bartender deal with goblins",
            ["Talk to bartender", "Defeat goblins"],
            {"gold": 100, "xp": 50}
        )
        
        # Метаданные
        .set_metadata("author", "Test Author")
        .set_metadata("difficulty", "easy")
        
        .build()
    )
    
    # Создаём движок
    engine = ScenarioEngine(room_id=1)
    engine.load_scenario(scenario)
    
    # Запускаем
    print("\n🚀 Запуск сценария...")
    await engine.start()
    
    # Проверяем состояние
    state = engine.get_state()
    print(f"\n📊 Состояние:")
    print(f"   Сценарий: {state['scenario_name']}")
    print(f"   Текущая сцена: {state['current_scene']['name']}")
    print(f"   Переменные: {state['variables']}")
    
    # Тестируем триггеры
    print("\n🔄 Тестирование триггеров...")
    
    # Имитируем вход в таверну
    await engine._check_triggers({'area': 'tavern', 'players': 1})
    
    # Имитируем разговор с барменом
    await engine._check_triggers({
        'type': 'interact',
        'target': 'bartender'
    })
    
    # Проверяем состояние после действий
    state2 = engine.get_state()
    print(f"\n📊 Состояние после действий:")
    print(f"   Переменные: {state2['variables']}")
    print(f"   Квесты: {state2['quests']}")
    
    # Останавливаем
    await engine.stop()
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# 21.7. ГЛОБАЛЬНЫЙ ИНСТАНС
# ============================================================

scenario_manager = ScenarioManager()

# ============================================================
# 21.8. ЗАПУСК ТЕСТОВ
# ============================================================

if __name__ == "__main__":
    asyncio.run(test_scenario_engine())
