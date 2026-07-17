Universal Plugin System - Fully independent plugin system.
Allows connecting new features without changing the core platform.

import asyncio
import json
import logging
import uuid
import importlib
import inspect
import sys
from datetime import datetime
from enum import Enum, auto
from dataclasses import dataclass, field
import functools
import traceback

# ============================================================
# ============================================================
class PluginState(str, Enum):
    """Plugin states."""
    UNLOADED = "unloaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"
    UPDATING = "updating"

class PluginType(str, Enum):
    """Plugin types."""
    CORE = "core"
    SYSTEM = "system"
    UI = "ui"
    NETWORK = "network"
    IMPORT = "import"
    EXPORT = "export"
    CUSTOM = "custom"

# ============================================================
# ============================================================
@dataclass
class PluginManifest:
    """Plugin manifest."""
    id: str
    name: str
    author: str
    version: str
    description: str
    plugin_type: PluginType
    api_version: str
    dependencies: List[str] = field(default_factory=list)
    optional_dependencies: List[str] = field(default_factory=list)
    entry_point: str = ""
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'author': self.author,
            'description': self.description,
            'api_version': self.api_version,
            'dependencies': self.dependencies,
            'permissions': self.permissions,
            'enabled': self.enabled,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PluginManifest':
            id=data.get('id', str(uuid.uuid4())),
            author=data.get('author', ''),
            version=data.get('version', '1.0.0'),
            plugin_type=PluginType(data.get('plugin_type', 'custom')),
            api_version=data.get('api_version', '1.0'),
            dependencies=data.get('dependencies', []),
            optional_dependencies=data.get('optional_dependencies', []),
            entry_point=data.get('entry_point', ''),
            metadata=data.get('metadata', {})
        )

@dataclass
class PluginContext:
    """Plugin execution context."""
    plugin_id: str
    event_bus: Optional[Any] = None
    action_system: Optional[Any] = None
    config: Dict[str, Any] = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""

@dataclass
class PluginInfo:
    """Plugin runtime information."""
    state: PluginState = PluginState.UNLOADED
    instance: Optional[Any] = None
    enabled_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'manifest': self.manifest.to_dict(),
            'state': self.state.value,
            'enabled_at': self.enabled_at.isoformat() if self.enabled_at else None,
            'error': self.error,
            'metadata': self.metadata
        }

# ============================================================
# 28.3. PLUGIN INTERFACE
# ============================================================

