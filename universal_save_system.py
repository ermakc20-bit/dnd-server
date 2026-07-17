Universal Save System - Fully independent save/load system.
Only saves state of game objects.

import json
import gzip
import zipfile
import uuid
import shutil
import tempfile
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Union, Tuple
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import pickle

# ============================================================
# ============================================================
class SaveType(str, Enum):
    """Types of saves."""
    MANUAL = "manual"
    AUTO = "auto"
    CHECKPOINT = "checkpoint"
    QUICKSAVE = "quicksave"
    BACKUP = "backup"

class SaveState(str, Enum):
    CREATED = "created"
    LOADING = "loading"
    FAILED = "failed"
    DELETED = "deleted"

class AutoSaveMode(str, Enum):
    """Auto-save modes."""
    DISABLED = "disabled"
    EVERY_5_MINUTES = "every_5_minutes"
    EVERY_10_MINUTES = "every_10_minutes"
    EVERY_15_MINUTES = "every_15_minutes"
    COMBAT_START = "combat_start"
    MANUAL_ONLY = "manual_only"

# ============================================================
# 27.2. DATA CLASSES
# ============================================================
@dataclass
class SaveMetadata:
    """Metadata for a save."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario_id: str = ""
    save_name: str = ""
    save_type: SaveType = SaveType.MANUAL
    created_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0"
    description: str = ""
    play_time: float = 0.0
    scene: str = ""
    custom_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
            'id': self.id,
            'room_id': self.room_id,
            'scenario_id': self.scenario_id,
            'save_name': self.save_name,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
            'version': self.version,
            'play_time': self.play_time,
            'custom_metadata': self.custom_metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SaveMetadata':
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            scenario_id=data.get('scenario_id', ''),
            save_type=SaveType(data.get('save_type', 'manual')),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            version=data.get('version', '1.0'),
            play_time=data.get('play_time', 0.0),
            scene=data.get('scene', ''),
        )

@dataclass
class SaveData:
    """Complete save data."""
    metadata: SaveMetadata
    room_state: Dict[str, Any] = field(default_factory=dict)
    characters: Dict[str, Any] = field(default_factory=dict)
    tokens: Dict[str, Any] = field(default_factory=dict)
    effects: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    initiative: Dict[str, Any] = field(default_factory=dict)
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'metadata': self.metadata.to_dict(),
            'room_state': self.room_state,
            'characters': self.characters,
            'tokens': self.tokens,
            'inventory': self.inventory,
            'quests': self.quests,
            'variables': self.variables,
            'dice_history': self.dice_history,
            'chat_history': self.chat_history,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SaveData':
            metadata=SaveMetadata.from_dict(data.get('metadata', {})),
            characters=data.get('characters', {}),
            tokens=data.get('tokens', {}),
            effects=data.get('effects', {}),
            variables=data.get('variables', {}),
            initiative=data.get('initiative', {}),
            chat_history=data.get('chat_history', []),
        )

# ============================================================
# 27.3. PLUGIN API
# ============================================================

class SaveModule:
    """Base class for save modules."""
    
    def __init__(self, name: str):
        self.name = name
    
    def export(self) -> Dict[str, Any]:
        """Export module data for save."""
    
    def import_data(self, data: Dict[str, Any]) -> None:
        """Import data from save."""

class SaveModuleRegistry:
    """Registry for save modules."""
    
    def __init__(self):
        self._modules: Dict[str, SaveModule] = {}
        self._logger = logging.getLogger("save_module_registry")
    def register(self, module: SaveModule) -> None:
        self._modules[module.name] = module
        self._logger.info(f"Registered module: {module.name}")
    def unregister(self, name: str) -> bool:
        if name in self._modules:
            del self._modules[name]
            return True
        return False
    
    def get_modules(self) -> Dict[str, SaveModule]:
        return dict(self._modules)
    def get_module(self, name: str) -> Optional[SaveModule]:
        """Get a specific module."""
    
    def export_all(self) -> Dict[str, Any]:
        """Export all modules data."""
        result = {}
        for name, module in self._modules.items():
            try:
                result[name] = module.export()
            except Exception as e:
                self._logger.error(f"Error exporting module {name}: {e}")
    
    def import_all(self, data: Dict[str, Any]) -> None:
        """Import data to all modules."""
        for name, module in self._modules.items():
                try:
                    module.import_data(data[name])
                except Exception as e:
                    self._logger.error(f"Error importing module {name}: {e}")
# ============================================================
# ============================================================

class UniversalSaveSystem:
    """
    Universal Save System - Independent save/load system.
    Knows nothing about game mechanics.
    """
    
    def __init__(self, save_dir: str = "saves", max_autosaves: int = 10):
        self.max_autosaves = max_autosaves
        self._module_registry = SaveModuleRegistry()
        self._lock = asyncio.Lock()
        # Create directories
        self.save_dir.mkdir(parents=True, exist_ok=True)
        (self.save_dir / "auto").mkdir(parents=True, exist_ok=True)
        (self.save_dir / "quicksave").mkdir(parents=True, exist_ok=True)
        (self.save_dir / "backup").mkdir(parents=True, exist_ok=True)
        
        # Auto-save settings
        self._auto_save_mode: AutoSaveMode = AutoSaveMode.DISABLED
        self._auto_save_task: Optional[asyncio.Task] = None
        
        # Event bus integration
        self.event_bus = None
        
        # Statistics
        self._stats = {
            'total_saves': 0,
            'total_loads': 0,
            'total_deletes': 0,
            'failed_loads': 0
        }
        
        # Logger
        self._logger = logging.getLogger("universal_save_system")
    # ===== MODULE REGISTRATION =====
    
    def register_module(self, module: SaveModule) -> None:
        """Register a save module."""
    
    def unregister_module(self, name: str) -> bool:
        return self._module_registry.unregister(name)
    def get_modules(self) -> Dict[str, SaveModule]:
        """Get all registered modules."""
    
    # ===== SAVE OPERATIONS =====
    
    async def create_save(
        self,
        room_id: int,
        scenario_id: str,
        data: Dict[str, Any],
        save_name: str = "",
        created_by: int = 0,
        version: str = "1.0"
    ) -> Optional[SaveData]:
        """Create a new save."""
        async with self._lock:
                # Create metadata
                metadata = SaveMetadata(
                    scenario_id=scenario_id,
                    save_type=save_type,
                    created_by=created_by,
                    description=description,
                    scene=data.get('scene', '')
                )
                
                # Collect module data
                
                # Create save data
                    metadata=metadata,
                    characters=data.get('characters', {}),
                    tokens=data.get('tokens', {}),
                    effects=data.get('effects', {}),
                    variables=data.get('variables', {}),
                    initiative=data.get('initiative', {}),
                    chat_history=data.get('chat_history', []),
                )
                
                # Export to file
                save_path = self._get_save_path(metadata.id, save_type)
                
                # Update stats
                
                # Store current save
                self._current_save = save_data
                
                # Publish event
                await self._publish_event('SAVE_CREATED', {
                    'save_name': metadata.save_name,
                    'save_type': save_type.value
                
                self._logger.info(f"Save created: {metadata.save_name} ({metadata.id})")
                return save_data
                
            except Exception as e:
                self._logger.error(f"Failed to create save: {e}")
                return None
    
    async def load_save(self, save_id: str) -> Optional[SaveData]:
        """Load a save by ID."""
        async with self._lock:
            try:
                # Find save file
                if not save_path:
                    return None
                
                # Import save
                save_data = await self._import_save(save_path)
                    return None
                
                # Restore modules
                self._module_registry.import_all(save_data.custom_data)
                # Update stats
                self._stats['total_loads'] += 1
                # Store current save
                
                # Publish event
                    'save_id': save_data.metadata.id,
                })
                
                self._logger.info(f"Save loaded: {save_data.metadata.save_name} ({save_id})")
                return save_data
            except Exception as e:
                self._logger.error(f"Failed to load save: {e}")
                return None
    
    async def delete_save(self, save_id: str) -> bool:
        """Delete a save."""
            try:
                # Find save file
                save_path = self._find_save_file(save_id)
                if not save_path:
                
                # Delete file
                
                # Also delete metadata if exists
                meta_path = self.save_dir / "metadata" / f"{save_id}.json"
                if meta_path.exists():
                    meta_path.unlink()
                
                # Update stats
                self._stats['total_deletes'] += 1
                
                # Publish event
                await self._publish_event('SAVE_DELETED', {
                })
                
                self._logger.info(f"Save deleted: {save_id}")
                return True
            except Exception as e:
                self._logger.error(f"Failed to delete save: {e}")
    
    async def rename_save(self, save_id: str, new_name: str) -> bool:
        """Rename a save."""
        async with self._lock:
            try:
                # Find save file
                if not save_path:
                    return False
                # Load save
                if not save_data:
                    return False
                
                # Update name
                
                # Re-save
                await self._export_save(save_data, save_path)
                
                self._logger.info(f"Save renamed: {save_id} -> {new_name}")
                return True
                
            except Exception as e:
                self._logger.error(f"Failed to rename save: {e}")
    
    async def duplicate_save(self, save_id: str, new_name: str) -> Optional[str]:
        async with self._lock:
                # Find save file
                save_path = self._find_save_file(save_id)
                    return None
                
                # Load save
                save_data = await self._import_save(save_path)
                    return None
                # Create new ID and name
                new_id = str(uuid.uuid4())
                save_data.metadata.id = new_id
                save_data.metadata.created_at = datetime.now()
                save_data.metadata.save_type = SaveType.MANUAL
                # Save duplicate
                await self._export_save(save_data, new_path)
                
                self._logger.info(f"Save duplicated: {save_id} -> {new_id}")
                return new_id
            except Exception as e:
                self._logger.error(f"Failed to duplicate save: {e}")
    
    # ===== SAVE LISTING =====
    
    async def list_saves(
        self,
        room_id: Optional[int] = None,
        limit: int = 100
    ) -> List[SaveMetadata]:
        saves = []
        
        # Search all save directories
        for save_type_dir in ["manual", "auto", "checkpoint", "quicksave", "backup"]:
            if not dir_path.exists():
            
            for file_path in dir_path.glob("*.json.gz"):
                    # Extract metadata
                    save_data = await self._import_save(file_path)
                    if save_data:
                        metadata = save_data.metadata
                        
                        if room_id is not None and metadata.room_id != room_id:
                            continue
                            continue
                        
                        saves.append(metadata)
                except Exception as e:
                    self._logger.error(f"Error reading save file {file_path}: {e}")
        
        # Sort by created_at (newest first)
        saves.sort(key=lambda s: s.created_at, reverse=True)
        return saves[:limit]
    
    async def get_save(self, save_id: str) -> Optional[SaveData]:
        """Get a save by ID."""
        save_path = self._find_save_file(save_id)
        if not save_path:
            return None
        
        return await self._import_save(save_path)
    async def save_exists(self, save_id: str) -> bool:
        """Check if a save exists."""
        return self._find_save_file(save_id) is not None
    
    # ===== CHECKPOINTS =====
    
    async def create_checkpoint(
        room_id: int,
        scenario_id: str,
        data: Dict[str, Any],
        description: str = ""
        """Create a checkpoint save."""
            room_id=room_id,
            scenario_id=scenario_id,
            save_name=f"Checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=description
        )
    
    # ===== AUTO-SAVE =====
    
    def enable_autosave(
        self,
        mode: AutoSaveMode = AutoSaveMode.EVERY_5_MINUTES,
        interval: int = 300
    ) -> None:
        """Enable auto-save."""
        self._auto_save_mode = mode
        
        if self._auto_save_task is None or self._auto_save_task.done():
            self._auto_save_task = asyncio.create_task(self._autosave_loop())
        
        self._logger.info(f"Auto-save enabled: {mode.value}")
    
    def disable_autosave(self) -> None:
        """Disable auto-save."""
        self._auto_save_mode = AutoSaveMode.DISABLED
        if self._auto_save_task:
            self._auto_save_task = None
        
        self._logger.info("Auto-save disabled")
    async def trigger_autosave(self, room_id: int, data: Dict[str, Any]) -> Optional[SaveData]:
        """Manually trigger auto-save."""
            return None
        return await self.create_save(
            room_id=room_id,
            data=data,
            save_type=SaveType.AUTO,
            description="Auto-save"
        )
    
    async def _autosave_loop(self) -> None:
        while self._auto_save_mode != AutoSaveMode.DISABLED:
            try:
                await asyncio.sleep(self._auto_save_interval)
                
                if self._auto_save_mode == AutoSaveMode.DISABLED:
                    break
                
                # Trigger auto-save
                if self._current_save:
                    # Use current save data
                    data = self._current_save.to_dict()
                    await self.trigger_autosave(
                        data=data
                    )
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
    
    # ===== FILE OPERATIONS =====
    
    def _get_save_path(self, save_id: str, save_type: SaveType) -> Path:
        type_dir = {
            SaveType.MANUAL: "manual",
            SaveType.AUTO: "auto",
            SaveType.CHECKPOINT: "checkpoint",
            SaveType.BACKUP: "backup"
        
        return self.save_dir / type_dir / f"{save_id}.json.gz"
    def _find_save_file(self, save_id: str) -> Optional[Path]:
        for type_dir in ["manual", "auto", "checkpoint", "quicksave", "backup"]:
            path = self.save_dir / type_dir / f"{save_id}.json.gz"
                return path
            # Also check without compression
            path = self.save_dir / type_dir / f"{save_id}.json"
            if path.exists():
                return path
        return None
    async def _export_save(self, save_data: SaveData, path: Path) -> None:
        """Export save to file with compression."""
            # Convert to dict
            
            # Add checksum
            json_str = json.dumps(data, default=str, indent=2)
            data['_checksum'] = checksum
            
            # Compress and save
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp:
                tmp.write(compressed)
                tmp_path = tmp.name
            # Move to target
            shutil.move(tmp_path, path)
        
        await asyncio.get_event_loop().run_in_executor(None, sync_export)
    async def _import_save(self, path: Path) -> Optional[SaveData]:
        def sync_import():
            with open(path, 'rb') as f:
            
            # Decompress
            try:
                json_str = gzip.decompress(data).decode('utf-8')
                # Not compressed
            
            # Parse
            data_dict = json.loads(json_str)
            
            # Verify checksum
            checksum = data_dict.pop('_checksum', None)
            if checksum:
                json_str = json.dumps(data_dict, default=str, indent=2)
                computed = hashlib.sha256(json_str.encode()).hexdigest()
                    raise ValueError("Checksum verification failed")
            
            return SaveData.from_dict(data_dict)
        
        try:
            return await asyncio.get_event_loop().run_in_executor(None, sync_import)
        except Exception as e:
            return None
    
    # ===== EVENT BUS INTEGRATION =====
    
    async def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish event to event bus."""
            try:
                from event_bus import Event
                    event_type=f"save_{event_type.lower()}",
                    payload=data
                )
                self.event_bus.publish(event)
            except Exception as e:
    
    # ===== STATISTICS =====
    def get_statistics(self) -> Dict[str, Any]:
        return {
            **self._stats,
            'autosave_mode': self._auto_save_mode.value,
            'max_autosaves': self.max_autosaves
        }

