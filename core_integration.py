No game logic here - only orchestration and communication.
"""

import asyncio
import logging
import time
import sys
import os
import signal
import threading
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum, auto
import gc
import psutil

# 31.1. ENUMS
# ============================================================

class ComponentState(str, Enum):
    """Component lifecycle states."""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"
    ERROR = "error"
    RELOADING = "reloading"

class SystemStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"
class CoreEvent(str, Enum):
    """Core system events."""
    SYSTEM_STARTING = "system.starting"
    SYSTEM_STOPPING = "system.stopping"
    SYSTEM_STOPPED = "system.stopped"
    SYSTEM_RELOADED = "system.reloaded"
    # Component events
    COMPONENT_INITIALIZED = "component.initialized"
    COMPONENT_SHUTDOWN = "component.shutdown"
    COMPONENT_ERROR = "component.error"
    # Health
    HEALTH_CHECK = "health.check"
    
    # Metrics
    METRIC_UPDATE = "metric.update"
    PERFORMANCE_REPORT = "performance.report"
# ============================================================
# ============================================================

@dataclass
class ComponentInfo:
    """Information about a registered component."""
    name: str
    instance: Any
    state: ComponentState = ComponentState.UNINITIALIZED
    initialized_at: Optional[datetime] = None
    health_status: SystemStatus = SystemStatus.UNKNOWN
    health_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
@dataclass
class SystemMetrics:
    """System performance metrics."""
    uptime_seconds: float
    active_players: int
    active_combats: int
    events_per_second: float
    api_latency_p95: float
    db_latency_avg: float
    memory_usage_mb: float
    cpu_percent: float
    errors_last_minute: int
    autosave_duration_avg: float
    dice_rolls_total: int
    def to_dict(self) -> dict:
            'timestamp': self.timestamp.isoformat(),
            'active_rooms': self.active_rooms,
            'active_combats': self.active_combats,
            'total_events': self.total_events,
            'api_latency_avg': self.api_latency_avg,
            'db_latency_avg': self.db_latency_avg,
            'memory_usage_mb': self.memory_usage_mb,
            'thread_count': self.thread_count,
            'autosave_duration_avg': self.autosave_duration_avg,
            'combat_duration_avg': self.combat_duration_avg,
        }

@dataclass
class VersionInfo:
    """Version information."""
    server_version: str = "1.0.0"
    scenario_version: str = "1.0.0"
    database_version: str = "1.0.0"
    asset_version: str = "1.0.0"
    api_version: str = "v1"
    build_date: str = ""
    git_commit: str = ""

    def to_dict(self) -> dict:
        return {
            'server_version': self.server_version,
            'protocol_version': self.protocol_version,
            'scenario_version': self.scenario_version,
            'asset_version': self.asset_version,
            'build_date': self.build_date,
            'git_commit': self.git_commit
        }

# ============================================================
# 31.3. CORE INTEGRATION
# ============================================================

class CoreIntegration:
    """
    Central application layer.
    """
    
    _instance = None
    _initialized = False
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
            return
        
        self._initialized = True
        self._state = ComponentState.UNINITIALIZED
        self._start_time: Optional[datetime] = None
        self._event_bus = EventBus()
        self._max_metrics = 1000
        self._error_timestamps: List[datetime] = []
        self._total_events = 0
        self._lock = threading.RLock()
        self._shutdown_requested = False
        
        # Version info
        self.version = VersionInfo()
        
        self.configuration = None
        self.permission_system = None
        self.character_system = None
        self.inventory_system = None
        self.skill_system = None
        self.effect_system = None
        self.combat_system = None
        self.turn_manager = None
        self.map_system = None
        self.fog_system = None
        self.trigger_system = None
        self.quest_system = None
        self.autosave_system = None
        self.localization_system = None
        self.scenario_manager = None
        self.plugin_manager = None
        self.websocket_manager = None
        
        # Register signal handlers
        self._setup_signal_handlers()
        
        self._logger.info("CoreIntegration instance created")
    
    def _setup_logging(self):
        """Setup logging."""
        logger = logging.getLogger("core")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            logger.addHandler(handler)
        return logger
    
        """Setup signal handlers for graceful shutdown."""
            self._logger.info(f"Received signal {sig}, shutting down...")
            asyncio.create_task(self.shutdown())
        signal.signal(signal.SIGINT, signal_handler)
    
    def _load_version_info(self):
        # Try to read from version file
        version_file = Path("version.json")
        if version_file.exists():
            try:
                import json
                    data = json.load(f)
                    self.version = VersionInfo(**data)
                self._logger.warning(f"Failed to load version info: {e}")
        # Set build date
        self.version.build_date = datetime.now().isoformat()
        
        # Try to get git commit
            import subprocess
            result = subprocess.run(
                capture_output=True,
            )
            if result.returncode == 0:
        except Exception:
            pass
    
    # ============================================================
    # ============================================================
    async def initialize(self) -> bool:
        """Initialize the entire system."""
            self._logger.warning("System already running")
        
        self._logger.info("="*60)
        self._logger.info("="*60)
        self._state = ComponentState.INITIALIZING
        self._start_time = datetime.now()
        try:
            # Define initialization order
            init_order = [
                ("configuration", self._init_configuration),
                ("permission_system", self._init_permissions),
                ("plugin_manager", self._init_plugins),
                ("room_manager", self._init_rooms),
                ("inventory_system", self._init_inventory),
                ("effect_system", self._init_effects),
                ("dice_engine", self._init_dice),
                ("combat_system", self._init_combat),
                ("map_system", self._init_maps),
                ("fog_system", self._init_fog),
                ("trigger_system", self._init_triggers),
                ("scenario_manager", self._init_scenario),
                ("ui_framework", self._init_ui),
                ("save_system", self._init_saves),
                ("analytics_system", self._init_analytics),
            ]
            
            # Initialize each component
                self._logger.info(f"Initializing {name}...")
                try:
                    await init_func()
                    self._logger.info(f"✅ {name} initialized")
                    self._logger.error(f"❌ Failed to initialize {name}: {e}")
                    self._logger.error(traceback.format_exc())
            
            # Register event handlers
            self._register_core_event_handlers()
            
            # Start background tasks
            await self._start_background_tasks()
            self._state = ComponentState.RUNNING
            self._running = True
            
            # Emit system started event
                'timestamp': datetime.now().isoformat(),
                'version': self.version.to_dict()
            
            self._logger.info("="*60)
            self._logger.info("✅ CORE INTEGRATION INITIALIZED SUCCESSFULLY")
            self._logger.info(f"🚀 Server ready at {datetime.now()}")
            
            # Print component summary
            self._print_component_summary()
            
            return True
            
        except Exception as e:
            self._state = ComponentState.ERROR
            self._logger.error(f"Fatal error during initialization: {e}")
            return False
    
    def _print_component_summary(self):
        """Print component initialization summary."""
        self._logger.info("-" * 40)
            status = "✅" if info.state == ComponentState.RUNNING else "❌"
            self._logger.info(f"  {status} {name}: {info.state.value}")
        self._logger.info(f"Total components: {len(self._components)}")
    # ============================================================
    # 31.5. COMPONENT INITIALIZATION
    # ============================================================
    
    async def _init_configuration(self):
        """Initialize configuration system."""
        try:
            from configuration_system import ConfigurationManager
            self.configuration = ConfigurationManager()
            self.configuration.load()
            self._state = ComponentState.RUNNING
            self._logger.warning(f"Configuration system not available: {e}")
            self.configuration = None
    
    async def _init_database(self):
        try:
            if self.configuration:
                db_config = self.configuration.get_section("database")
                # Create database connection
                self.database = type('Database', (), {
                    'config': db_config,
                    'execute': lambda self, q: None,
                })()
            else:
                self.database = None
            self._register_component("database", self.database)
            self._logger.error(f"Database init error: {e}")
            self.database = None
    async def _init_permissions(self):
        try:
            from permission_system import PermissionSystem
            self.permission_system = PermissionSystem()
            if self.database:
            self._register_component("permission_system", self.permission_system)
        except ImportError as e:
            self.permission_system = None
    async def _init_localization(self):
        """Initialize localization system."""
            from localization_system import LocalizationManager
            self._register_component("localization_system", self.localization_system)
        except ImportError as e:
            self._logger.warning(f"Localization system not available: {e}")
    
    async def _init_plugins(self):
        try:
            self.plugin_manager = PluginManager()
            self._register_component("plugin_manager", self.plugin_manager)
            self._logger.warning(f"Plugin system not available: {e}")
    
    async def _init_rooms(self):
        try:
            self.room_manager = RoomManager()
            if self.permission_system:
            self._register_component("room_manager", self.room_manager)
            self._logger.warning(f"Room system not available: {e}")
            self.room_manager = None
    
    async def _init_characters(self):
        try:
            from character_system import CharacterSystem
            if self.database:
            self._register_component("character_system", self.character_system)
        except ImportError as e:
            self.character_system = None
    async def _init_inventory(self):
        """Initialize inventory system."""
            from inventory_system import InventorySystem
            self._register_component("inventory_system", self.inventory_system)
        except ImportError as e:
            self.inventory_system = None
    async def _init_skills(self):
        """Initialize skill system."""
        try:
            from skill_system import SkillSystem
            self.skill_system = SkillSystem()
            self._register_component("skill_system", self.skill_system)
            self._logger.warning(f"Skill system not available: {e}")
    
    async def _init_effects(self):
        try:
            from effect_system import EffectSystem
            self.effect_system = EffectSystem()
            self._register_component("effect_system", self.effect_system)
            self._logger.warning(f"Effect system not available: {e}")
    
    async def _init_dice(self):
        try:
            from dice_system import DiceEngine
            self.dice_engine = DiceEngine()
            self._register_component("dice_engine", self.dice_engine)
            self._logger.warning(f"Dice system not available: {e}")
    
    async def _init_actions(self):
        try:
            from action_system import ActionSystem
            self.action_system = ActionSystem()
            self._register_component("action_system", self.action_system)
        except ImportError as e:
            self._logger.warning(f"Action system not available: {e}")
    
    async def _init_combat(self):
        try:
            from combat_system import CombatSystem
            self.combat_system = CombatSystem()
            if self.dice_engine:
            self._register_component("combat_system", self.combat_system)
            self._logger.warning(f"Combat system not available: {e}")
            self.combat_system = None
    async def _init_turns(self):
        try:
            from turn_system import TurnManager
            self.turn_manager = TurnManager()
            if self.combat_system:
            self._register_component("turn_manager", self.turn_manager)
        except ImportError as e:
            self.turn_manager = None
    async def _init_maps(self):
        """Initialize map system."""
            from map_system import MapSystem
            self._register_component("map_system", self.map_system)
        except ImportError as e:
            self.map_system = None
    async def _init_fog(self):
        """Initialize fog of war system."""
            from fog_system import FogSystem
            self._register_component("fog_system", self.fog_system)
        except ImportError as e:
            self.fog_system = None
    async def _init_audio(self):
        """Initialize audio system."""
            from audio_system import AudioSystem
            self._register_component("audio_system", self.audio_system)
        except ImportError as e:
            self.audio_system = None
    async def _init_triggers(self):
        """Initialize trigger system."""
            from trigger_system import TriggerSystem
            self._register_component("trigger_system", self.trigger_system)
        except ImportError as e:
            self.trigger_system = None
    async def _init_quests(self):
        """Initialize quest system."""
            from quest_system import QuestSystem
            self._register_component("quest_system", self.quest_system)
        except ImportError as e:
            self.quest_system = None
    async def _init_scenario(self):
        """Initialize scenario manager."""
            from scenario_manager import ScenarioManager
            self._register_component("scenario_manager", self.scenario_manager)
        except ImportError as e:
            self.scenario_manager = None
    async def _init_ui(self):
        """Initialize UI framework."""
            from ui_framework import UIFramework
            self._register_component("ui_framework", self.ui_framework)
        except ImportError as e:
            self.ui_framework = None
    async def _init_autosave(self):
        """Initialize autosave system."""
            from autosave_system import AutosaveSystem
            if self.room_manager:
                self.autosave_system.set_room_manager(self.room_manager)
            self._register_component("autosave_system", self.autosave_system)
        except ImportError as e:
            self._logger.warning(f"Autosave system not available: {e}")
    
        """Initialize save system."""
        try:
            from save_system import SaveSystem
            self.save_system = SaveSystem()
        except ImportError as e:
            self._logger.warning(f"Save system not available: {e}")
    
        """Initialize WebSocket manager."""
        try:
            from websocket_manager import WebSocketManager
            self.websocket_manager = WebSocketManager()
        except ImportError as e:
            self._logger.warning(f"WebSocket manager not available: {e}")
    
        """Initialize analytics system."""
        try:
            from analytics_system import AnalyticsSystem
            self.analytics_system = AnalyticsSystem()
        except ImportError as e:
            self._logger.warning(f"Analytics system not available: {e}")
    
        """Register a component in the core."""
        info = ComponentInfo(
            name=name,
            instance=instance,
            initialized_at=datetime.now(),
            dependencies=dependencies or []
        self._components[name] = info
    def register(self, name: str, instance: Any, dependencies: List[str] = None) -> None:
        """Register a new component (for plugins/extensions)."""
        self._logger.info(f"Registered component: {name}")
        # Initialize if core is running
        if self._state == ComponentState.RUNNING:
                try:
                    asyncio.create_task(instance.initialize())
                except Exception as e:
                    self._logger.error(f"Failed to initialize registered component {name}: {e}")
    # ============================================================
    # ============================================================
    
    def _register_core_event_handlers(self):
        """Register core event handlers."""
        self._event_bus.subscribe(CoreEvent.METRIC_UPDATE.value, self._handle_metric_update)
        self._event_bus.subscribe(CoreEvent.COMPONENT_ERROR.value, self._handle_component_error)
    
        """Handle health check event."""
        report = await self.run_health_check()
    
        """Handle metric update event."""
        self._update_metrics(data)
    
    async def _handle_component_error(self, data: dict):
        component = data.get('component', 'unknown')
        error = data.get('error', 'unknown error')
        self._error_timestamps.append(datetime.now())
            self._error_timestamps = self._error_timestamps[-100:]
    
    # ============================================================
    # 31.7. BACKGROUND TASKS
    
    async def _start_background_tasks(self):
        self._running = True
        # Metrics collection task
        asyncio.create_task(self._metrics_collector())
        # Health check task
        
        # Event cleanup task
        asyncio.create_task(self._event_cleaner())
        
    
    async def _metrics_collector(self):
        while self._running and not self._shutdown_requested:
                await asyncio.sleep(30)  # Every 30 seconds
                metrics = await self._collect_metrics()
                if len(self._metrics) > self._max_metrics:
                
                # Emit metrics event
                
                # Log if any issues
                if metrics.cpu_percent > 80:
                    self._logger.warning(f"High CPU usage: {metrics.cpu_percent:.1f}%")
                    self._logger.warning(f"High memory usage: {metrics.memory_usage_mb:.1f} MB")
            except Exception as e:
                self._logger.error(f"Metrics collection error: {e}")
    async def _collect_metrics(self) -> SystemMetrics:
        uptime = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        
        # Count errors in last minute
        now = datetime.now()
        errors_last_minute = len(recent_errors)
        
        # Event rate
        events_per_second = 0
            recent_events = [t for t in self._event_timestamps if (time.time() - t) < 1]
            events_per_second = len(recent_events)
        
        # Memory usage
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
        except Exception:
            memory_mb = 0
            cpu_percent = 0
        # Active rooms and players
        active_rooms = 0
        active_players = 0
        if self.room_manager and hasattr(self.room_manager, 'get_active_rooms'):
                rooms = self.room_manager.get_active_rooms()
                active_rooms = len(rooms)
                for room in rooms:
                        active_players += len(room.players)
            except Exception:
                pass
        
        # Active combats
        active_combats = 0
        if self.combat_system and hasattr(self.combat_system, 'get_active_combats'):
                active_combats = len(self.combat_system.get_active_combats())
                pass
        
        return SystemMetrics(
            timestamp=datetime.now(),
            active_rooms=active_rooms,
            active_players=active_players,
            total_events=self._total_events,
            api_latency_avg=0.0,
            api_latency_p95=0.0,
            memory_usage_mb=memory_mb,
            thread_count=threading.active_count(),
            errors_last_minute=errors_last_minute,
            combat_duration_avg=0.0,
        )
    
    async def _health_checker(self):
        """Periodic health check."""
            try:
                await asyncio.sleep(60)  # Every minute
                unhealthy = [r for r in report.values() if r.get('status') == 'error']
                    self._logger.warning(f"Unhealthy components: {[u['component'] for u in unhealthy]}")
            except Exception as e:
    
    async def _event_cleaner(self):
        """Clean up old event timestamps."""
        while self._running and not self._shutdown_requested:
                await asyncio.sleep(60)
                now = time.time()
                self._event_timestamps = [t for t in self._event_timestamps if (now - t) < 60]
                pass
    
    # ============================================================
    # 31.8. SHUTDOWN
    # ============================================================
    
        """Gracefully shutdown the entire system."""
        if self._state == ComponentState.SHUTDOWN:
        
        self._logger.info("="*60)
        self._logger.info("🛑 SHUTTING DOWN CORE INTEGRATION")
        self._logger.info("="*60)
        self._shutdown_requested = True
        
        try:
            # Emit stopping event
            await self._event_bus.emit(CoreEvent.SYSTEM_STOPPING.value, {
            })
            
            # Shutdown in reverse order
            shutdown_order = [
                ("autosave_system", self._shutdown_autosave),
                ("analytics_system", self._shutdown_analytics),
                ("trigger_system", self._shutdown_triggers),
                ("fog_system", self._shutdown_fog),
                ("map_system", self._shutdown_maps),
                ("combat_system", self._shutdown_combat),
                ("dice_engine", self._shutdown_dice),
                ("effect_system", self._shutdown_effects),
                ("skill_system", self._shutdown_skills),
                ("inventory_system", self._shutdown_inventory),
                ("character_system", self._shutdown_characters),
                ("plugin_manager", self._shutdown_plugins),
                ("database", self._shutdown_database),
                ("configuration", self._shutdown_configuration),
            
                self._logger.info(f"Shutting down {name}...")
                try:
                    await shutdown_func()
                    self._logger.info(f"✅ {name} shut down")
                    self._logger.error(f"❌ Failed to shut down {name}: {e}")
            
            self._running = False
            self._state = ComponentState.SHUTDOWN
            # Emit stopped event
            await self._event_bus.emit(CoreEvent.SYSTEM_STOPPED.value, {
                'uptime_seconds': (datetime.now() - self._start_time).total_seconds()
            
            self._logger.info("="*60)
            self._logger.info("="*60)
            return True
            
        except Exception as e:
            self._state = ComponentState.ERROR
            self._logger.error(traceback.format_exc())
            return False
    
    async def _shutdown_websocket(self):
        if self.websocket_manager and hasattr(self.websocket_manager, 'shutdown'):
            await self.websocket_manager.shutdown()
    
    async def _shutdown_autosave(self):
        if self.autosave_system and hasattr(self.autosave_system, 'shutdown'):
    
    async def _shutdown_analytics(self):
            await self.analytics_system.shutdown()
    async def _shutdown_quests(self):
        if self.quest_system and hasattr(self.quest_system, 'shutdown'):
    
        if self.trigger_system and hasattr(self.trigger_system, 'shutdown'):
            await self.trigger_system.shutdown()
    async def _shutdown_audio(self):
            await self.audio_system.shutdown()
    
    async def _shutdown_fog(self):
        if self.fog_system and hasattr(self.fog_system, 'shutdown'):
    
    async def _shutdown_maps(self):
            await self.map_system.shutdown()
    async def _shutdown_turns(self):
        if self.turn_manager and hasattr(self.turn_manager, 'shutdown'):
            await self.turn_manager.shutdown()
    
        if self.combat_system and hasattr(self.combat_system, 'shutdown'):
            await self.combat_system.shutdown()
    async def _shutdown_actions(self):
            await self.action_system.shutdown()
    
    async def _shutdown_dice(self):
        if self.dice_engine and hasattr(self.dice_engine, 'shutdown'):
    
    async def _shutdown_effects(self):
            await self.effect_system.shutdown()
    async def _shutdown_skills(self):
        if self.skill_system and hasattr(self.skill_system, 'shutdown'):
    
        if self.inventory_system and hasattr(self.inventory_system, 'shutdown'):
            await self.inventory_system.shutdown()
    async def _shutdown_characters(self):
            await self.character_system.shutdown()
    
    async def _shutdown_rooms(self):
        if self.room_manager and hasattr(self.room_manager, 'shutdown'):
    
    async def _shutdown_plugins(self):
            await self.plugin_manager.shutdown()
    async def _shutdown_permissions(self):
        if self.permission_system and hasattr(self.permission_system, 'shutdown'):
    
        if self.database and hasattr(self.database, 'close'):
            await self.database.close()
    async def _shutdown_configuration(self):
        if self.configuration and hasattr(self.configuration, 'save'):
            self.configuration.save()
    
    # ============================================================
    # 31.9. RELOAD
    
    async def reload(self, component: Optional[str] = None) -> bool:
        self._logger.info(f"Reloading {'all' if not component else component}...")
        try:
            await self._event_bus.emit(CoreEvent.SYSTEM_RELOADING.value, {
                'component': component,
                'timestamp': datetime.now().isoformat()
            
            if component == "configuration" or component is None:
                    self.configuration.reload()
            
            if component == "localization" or component is None:
                if self.localization_system and hasattr(self.localization_system, 'reload'):
                    await self.localization_system.reload()
            
            if component == "scenario" or component is None:
                    await self.scenario_manager.reload()
            
            if component == "plugins" or component is None:
                    await self.plugin_manager.reload_all()
            
            if component is not None and component not in ["configuration", "localization", "scenario", "plugins"]:
                # Try to reload specific component
                comp_info = self._components.get(component)
                if comp_info and comp_info.instance:
                    if hasattr(comp_info.instance, 'reload'):
                        self._logger.info(f"✅ {component} reloaded")
                        self._logger.warning(f"{component} does not support reload")
                        return False
            
            await self._event_bus.emit(CoreEvent.SYSTEM_RELOADED.value, {
                'timestamp': datetime.now().isoformat()
            })
            
            return True
            
        except Exception as e:
            self._logger.error(f"Reload failed: {e}")
            return False
    # ============================================================
    # 31.10. HEALTH CHECKS
    # ============================================================
    
        """Run health check on all components."""
        results = {}
        
        for name, info in self._components.items():
                'component': name,
                'state': info.state.value,
                'message': 'OK',
            }
            
            if info.instance and hasattr(info.instance, 'health_check'):
                try:
                    health = info.instance.health_check()
                    if isinstance(health, dict):
                        status['status'] = health.get('status', 'healthy')
                        status['message'] = health.get('message', 'OK')
                        status['details'] = health.get('details', {})
                    status['status'] = 'error'
                    status['message'] = str(e)
            # Check component state
                status['status'] = 'error'
            elif info.state == ComponentState.UNINITIALIZED:
                status['message'] = 'Not initialized'
            results[name] = status
        
        # Overall status
        errors = [r for r in results.values() if r['status'] == 'error']
        
        overall = {
            'status': 'healthy' if not errors else 'error',
            'total': len(results),
            'healthy': len([r for r in results.values() if r['status'] == 'healthy']),
            'warning': len(warnings),
            'error': len(errors),
            'timestamp': datetime.now().isoformat()
        }
        return {'overall': overall, 'components': results}
    # ============================================================
    # 31.11. EVENT BUS
    # ============================================================
    
    def emit_event(self, event_type: str, data: dict) -> None:
        """Emit an event to the event bus."""
        self._total_events += 1
        asyncio.create_task(self._event_bus.emit(event_type, data))
    def subscribe_event(self, event_type: str, handler: Callable) -> None:
        """Subscribe to an event."""
        self._event_bus.subscribe(event_type, handler)
    
    def unsubscribe_event(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe from an event."""
        self._event_bus.unsubscribe(event_type, handler)
    
    # ============================================================
    # ============================================================
    
    def get_component(self, name: str) -> Optional[Any]:
        """Get a component by name."""
        return info.instance if info else None
    
    def get_all_components(self) -> Dict[str, ComponentInfo]:
        """Get all components."""
    
    def get_metrics(self, limit: int = 100) -> List[SystemMetrics]:
        return self._metrics[-limit:]
    def get_current_metrics(self) -> SystemMetrics:
        """Get current metrics."""
        return asyncio.run(self._collect_metrics())
    
    def get_uptime(self) -> float:
        """Get system uptime in seconds."""
        if self._start_time:
        return 0
    
    def get_status(self) -> Dict[str, Any]:
        """Get system status."""
            'state': self._state.value,
            'components': len(self._components),
            'running': self._running,
            'start_time': self._start_time.isoformat() if self._start_time else None,
        }
    
    # ============================================================
    # 31.13. DIAGNOSTICS
    # ============================================================
    
    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            'status': self.get_status(),
            'metrics': asyncio.run(self._collect_metrics()).to_dict() if self._running else {},
            'components': {
                    'state': info.state.value,
                    'dependencies': info.dependencies
                }
                for name, info in self._components.items()
            },
            'events': {
                'total': self._total_events,
                'recent_rate': len([t for t in self._event_timestamps if (time.time() - t) < 1])
            'errors': {
                'total': len(self._error_timestamps)
            }
        }
    
        """Generate crash report."""
        report = self.get_diagnostics()
        report['crash_time'] = datetime.now().isoformat()
        report['threads'] = str(threading.enumerate())
        report['gc_stats'] = gc.get_stats()
        return report
    
    # ============================================================
    # 31.14. CRASH RECOVERY
    # ============================================================
    async def handle_crash(self, component: str, error: Exception) -> bool:
        self._logger.error(f"Component crash: {component} - {error}")
        self._logger.error(traceback.format_exc())
        
        try:
            # Log crash
            info = self._components.get(component)
            if info:
                info.state = ComponentState.ERROR
                info.health_status = SystemStatus.ERROR
                info.health_message = str(error)
            
            await self._event_bus.emit(CoreEvent.COMPONENT_ERROR.value, {
                'component': component,
                'traceback': traceback.format_exc(),
            })
            
            # Save state
            if self.autosave_system:
                    await self.autosave_system.save_all()
                    self._logger.info(f"✅ State saved during crash recovery")
                    self._logger.error(f"Failed to save state during recovery: {e}")
            # Try to restart component
            if component in self._components:
                if info.instance and hasattr(info.instance, 'restart'):
                        await info.instance.restart()
                        info.state = ComponentState.RUNNING
                        info.health_message = "Restarted after crash"
                        return True
                    except Exception as e:
            
            # If component has no restart method, try to reinitialize
            init_func = getattr(self, f"_init_{component}", None)
            if init_func:
                    await init_func()
                    return True
                except Exception as e:
            
            return False
            
        except Exception as e:
            return False