class Plugin:
    """Base plugin interface."""
    
    def __init__(self, context: PluginContext):
        self.context = context
        self._logger = logging.getLogger(f"plugin.{self.__class__.__name__}")
    async def initialize(self) -> bool:
        self._logger.info(f"Initializing {self.__class__.__name__}")
        return True
    
    async def enable(self) -> bool:
        """Enable the plugin."""
        self._logger.info(f"Enabling {self.__class__.__name__}")
        return True
    
    async def disable(self) -> bool:
        self._logger.info(f"Disabling {self.__class__.__name__}")
        return True
    
    async def shutdown(self) -> bool:
        self._logger.info(f"Shutting down {self.__class__.__name__}")
        return True
    def export_state(self) -> Dict[str, Any]:
        return {}
    
    def import_state(self, data: Dict[str, Any]) -> None:
        """Import plugin state from save."""
    
    def get_information(self) -> Dict[str, Any]:
        return {
            'name': self.__class__.__name__,
            'version': '1.0.0',
            'description': 'Base plugin'
    
    def register_commands(self) -> Dict[str, Callable]:
        return {}
    
    def register_event_handlers(self) -> Dict[str, Callable]:
        """Register event handlers."""
    
    def register_permissions(self) -> List[str]:
        return []
    
    def register_ui_panels(self) -> Dict[str, Any]:
        """Register UI panels."""
    
    def register_actions(self) -> Dict[str, Callable]:
        """Register custom actions."""
        return {}
    
    def register_importers(self) -> Dict[str, Callable]:
        return {}
    
    def register_exporters(self) -> Dict[str, Callable]:
        """Register custom exporters."""

# ============================================================
# 28.4. PLUGIN MANAGER
# ============================================================

class PluginManager:
    """
    Universal Plugin Manager.
    """
    
    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self._plugins: Dict[str, PluginInfo] = {}
        self._instances: Dict[str, Plugin] = {}
        self._context: Optional[PluginContext] = None
        
        # External systems
        self.event_bus = None
        self.permission_system = None
        self.save_system = None
        
        # Create plugin directory
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        # Statistics
        self._stats = {
            'total_plugins': 0,
            'loaded_plugins': 0,
            'failed_loads': 0
        }
    
    # ===== SETUP =====
    
    def set_context(self, context: PluginContext) -> None:
        self._context = context
    
    def set_event_bus(self, event_bus) -> None:
        """Set event bus reference."""
        self.event_bus = event_bus
        if self._context:
            self._context.event_bus = event_bus
    def set_permission_system(self, permission_system) -> None:
        self.permission_system = permission_system
        if self._context:
            self._context.permission_system = permission_system
    
    def set_action_system(self, action_system) -> None:
        """Set action system reference."""
        self.action_system = action_system
        if self._context:
            self._context.action_system = action_system
    
    def set_save_system(self, save_system) -> None:
        """Set save system reference."""
        self.save_system = save_system
        if self._context:
            self._context.save_system = save_system
    
    # ===== PLUGIN REGISTRATION =====
    
    def register(
        self,
        manifest: PluginManifest,
    ) -> bool:
        """Register a plugin."""
        if manifest.id in self._plugins:
            self._logger.warning(f"Plugin {manifest.id} already registered")
        
        # Check API version compatibility
        if not self._check_api_version(manifest.api_version):
            self._logger.error(f"API version {manifest.api_version} not supported")
        
        # Check dependencies
        missing = self._check_dependencies(manifest.dependencies)
        if missing:
            self._logger.error(f"Missing dependencies: {missing}")
            return False
        # Check permissions
        if self.permission_system:
                # Register permission
                self.permission_system.register_permission(perm)
        
        # Create plugin info
            manifest=manifest,
        )
        
        self._plugins[manifest.id] = info
        self._stats['total_plugins'] += 1
        # Load plugin
        if manifest.enabled:
        
        self._logger.info(f"Registered plugin: {manifest.name} ({manifest.id})")
        return True
    
    def _load_plugin(self, plugin_id: str, plugin_class: Type[Plugin]) -> bool:
        """Load a plugin instance."""
        if not info:
            return False
        try:
            # Create context if not exists
            if not self._context:
                self._context = PluginContext(
                    event_bus=self.event_bus,
                    action_system=self.action_system,
                    save_system=self.save_system
            
            # Create instance
            instance = plugin_class(self._context)
            self._instances[plugin_id] = instance
            
            # Initialize
            asyncio.create_task(self._initialize_plugin(plugin_id))
            
            info.state = PluginState.LOADED
            info.loaded_at = datetime.now()
            
            self._logger.info(f"Loaded plugin: {plugin_id}")
            
        except Exception as e:
            info.state = PluginState.ERROR
            info.error = str(e)
            self._logger.error(f"Failed to load plugin {plugin_id}: {e}")
            return False
    
    async def _initialize_plugin(self, plugin_id: str) -> None:
        """Initialize plugin asynchronously."""
        instance = self._instances.get(plugin_id)
        if not instance:
            return
        
        try:
            # Initialize
            if await instance.initialize():
                # Register event handlers
                    handlers = instance.register_event_handlers()
                        self.event_bus.subscribe(event_type, handler)
                
                # Register commands
                commands = instance.register_commands()
                    for cmd_name, cmd_func in commands.items():
                        self.action_system.register_command(cmd_name, cmd_func)
                # Register permissions
                if permissions and self.permission_system:
                    for perm in permissions:
                
                # Register actions
                actions = instance.register_actions()
                if actions and self.action_system:
                    for action_name, action_func in actions.items():
                        self.action_system.register_action(action_name, action_func)
                # Enable if needed
                if self._plugins[plugin_id].manifest.enabled:
                    
            self._logger.error(f"Error initializing plugin {plugin_id}: {e}")
    
    def unregister(self, plugin_id: str) -> bool:
        """Unregister a plugin."""
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        
        try:
            if info.instance:
                asyncio.create_task(self._shutdown_plugin(plugin_id))
            # Remove from registry
            if plugin_id in self._instances:
                del self._instances[plugin_id]
            
            self._stats['loaded_plugins'] -= 1
            self._stats['total_plugins'] -= 1
            del self._plugins[plugin_id]
            
            self._logger.info(f"Unregistered plugin: {plugin_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to unregister plugin {plugin_id}: {e}")
    
    async def _shutdown_plugin(self, plugin_id: str) -> None:
        """Shutdown plugin asynchronously."""
        instance = self._instances.get(plugin_id)
            await instance.shutdown()
    
    # ===== PLUGIN CONTROL =====
    
        """Enable a plugin."""
        if not info:
            return False
        
        if info.state == PluginState.ENABLED:
        
        try:
            instance = self._instances.get(plugin_id)
            if instance and await instance.enable():
                info.state = PluginState.ENABLED
                self._stats['enabled_plugins'] += 1
                return True
                
        except Exception as e:
            info.state = PluginState.ERROR
            self._logger.error(f"Failed to enable plugin {plugin_id}: {e}")
    
    async def disable_plugin(self, plugin_id: str) -> bool:
        info = self._plugins.get(plugin_id)
        if not info:
            return False
        
        if info.state == PluginState.DISABLED:
            return True
        try:
            instance = self._instances.get(plugin_id)
                info.state = PluginState.DISABLED
                self._logger.info(f"Disabled plugin: {plugin_id}")
                return True
        except Exception as e:
            info.error = str(e)
            self._logger.error(f"Failed to disable plugin {plugin_id}: {e}")
    
    async def reload_plugin(self, plugin_id: str) -> bool:
        """Reload a plugin (hot reload)."""
        info = self._plugins.get(plugin_id)
            return False
        info.state = PluginState.UPDATING
        
        try:
            # Save state
            state = {}
            if info.instance:
                state = info.instance.export_state()
            # Disable
            await self.disable_plugin(plugin_id)
            
            # Re-initialize
            info.state = PluginState.LOADED
            await self._initialize_plugin(plugin_id)
            
            # Restore state
            if info.instance and state:
            
            # Re-enable
            if info.manifest.enabled:
                await self.enable_plugin(plugin_id)
            
            self._logger.info(f"Reloaded plugin: {plugin_id}")
            return True
        except Exception as e:
            info.error = str(e)
            self._logger.error(f"Failed to reload plugin {plugin_id}: {e}")
    
    # ===== QUERY METHODS =====
    
    def get_plugin(self, plugin_id: str) -> Optional[PluginInfo]:
        return self._plugins.get(plugin_id)
    def get_plugins(
        self,
        plugin_type: Optional[PluginType] = None,
        state: Optional[PluginState] = None,
    ) -> List[PluginInfo]:
        """Get plugins with optional filters."""
        
        if plugin_type:
            result = [p for p in result if p.manifest.plugin_type == plugin_type]
        
        if state:
            result = [p for p in result if p.state == state]
        if enabled is not None:
            result = [p for p in result if p.manifest.enabled == enabled]
        
        return result
    
    def get_plugin_instance(self, plugin_id: str) -> Optional[Plugin]:
        """Get plugin instance."""
        return self._instances.get(plugin_id)
    
    # ===== DEPENDENCY CHECKING =====
    
    def _check_api_version(self, api_version: str) -> bool:
        """Check if API version is supported."""
        major = api_version.split('.')[0]
        return major in ['1', '2']  # Support API v1 and v2
    def _check_dependencies(self, dependencies: List[str]) -> List[str]:
        """Check if all dependencies are registered."""
        missing = []
        for dep in dependencies:
                missing.append(dep)
    
    # ===== SAVE SYSTEM INTEGRATION =====
    
    def export_plugins_state(self) -> Dict[str, Dict[str, Any]]:
        """Export all plugin states."""
        result = {}
        for plugin_id, instance in self._instances.items():
                result[plugin_id] = instance.export_state()
                self._logger.error(f"Failed to export plugin {plugin_id}: {e}")
        return result
    
    def import_plugins_state(self, data: Dict[str, Dict[str, Any]]) -> None:
        """Import all plugin states."""
        for plugin_id, state in data.items():
            if plugin_id in self._instances:
                    self._instances[plugin_id].import_state(state)
                    self._logger.error(f"Failed to import plugin {plugin_id}: {e}")
    
    # ===== STATISTICS =====
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get plugin manager statistics."""
        return {
            **self._stats,
            'plugins_by_type': {
                for ptype in PluginType
            },
            'plugins_by_state': {
                state.value: len([p for p in self._plugins.values() if p.state == state])
            }
        }
    
    def get_plugin_info(self) -> Dict[str, Any]:
        return {
            plugin_id: info.to_dict()
        }
# ============================================================
# 28.5. PLUGIN DISCOVERY
# ============================================================
class PluginDiscovery:
    """Plugin discovery and loading from directory."""
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self._logger = logging.getLogger("plugin_discovery")
    
    async def discover_plugins(self) -> List[bool]:
        """Discover and load plugins from directory."""
        
        for plugin_dir in self.plugin_manager.plugin_dir.iterdir():
                manifest_path = plugin_dir / "manifest.json"
                if manifest_path.exists():
                    try:
                        loaded = await self._load_plugin_from_dir(plugin_dir)
                    except Exception as e:
                        results.append(False)
        
        return results
    
    async def _load_plugin_from_dir(self, plugin_dir: Path) -> bool:
        """Load a plugin from directory."""
        manifest_path = plugin_dir / "manifest.json"
        with open(manifest_path, 'r', encoding='utf-8') as f:
        
        manifest = PluginManifest.from_dict(manifest_data)
        # Find plugin class
        plugin_file = plugin_dir / "plugin.py"
        if not plugin_file.exists():
            self._logger.error(f"Plugin file not found: {plugin_file}")
        
        # Import plugin module
        spec = importlib.util.spec_from_file_location(manifest.id, plugin_file)
        if not spec:
            self._logger.error(f"Failed to load spec for {plugin_file}")
            return False
        module = importlib.util.module_from_spec(spec)
        sys.modules[manifest.id] = module
        spec.loader.exec_module(module)
        
        # Find Plugin class
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (inspect.isclass(attr) and 
                issubclass(attr, Plugin) and 
                attr != Plugin):
                break
        
        if not plugin_class:
            self._logger.error(f"Plugin class not found in {plugin_file}")
        
        # Register plugin
        return self.plugin_manager.register(manifest, plugin_class)

# ============================================================
# 28.6. EXAMPLE PLUGIN
# ============================================================

class ExamplePlugin(Plugin):
    
    def __init__(self, context):
        super().__init__(context)
        self._data = {"counter": 0}
    async def initialize(self) -> bool:
        return True
    
    async def enable(self) -> bool:
        self._logger.info("Example plugin enabled")
    
    async def disable(self) -> bool:
        return True
    
    async def shutdown(self) -> bool:
        self._logger.info("Example plugin shut down")
    
    def export_state(self) -> Dict[str, Any]:
        return {"counter": self._data["counter"]}
    
    def import_state(self, data: Dict[str, Any]) -> None:
        self._data["counter"] = data.get("counter", 0)
    def get_information(self) -> Dict[str, Any]:
        return {
            'name': 'Example Plugin',
            'version': '1.0.0',
            'description': 'A simple example plugin'
        }
    
    def register_commands(self) -> Dict[str, Callable]:
        return {
            'example_counter': self._cmd_counter
    
    def register_permissions(self) -> List[str]:
        return [
            'CAN_USE_EXAMPLE',
            'CAN_MODIFY_EXAMPLE'
    
    async def _cmd_hello(self, *args, **kwargs):
        return {"message": "Hello from Example Plugin!"}
    
    async def _cmd_counter(self, *args, **kwargs):
        self._data["counter"] += 1
        return {"counter": self._data["counter"]}

# ============================================================
# ============================================================
async def test_plugin_system():
    """Test Plugin System."""
    print("🧪 ТЕСТИРОВАНИЕ PLUGIN SYSTEM")
    
    # Create plugin manager
    
    # Test 1: Register plugin
    print("\n📋 Тест 1: Регистрация плагина")
    
    manifest = PluginManifest(
        id="test_plugin",
        name="Test Plugin",
        author="Test Author",
        version="1.0.0",
        description="Test plugin for testing",
        plugin_type=PluginType.CUSTOM,
        permissions=["TEST_PERMISSION"],
        enabled=True
    )
    
    success = manager.register(manifest, ExamplePlugin)
    assert success
    print(f"   ✅ Плагин зарегистрирован: {manifest.name}")
    # Test 2: Get plugin
    print("\n📋 Тест 2: Получение плагина")
    
    plugin_info = manager.get_plugin("test_plugin")
    assert plugin_info is not None
    print(f"   ✅ Плагин найден: {plugin_info.manifest.name}")
    print(f"   Состояние: {plugin_info.state.value}")
    
    # Test 3: Enable plugin
    print("\n📋 Тест 3: Включение плагина")
    await asyncio.sleep(0.1)  # Allow initialization
    enabled = await manager.enable_plugin("test_plugin")
    print(f"   ✅ Плагин включен")
    
    # Test 4: Disable plugin
    print("\n📋 Тест 4: Отключение плагина")
    disabled = await manager.disable_plugin("test_plugin")
    print(f"   ✅ Плагин отключен")
    
    # Test 5: Reload plugin
    print("\n📋 Тест 5: Перезагрузка плагина")
    
    reloaded = await manager.reload_plugin("test_plugin")
    assert reloaded
    print(f"   ✅ Плагин перезагружен")
    
    # Test 6: Export state
    print("\n📋 Тест 6: Экспорт состояния")
    
    state = manager.export_plugins_state()
    print(f"   ✅ Состояние экспортировано: {len(state)} плагинов")
    # Test 7: Statistics
    print("\n📋 Тест 7: Статистика")
    stats = manager.get_statistics()
    print(f"   Загружено: {stats['loaded_plugins']}")
    print(f"   Включено: {stats['enabled_plugins']}")
    
    # Test 8: Get all plugins
    print("\n📋 Тест 8: Список плагинов")
    
    plugins = manager.get_plugins()
    print(f"   Найдено: {len(plugins)} плагинов")
        print(f"   - {plugin.manifest.name} ({plugin.state.value})")
    
    # Test 9: Plugin instance
    print("\n📋 Тест 9: Получение экземпляра")
    instance = manager.get_plugin_instance("test_plugin")
    assert instance is not None
    print(f"   ✅ Экземпляр получен: {info['name']}")
    # Test 10: Unregister
    print("\n📋 Тест 10: Удаление плагина")
    unregistered = manager.unregister("test_plugin")
    print(f"   ✅ Плагин удален")
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)
# ============================================================
# 28.8. GLOBAL INSTANCE
# ============================================================

plugin_discovery = PluginDiscovery(plugin_manager)

# ============================================================
# 28.9. MAIN
# ============================================================

if __name__ == "__main__":
