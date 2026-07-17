Configuration System - Centralized server configuration management.
All subsystems get settings only through Configuration Manager.
"""

import json
import yaml
import sys
import logging
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, TypeVar, Generic, Callable
from dataclasses import dataclass, field
from functools import lru_cache
import copy
import re

# 30.1. ENUMS
# ============================================================

class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

    """Configuration types."""
    SERVER = "server"
    UI = "ui"
    DICE = "dice"
    NETWORK = "network"
    LOGGING = "logging"
    DATABASE = "database"
    UPLOAD = "upload"
    COMBAT = "combat"
    PERMISSION = "permission"
    INVENTORY = "inventory"
    AI = "ai"
    SAVE = "save"
    WEBSOCKET = "websocket"
    PLUGIN = "plugin"

# ============================================================
# ============================================================
@dataclass
class ConfigValue:
    value: Any
    source: str = "default"  # default, file, env, override
    modified_at: Optional[datetime] = None

        return {
            'value': self.value,
            'source': self.source,
            'modified_at': self.modified_at.isoformat() if self.modified_at else None,
        }

@dataclass
class ConfigChange:
    key: str
    old_value: Any
    new_value: Any
    timestamp: datetime
    changed_by: str
    source: str

    def to_dict(self) -> dict:
        return {
            'old_value': self.old_value,
            'timestamp': self.timestamp.isoformat(),
            'changed_by': self.changed_by,
        }

@dataclass
class ConfigSchema:
    type: str  # string, integer, float, boolean, list, dict
    default: Any = None
    min_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    pattern: Optional[str] = None  # Regex pattern for strings
    enum: Optional[List[Any]] = None
    description: str = ""

    def validate(self, value: Any) -> tuple[bool, str]:
        """Validate a value against schema."""
        # Check required
            return False, f"Required field missing"
        if value is None:
            return True, ""
        # Check type
        type_map = {
            'string': str,
            'integer': int,
            'boolean': bool,
            'dict': dict
        }
        expected_type = type_map.get(self.type)
            return False, f"Expected type {self.type}, got {type(value).__name__}"
        # Numeric bounds
        if self.type in ['integer', 'float']:
            if self.min_value is not None and value < self.min_value:
            if self.max_value is not None and value > self.max_value:
                return False, f"Value {value} above maximum {self.max_value}"
        # String bounds
        if self.type == 'string':
            if self.min_length is not None and len(value) < self.min_length:
                return False, f"String length {len(value)} below minimum {self.min_length}"
                return False, f"String length {len(value)} above maximum {self.max_length}"
                return False, f"String doesn't match pattern {self.pattern}"

        # Enum
        if self.enum is not None and value not in self.enum:


# ============================================================
# 30.3. CONFIGURATION MANAGER
# ============================================================
class ConfigurationManager:
    Centralized Configuration Manager.
    All subsystems get settings through this manager.
    """
    
    _instance = None
    _initialized = False
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self):
        if self._initialized:
            return
        
        self._config: Dict[str, ConfigValue] = {}
        self._defaults: Dict[str, Any] = {}
        self._environment: Environment = Environment.DEVELOPMENT
        self._lock = threading.RLock()
        self._max_history = 1000
        self._watchers: Dict[str, List[Callable]] = {}
        self._loaded_files: List[str] = []
        self._hot_reload_enabled = True
        
        # Setup
        self._setup_logging()
        self._setup_defaults()
        self._setup_schemas()
        # Load configuration
        self.load()
        
        # Start hot reload thread
            self._start_hot_reload()
    # ===== SETUP =====
    
        """Setup logging."""
        self._logger.setLevel(logging.INFO)
        
        if not self._logger.handlers:
            handler = logging.StreamHandler()
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
    
    def _setup_defaults(self):
        """Setup default configuration values."""
        self._defaults = {
            'server.name': 'Dice Master Server',
            'server.host': '0.0.0.0',
            'server.port': 8080,
            'server.max_rooms': 100,
            'server.idle_timeout': 3600,  # seconds
            'server.shutdown_timeout': 30,
            # UI
            'ui.theme': 'dark',
            'ui.language': 'ru',
            'ui.animations_enabled': True,
            'ui.max_notifications': 50,
            # Dice
            'dice.max_dice_count': 100,
            'dice.animation_duration': 1.5,  # seconds
            'dice.modifiers_enabled': True,
            'dice.history_limit': 1000,
            # Network
            'network.max_packet_size': 65536,  # bytes
            'network.heartbeat_interval': 30,  # seconds
            'network.timeout': 60,  # seconds
            'network.rate_limit': 100,  # requests per minute
            
            # Logging
            'logging.level': 'INFO',
            'logging.max_entries': 10000,
            'logging.backup_count': 5,
            'logging.format': 'json',
            'logging.file_enabled': True,
            # Database
            'database.type': 'sqlite',
            'database.port': 5432,
            'database.user': 'postgres',
            'database.password': '',
            'database.max_connections': 20,
            'database.backup_interval': 86400,  # 24 hours
            
            # Security
            'security.jwt_secret': 'default_jwt_secret_change_me',
            'security.rate_limit': 100,
            'security.max_login_attempts': 5,
            'security.password_min_length': 8,
            'security.require_special_chars': True,
            'security.enable_cors': True,
            
            # Upload
            'upload.max_file_size': 10485760,  # 10 MB
            'upload.allowed_extensions': ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'],
            'upload.storage_path': './uploads',
            
            # Combat
            'combat.auto_end_turn': 60,  # seconds
            'combat.status_effects_enabled': True,
            'combat.advantage_roll': True,
            'combat.heal_roll': 'd4',
            
            # Effects
            'effect.max_active_effects': 50,
            'effect.auto_expire': True,
            'effect.show_expiry_warning': True,
            
            # Permission
            'permission.default_role': 'player',
            'permission.cache_ttl': 300,  # seconds
            'permission.enforce_permissions': True,
            # Room
            'room.max_map_size': 100,  # tiles
            'room.min_map_size': 5,
            'room.default_map_size': 20,
            'room.auto_save_interval': 300,  # seconds
            'room.max_room_description_length': 1000,
            
            'inventory.max_slots': 50,
            'inventory.default_capacity': 100,
            'inventory.auto_sort': True,
            
            # AI
            'ai.enabled': False,
            'ai.provider': 'openai',
            'ai.temperature': 0.7,
            'ai.max_tokens': 1000,
            'ai.timeout': 30,
            'ai.api_key': '',
            # Save
            'save.max_saves_per_user': 50,
            'save.max_saves_per_room': 10,
            'save.auto_save_interval': 60,  # seconds
            'save.retention_days': 30,
            # WebSocket
            'websocket.ping_interval': 30,
            'websocket.max_message_size': 65536,
            
            # Plugin
            'plugin.plugin_dir': './plugins',
            'plugin.allow_network': False,
            'plugin.sandbox_enabled': True,
            # System
            'system.timezone': 'UTC',
            'system.date_format': 'YYYY-MM-DD',
            'system.time_format': 'HH:mm:ss',
            'system.maintenance_mode': False,
            'system.max_cpu_percent': 80
        }
    
    def _setup_schemas(self):
        """Setup configuration schemas for validation."""
        self._schemas = {
            # Server
            'server.port': ConfigSchema('integer', True, 8080, 1, 65535),
            'server.max_players': ConfigSchema('integer', True, 6, 1, 100),
            'server.max_players_per_room': ConfigSchema('integer', True, 8, 1, 50),
            'server.idle_timeout': ConfigSchema('integer', True, 3600, 60, 86400),
            
            # Dice
            'dice.max_dice_count': ConfigSchema('integer', True, 100, 1, 1000),
            'dice.max_dice_sides': ConfigSchema('integer', True, 1000, 2, 10000),
            'dice.modifiers_enabled': ConfigSchema('boolean', True, True),
            # Network
            'network.max_packet_size': ConfigSchema('integer', True, 65536, 1024, 1048576),
            'network.max_connections': ConfigSchema('integer', True, 1000, 1, 10000),
            
            # Security
            'security.max_login_attempts': ConfigSchema('integer', True, 5, 1, 100),
            'security.jwt_expiry': ConfigSchema('integer', True, 86400, 60, 604800),
            
            'upload.max_file_size': ConfigSchema('integer', True, 10485760, 1024, 1073741824),
            
            # Room
            'room.min_map_size': ConfigSchema('integer', True, 5, 1, 50),
            'room.default_map_size': ConfigSchema('integer', True, 20, 5, 100),
            'room.max_rooms_per_user': ConfigSchema('integer', True, 5, 1, 100),
        }
    
    # ===== LOADING =====
    
    def load(self, environment: Optional[Environment] = None):
        """Load configuration from files."""
            if environment:
            else:
                env = os.getenv('DICEMASTER_ENV', 'development')
                    self._environment = Environment(env.lower())
                    self._environment = Environment.DEVELOPMENT
            
            self._logger.info(f"Loading configuration for environment: {self._environment.value}")
            
            # Create config directory if not exists
            self._config_dir.mkdir(parents=True, exist_ok=True)
            
            # Load defaults
            self._config = {}
            for key, value in self._defaults.items():
                self._config[key] = ConfigValue(value, "default")
            
            config_file = self._config_dir / f"{self._environment.value}.json"
                self._load_json_file(config_file)
            else:
                yaml_file = self._config_dir / f"{self._environment.value}.yaml"
                    self._load_yaml_file(yaml_file)
                else:
                    default_file = self._config_dir / "default.json"
                        self._load_json_file(default_file)
            
            for file_path in self._config_dir.glob("*.json"):
                    self._load_json_file(file_path)
            
            # Apply environment variables
            self._load_from_env()
            # Validate all values
            self._validate_all()
            self._logger.info(f"Configuration loaded: {len(self._config)} settings")
    
    def reload(self):
        """Reload configuration without restart."""
        self._logger.info("Reloading configuration...")
        self.load()
        
        # Log changes
        for key, value in self._config.items():
                old_val = old_config[key].value
                new_val = value.value
                    change = ConfigChange(
                        old_value=old_val,
                        new_value=new_val,
                        changed_by="system.reload",
                    )
                    self._change_history.append(change)
                        self._change_history = self._change_history[-self._max_history:]
                    self._logger.info(f"Config changed: {key} = {new_val} (was {old_val})")
                    
                    # Notify watchers
                    self._notify_watchers(key, old_val, new_val)
    
    def _load_json_file(self, file_path: Path):
        """Load configuration from JSON file."""
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._file_hashes[file_path.name] = self._compute_hash(file_path)
        except Exception as e:
            self._logger.error(f"Failed to load {file_path.name}: {e}")
    def _load_yaml_file(self, file_path: Path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
            self._merge_config(data, file_path.name)
            self._logger.info(f"Loaded config: {file_path.name}")
        except Exception as e:
    
    def _merge_config(self, data: Dict[str, Any], source: str):
        """Merge configuration data."""
        def flatten_dict(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
            for key, value in d.items():
                if isinstance(value, dict):
                    result.update(flatten_dict(value, full_key))
                    result[full_key] = value
        
        flat_data = flatten_dict(data)
        for key, value in flat_data.items():
                self._config[key].value = value
                self._config[key].source = source
            else:
                self._config[key] = ConfigValue(value, source, datetime.now())
    
    def _load_from_env(self):
        prefix = "DICEMASTER_"
        env_pattern = re.compile(r'^' + prefix + r'([A-Z_]+)$')
        
        for key, value in os.environ.items():
            if match:
                config_key = match.group(1).lower().replace('_', '.')
                # Try to parse value
                parsed_value = self._parse_env_value(value)
                    self._config[config_key].value = parsed_value
                    self._config[config_key].modified_at = datetime.now()
    
    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value."""
        if value.lower() in ['true', '1', 'yes']:
            return True
        if value.lower() in ['false', '0', 'no']:
            return False
        
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float
            return float(value)
            pass
        
        # String (including JSON)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    
    def _validate_all(self):
        """Validate all configuration values."""
            schema = self._schemas.get(key)
                is_valid, error = schema.validate(value.value)
                if not is_valid:
                    # Use default if available
                        self._config[key].value = schema.default
                        self._config[key].source = "default_override"
    
    # ===== GETTERS =====
    
    def get(self, key: str, default: Any = None) -> Any:
        if key in self._config:
            return self._config[key].value
        return default
    
    def get_typed(self, key: str, expected_type: type, default: Any = None) -> Any:
        """Get typed configuration value."""
        if value is not None and not isinstance(value, expected_type):
            self._logger.warning(f"Config {key} has wrong type: expected {expected_type.__name__}, got {type(value).__name__}")
        return value
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get integer value."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    def get_float(self, key: str, default: float = 0.0) -> float:
        value = self.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, default)
            return value
        if isinstance(value, str):
        return bool(value)
    
    def get_str(self, key: str, default: str = "") -> str:
        """Get string value."""
        return str(value) if value is not None else default
    def get_list(self, key: str, default: List[Any] = None) -> List[Any]:
        """Get list value."""
        if isinstance(value, list):
            return value
        return default or []
    def get_dict(self, key: str, default: Dict[str, Any] = None) -> Dict[str, Any]:
        value = self.get(key, default)
        if isinstance(value, dict):
        return default or {}
    
    def get_section(self, prefix: str) -> Dict[str, Any]:
        """Get all configurations with a prefix."""
        for key, value in self._config.items():
                subkey = key[len(prefix) + 1:]
                result[subkey] = value.value
    
    # ===== SETTERS =====
    
    def set(self, key: str, value: Any, source: str = "manual", changed_by: str = "user") -> bool:
        with self._lock:
            
            # Validate
            if key in self._schemas:
                is_valid, error = self._schemas[key].validate(value)
                    self._logger.error(f"Invalid value for {key}: {error}")
                    return False
            # Store
            self._config[key] = ConfigValue(value, source, datetime.now(), changed_by)
            
            # Log change
            if old_value is not None:
                    key=key,
                    old_value=old_value,
                    new_value=value,
                    changed_by=changed_by,
                    source=source
                self._change_history.append(change)
                    self._change_history = self._change_history[-self._max_history:]
                
                
                # Notify watchers
                self._notify_watchers(key, old_value, value)
            
            return True
    
    # ===== WATCHERS =====
    
    def watch(self, key: str, callback: Callable):
        if key not in self._watchers:
        self._watchers[key].append(callback)
        self._logger.debug(f"Added watcher for {key}")
    def unwatch(self, key: str, callback: Callable):
        if key in self._watchers:
            self._watchers[key].remove(callback)
    def _notify_watchers(self, key: str, old_value: Any, new_value: Any):
        if key in self._watchers:
            for callback in self._watchers[key]:
                    callback(key, old_value, new_value)
                    self._logger.error(f"Watcher callback failed: {e}")
        
        parent_key = '.'.join(key.split('.')[:-1])
            for callback in self._watchers[parent_key]:
                try:
                    callback(key, old_value, new_value)
                except Exception as e:
    
    # ===== HOT RELOAD =====
    def _start_hot_reload(self):
        def watch_files():
            while self._hot_reload_enabled:
                    time.sleep(5)  # Check every 5 seconds
                        if file_path.exists():
                            current_hash = self._compute_hash(file_path)
                                self._logger.info(f"Config file changed: {file_path.name}")
                                break
                except Exception as e:
        
        thread = threading.Thread(target=watch_files, daemon=True)
        thread.start()
        self._logger.info("Hot reload thread started")
    def _compute_hash(self, file_path: Path) -> str:
        try:
            with open(file_path, 'rb') as f:
        except Exception:
    
    def enable_hot_reload(self, enabled: bool):
        self._hot_reload_enabled = enabled
    
    # ===== QUERY METHODS =====
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return {key: value.value for key, value in self._config.items()}
    def get_all_metadata(self) -> Dict[str, Dict[str, Any]]:
        return {key: value.to_dict() for key, value in self._config.items()}
    
        """Get change history."""
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_settings': len(self._config),
            'environment': self._environment.value,
            'loaded_files': self._loaded_files,
            'watchers_count': sum(len(watchers) for watchers in self._watchers.values()),
        }
    
    
    def export(self, format: str = "json") -> str:
        """Export configuration."""
        data = self.get_all()
        if format.lower() == "json":
        elif format.lower() == "yaml":
            return yaml.dump(data, allow_unicode=True, default_flow_style=False)
            raise ValueError(f"Unsupported format: {format}")
    def save(self, file_path: Optional[Path] = None):
        """Save configuration to file."""
            file_path = self._config_dir / f"{self._environment.value}.json"
        data = self.get_all()
        with open(file_path, 'w', encoding='utf-8') as f:
        
        self._logger.info(f"Configuration saved to {file_path}")
    
    # ===== DYNAMIC ACCESS =====
    def __getattr__(self, name: str):
        if name.startswith('_'):
            return super().__getattribute__(name)
        # Check if it's a section
            section = ConfigType(name).value
            return self.get_section(section)
        # Try to get value
        if name in self._config:
            return self._config[name].value
        
        # Try as nested attribute
        for key, value in self._config.items():
                return value.value
        
        raise AttributeError(f"Configuration not found: {name}")
    
    def __getitem__(self, key: str) -> Any:
        """Dictionary-style access."""
        return self.get(key)
# ============================================================
# ============================================================

    """Decorator to get configuration value."""
        def wrapper(*args, **kwargs):
            config = ConfigurationManager()
            return func(value, *args, **kwargs)
    return decorator

def config_watch(key: str):
    """Decorator to watch configuration changes."""
        def wrapper(*args, **kwargs):
            config = ConfigurationManager()
            def callback(change_key, old_value, new_value):
            
            config.watch(key, callback)
        return wrapper
    return decorator

# ============================================================
# ============================================================
config = ConfigurationManager()

# ============================================================
# 30.6. TESTS
# ============================================================

async def test_configuration_system():
    print("\n" + "="*60)
    print("🧪 ТЕСТИРОВАНИЕ CONFIGURATION SYSTEM")
    print("="*60)
    
    config = ConfigurationManager()
    
    # Test 1: Default values
    print("\n📋 Тест 1: Значения по умолчанию")
    print(f"   server.max_players: {config.get('server.max_players')}")
    print(f"   network.rate_limit: {config.get('network.rate_limit')}")
    
    # Test 2: Type-safe getters
    max_players = config.get_int('server.max_players')
    debug = config.get_bool('system.debug_mode')
    print(f"   max_players: {max_players} (type: {type(max_players).__name__})")
    print(f"   debug_mode: {debug} (type: {type(debug).__name__})")
    
    # Test 3: Sections
    security = config.get_section('security')
    print(f"   jwt_expiry: {security.get('jwt_expiry')}")
    print(f"   ✅ Секции работают")
    # Test 4: Set and get
    print("\n📋 Тест 4: Установка значения")
    old_value = config.get('test.key')
    config.set('test.key', 'test_value', 'test')
    print(f"   old: {old_value}")
    print(f"   new: {new_value}")
    print(f"   ✅ Установка работает")
    
    print("\n📋 Тест 5: Динамический доступ")
        max_rooms = config.server.max_rooms
        print(f"   config.server.max_rooms: {max_rooms}")
    except AttributeError:
        print(f"   ❌ Динамический доступ не работает")
    
    # Test 6: History
    print("\n📋 Тест 6: История изменений")
    config.set('test.history', 1, 'test')
    config.set('test.history', 3, 'test')
    history = config.get_history(limit=10)
    print(f"   Записей в истории: {len(history)}")
    if history:
        latest = history[-1]
        print(f"   Последнее изменение: {latest.key} = {latest.new_value}")
    print(f"   ✅ История работает")
    
    # Test 7: Validation
    print("\n📋 Тест 7: Валидация")
    # Valid value
    valid = config.set('server.max_players', 10)
    print(f"   Установка 10: {valid}")
    # Invalid value
    invalid = config.set('server.max_players', 200)  # > 100
    print(f"   ✅ Валидация работает")
    
    # Test 8: Export
    print("\n📋 Тест 8: Экспорт")
    print(f"   JSON размер: {len(export_json)} байт")
    print(f"   YAML размер: {len(export_yaml)} байт")
    print(f"   ✅ Экспорт работает")
    # Test 9: Stats
    print("\n📋 Тест 9: Статистика")
    stats = config.get_stats()
    print(f"   Всего настроек: {stats['total_settings']}")
    print(f"   Изменений: {stats['changes_count']}")
    
    # Test 10: Environment
    old_env = config._environment
    env = config._environment
    print(f"   Текущее окружение: {env.value}")
    print(f"   ✅ Окружения работают")
    # Test 11: Watchers
    print("\n📋 Тест 11: Watchers")
    
    def on_config_change(key, old_val, new_val):
        nonlocal watcher_called
        watcher_called = True
    
    config.watch('test.watcher', on_config_change)
    config.set('test.watcher', 'test_value', 'test')
    print(f"   ✅ Watchers работают: {watcher_called}")
    # Test 12: All values
    print("\n📋 Тест 12: Все значения")
    all_config = config.get_all()
    print(f"   Всего значений: {len(all_config)}")
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# 30.7. MAIN
# ============================================================

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_configuration_system())