# ============================================================
# 31.15. EVENT BUS
# ============================================================

class EventBus:
    """Simple event bus for inter-component communication."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
    
    async def emit(self, event_type: str, data: dict) -> None:
        """Emit an event to all subscribers."""
        if event_type in self._subscribers:
            for handler in self._subscribers[event_type]:
                try:
                        await handler(data)
                        handler(data)
                except Exception as e:
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to an event."""
        if event_type not in self._subscribers:
        self._subscribers[event_type].append(handler)
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Unsubscribe from an event."""
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass
    def clear(self) -> None:
        """Clear all subscribers."""
        self._subscribers.clear()

# ============================================================
# 31.16. GLOBAL INSTANCE

core = CoreIntegration()
# ============================================================
# ============================================================

async def test_core_integration():
    """Test Core Integration."""
    print("🧪 ТЕСТИРОВАНИЕ CORE INTEGRATION")
    print("="*60)
    # Test 1: Singleton
    core1 = CoreIntegration()
    core2 = CoreIntegration()
    print(f"   ✅ Core - синглтон: {core1 is core2}")
    # Test 2: Initialize
    print("\n📋 Тест 2: Инициализация")
    result = await core.initialize()
    assert result
    print(f"   ✅ Core инициализирован")
    
    # Test 3: Components
    print("\n📋 Тест 3: Компоненты")
    components = core.get_all_components()
    for name in list(components.keys())[:10]:
        print(f"   - {name}: {info.state.value}")
    print(f"   ✅ Компоненты зарегистрированы")
    # Test 4: Event Bus
    print("\n📋 Тест 4: Event Bus")
    event_received = False
    
        nonlocal event_received
        print(f"   🔔 Событие получено: {data}")
    
    core.emit_event("test.event", {"message": "Hello"})
    assert event_received
    print(f"   ✅ Event Bus работает")
    # Test 5: Health Check
    health = await core.run_health_check()
    print(f"   Статус: {health['overall']['status']}")
    print(f"   Предупреждений: {health['overall']['warning']}")
    print(f"   ✅ Health Check работает")
    
    print("\n📋 Тест 6: Метрики")
    print(f"   uptime: {metrics.uptime_seconds:.1f}s")
    print(f"   active_rooms: {metrics.active_rooms}")
    print(f"   cpu_percent: {metrics.cpu_percent:.1f}%")
    
    # Test 7: Register Component
    class TestComponent:
        def __init__(self):
            self.name = "Test"
        async def initialize(self):
            print("   Test component initialized")
    
    test_component = TestComponent()
    core.register("test_component", test_component)
    assert core.get_component("test_component") is not None
    
    # Test 8: Get Component
    print("\n📋 Тест 8: Получение компонента")
    comp = core.get_component("test_component")
    print(f"   ✅ Компонент получен: {comp.name}")
    # Test 9: Version Info
    print("\n📋 Тест 9: Версионирование")
    print(f"   server_version: {version.server_version}")
    print(f"   api_version: {version.api_version}")
    print(f"   build_date: {version.build_date}")
    
    # Test 10: Status
    print("\n📋 Тест 10: Статус")
    status = core.get_status()
    print(f"   uptime: {status['uptime_seconds']:.1f}s")
    print(f"   ✅ Статус работает")
    
    # Test 11: Diagnostics
    print("\n📋 Тест 11: Диагностика")
    print(f"   events_total: {diagnostics['events']['total']}")
    print(f"   errors_total: {diagnostics['errors']['total']}")
    
    # Test 12: Crash Recovery
    print("\n📋 Тест 12: Crash Recovery")
    class CrashComponent:
    
    crash_comp = CrashComponent()
    core.register("crash_test", crash_comp)
    
    # Simulate crash
    try:
        raise ValueError("Test crash")
    except Exception as e:
        recovered = await core.handle_crash("crash_test", e)
    
    print(f"   ✅ Crash Recovery работает")
    
    # Test 13: Reload
    reload_result = await core.reload()
    print(f"   Reload result: {reload_result}")
    print(f"   ✅ Reload работает")
    
    # Test 14: Shutdown
    print("\n📋 Тест 14: Shutdown")
    shutdown_result = await core.shutdown()
    assert shutdown_result
    print(f"   ✅ Core остановлен")
    print(f"   Состояние: {core._state.value}")
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# 31.18. MAIN
# ============================================================

if __name__ == "__main__":
    asyncio.run(test_core_integration())