# ============================================================
# ============================================================

class ExampleModule(SaveModule):
    """Example save module for demonstration."""
    def __init__(self):
        super().__init__("example")
    
    def export(self) -> Dict[str, Any]:
        return {"counter": self.data["counter"]}
    
    def import_data(self, data: Dict[str, Any]) -> None:
        self.data["counter"] = data.get("counter", 0)
# ============================================================
# 27.6. TESTS
# ============================================================

async def test_universal_save_system():
    """Test Universal Save System."""
    print("\n" + "="*60)
    print("🧪 ТЕСТИРОВАНИЕ UNIVERSAL SAVE SYSTEM")
    
    # Create system
    save_system = UniversalSaveSystem(save_dir="test_saves")
    
    # Register test module
    test_module = ExampleModule()
    save_system.register_module(test_module)
    # Test data
    test_data = {
        'room_state': {'state': 'exploration', 'current_scene': 'tavern'},
        'characters': {'char_1': {'name': 'Warrior', 'hp': 50}},
        'inventory': {'item_1': {'name': 'Sword', 'count': 1}},
        'quests': {'quest_1': {'name': 'Main Quest', 'state': 'active'}},
        'variables': {'var_1': 'value_1'},
        'dice_history': [{'roll': 10}],
        'play_time': 120.5,
        'scene': 'tavern'
    
    
        scenario_id="test_scenario",
        save_name="Test Save",
    )
    assert save_data is not None
    # Test 2: List saves
    saves = await save_system.list_saves(limit=10)
    for save in saves[:3]:
        print(f"   - {save.save_name} ({save.save_type.value})")
    # Test 3: Load save
    print("\n📋 Тест 3: Загрузка сохранения")
    
    loaded = await save_system.load_save(save_data.metadata.id)
    print(f"   ✅ Загружено: {loaded.metadata.save_name}")
    print(f"     Персонажей: {len(loaded.characters)}")
    
    # Test 4: Rename save
    print("\n📋 Тест 4: Переименование")
    new_name = "Renamed Save"
    assert success
    
    print("\n📋 Тест 5: Дублирование")
    print(f"   ✅ Создана копия: {dup_id}")
    
    # Test 6: Checkpoint
    checkpoint = await save_system.create_checkpoint(
        data=test_data,
        description="Before boss fight"
    print(f"   ✅ Создана контрольная точка: {checkpoint.metadata.save_name}")
    
    save_system.enable_autosave(AutoSaveMode.EVERY_5_MINUTES, interval=1)
    await asyncio.sleep(2)
    # Test 8: Save exists
    print("\n📋 Тест 8: Проверка существования")
    exists = await save_system.save_exists(save_data.metadata.id)
    not_exists = await save_system.save_exists("non_existent_id")
    print(f"   ✅ Несуществующее сохранение: {not not_exists}")
    # Test 9: Delete save
    print("\n📋 Тест 9: Удаление")
    deleted = await save_system.delete_save(save_data.metadata.id)
    print(f"   ✅ Сохранение удалено")
    
    # Test 10: Statistics
    print("\n📋 Тест 10: Статистика")
    stats = save_system.get_statistics()
    print(f"   Всего сохранений: {stats['total_saves']}")
    print(f"   Всего удалений: {stats['total_deletes']}")
    
    # Cleanup
    import shutil
    shutil.rmtree("test_saves", ignore_errors=True)
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# ============================================================

universal_save_system = UniversalSaveSystem()

# ============================================================
# 27.8. MAIN
# ============================================================
if __name__ == "__main__":
    asyncio.run(test_universal_save_system())
