# 24. SAVE & PERSISTENCE SYSTEM
# ============================================================
import asyncio
import json
import os
import shutil
import hashlib
import gzip
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
import copy
import tempfile
import threading

# ============================================================
# 24.1. БАЗОВЫЕ КЛАССЫ
# ============================================================
class SaveFormat(str, Enum):
    """Форматы сохранения."""
    JSON = "json"
    COMPRESSED_JSON = "json.gz"

class SaveStatus(str, Enum):
    """Статус сохранения."""
    PENDING = "pending"
    SAVING = "saving"
    FAILED = "failed"
    LOADING = "loading"
    CORRUPTED = "corrupted"

class AutoSaveTrigger(str, Enum):
    """Триггеры автоматического сохранения."""
    COMBAT_END = "combat_end"
    CHARACTER_DEATH = "character_death"
    PLAYER_JOIN = "player_join"
    GM_COMMAND = "gm_command"
    PERIODIC = "periodic"

@dataclass
class SaveMetadata:
    """Метаданные сохранения."""
    save_version: int = 1
    engine_version: str = "1.0.0"
    scenario_version: str = "1.0.0"
    room_name: str = ""
    gm_name: str = ""
    game_state: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    saved_at: datetime = field(default_factory=datetime.now)
    game_time_seconds: float = 0.0
    players_count: int = 0
    characters_count: int = 0
    file_size: int = 0
    checksum: str = ""
    autosave_trigger: Optional[str] = None
    description: str = ""
    def to_dict(self) -> dict:
            'save_id': self.save_id,
            'save_version': self.save_version,
            'engine_version': self.engine_version,
            'scenario_version': self.scenario_version,
            'room_name': self.room_name,
            'gm_name': self.gm_name,
            'game_state': self.game_state,
            'created_at': self.created_at.isoformat(),
            'game_time_seconds': self.game_time_seconds,
            'players_count': self.players_count,
            'file_size': self.file_size,
            'is_autosave': self.is_autosave,
            'autosave_trigger': self.autosave_trigger,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SaveMetadata':
        return cls(
            save_id=data.get('save_id', ''),
            save_version=data.get('save_version', 1),
            scenario_version=data.get('scenario_version', '1.0.0'),
            room_id=data.get('room_id', 0),
            room_name=data.get('room_name', ''),
            gm_id=data.get('gm_id', 0),
            gm_name=data.get('gm_name', ''),
            game_state=data.get('game_state', ''),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else datetime.now(),
            saved_at=datetime.fromisoformat(data['saved_at']) if data.get('saved_at') else datetime.now(),
            players_count=data.get('players_count', 0),
            file_size=data.get('file_size', 0),
            checksum=data.get('checksum', ''),
            autosave_trigger=data.get('autosave_trigger'),
            description=data.get('description', '')
        )

@dataclass
    """Полные данные сохранения."""
    metadata: SaveMetadata
    game_state: Dict[str, Any]
    characters: Dict[str, Any]
    combat_system: Dict[str, Any]
    effects: Dict[str, Any]
    inventory: Dict[str, Any]
    event_system: Dict[str, Any]
    dialogue_system: Dict[str, Any]
    
    def to_dict(self) -> dict:
        return {
            'metadata': self.metadata.to_dict(),
            'room_lifecycle': self.room_lifecycle,
            'game_state': self.game_state,
            'characters': self.characters,
            'combat_system': self.combat_system,
            'inventory': self.inventory,
            'event_system': self.event_system,
            'turn_manager': self.turn_manager,
            'custom_data': self.custom_data
    
    def from_dict(cls, data: dict) -> 'SaveData':
            metadata=SaveMetadata.from_dict(data.get('metadata', {})),
            game_state=data.get('game_state', {}),
            scenario_engine=data.get('scenario_engine', {}),
            combat_system=data.get('combat_system', {}),
            inventory=data.get('inventory', {}),
            map_engine=data.get('map_engine', {}),
            turn_manager=data.get('turn_manager', {}),
            custom_data=data.get('custom_data', {})
        )
# ============================================================
# ============================================================

class SaveSystem:
    """
    Универсальная система сохранения и восстановления.
    """
    
    def __init__(self, save_dir: str = "saves", max_autosaves: int = 10):
        self.save_dir = Path(save_dir)
        self._current_save_id: Optional[str] = None
        self._save_lock = asyncio.Lock()
        self._is_saving = False
        
        # Создаём директории
        self.save_dir.mkdir(parents=True, exist_ok=True)
        (self.save_dir / "autosave").mkdir(parents=True, exist_ok=True)
        (self.save_dir / "backup").mkdir(parents=True, exist_ok=True)
        
        # Кэш сохранений
        self._cache: Dict[str, SaveData] = {}
        
        # Подписки на события
        
        # Логирование
        self._logger = self._setup_logger()
        
        self._logger.info(f"Save System initialized. Save directory: {self.save_dir}")
    
    def _setup_logger(self):
        logger = logging.getLogger("save_system")
        return logger
    
    # ===== СОХРАНЕНИЕ =====
    async def save_game(
        self,
        room_id: int,
        data: Dict[str, Any],
        autosave_trigger: Optional[str] = None,
        description: str = "",
    ) -> Optional[SaveMetadata]:
        Сохраняет игру.
        """
        async with self._save_lock:
            if self._is_saving:
                return None
            
            self._is_saving = True
            
            try:
                # Создаём метаданные
                save_id = self._generate_save_id()
                metadata = SaveMetadata(
                    save_id=save_id,
                    room_name=data.get('room_name', ''),
                    gm_id=data.get('gm_id', 0),
                    gm_name=data.get('gm_name', ''),
                    game_state=data.get('game_state', ''),
                    is_autosave=is_autosave,
                    autosave_trigger=autosave_trigger,
                    description=description,
                    tags=tags or []
                
                # Создаём полные данные
                    metadata=metadata,
                    game_state=data.get('game_state', {}),
                    scenario_engine=data.get('scenario_engine', {}),
                    characters=data.get('characters', {}),
                    combat_system=data.get('combat_system', {}),
                    inventory=data.get('inventory', {}),
                    map_engine=data.get('map_engine', {}),
                    turn_manager=data.get('turn_manager', {}),
                    custom_data=data.get('custom_data', {})
                )
                
                # Сериализуем
                
                # Вычисляем контрольную сумму
                metadata.checksum = checksum
                
                # Определяем путь
                
                temp_path = save_path.with_suffix('.tmp')
                await self._write_file(temp_path, serialized)
                
                # Заменяем
                if save_path.exists():
                    backup_path = self.save_dir / "backup" / f"{save_path.name}.backup"
                    shutil.copy(save_path, backup_path)
                os.rename(temp_path, save_path)
                
                # Обновляем метаданные
                self._current_save_id = save_id
                
                # Сохраняем метаданные отдельно
                await self._save_metadata(metadata)
                
                if is_autosave:
                    await self._cleanup_autosaves(room_id)
                self._logger.info(f"Game saved: {save_id} (autosave: {is_autosave})")
                # Уведомляем слушателей
                await self._notify_listeners('save_completed', metadata)
                
                return metadata
            except Exception as e:
                self._logger.error(f"Save failed: {e}")
                return None
                self._is_saving = False
    
    async def save_metadata(self, metadata: SaveMetadata) -> None:
        """Сохраняет метаданные отдельно."""
        pass
    
    # ===== ВОССТАНОВЛЕНИЕ =====
    
    async def load_game(self, save_id: str) -> Optional[SaveData]:
        """
        Загружает игру.
        async with self._load_lock:
                self._logger.warning("Load already in progress")
                return None
            
            self._is_loading = True
            try:
                # Проверяем кэш
                    cache_time = self._cache.get('_cache_time', 0)
                        self._logger.info(f"Loading from cache: {save_id}")
                        return self._cache[save_id]
                # Ищем файл
                if not save_path:
                    self._logger.error(f"Save file not found: {save_id}")
                    return None
                
                serialized = await self._read_file(save_path)
                
                # Проверяем контрольную сумму
                if not self._verify_checksum(serialized):
                    return None
                
                # Десериализуем
                save_data = self._deserialize(serialized)
                # Обновляем метаданные
                save_data.metadata.loaded_at = datetime.now()
                # Кэшируем
                self._cache['_cache_time'] = datetime.now().timestamp()
                
                self._logger.info(f"Game loaded: {save_id}")
                # Уведомляем слушателей
                await self._notify_listeners('load_completed', save_data)
                
                return save_data
            except Exception as e:
                self._logger.error(f"Load failed: {e}")
                await self._notify_listeners('load_failed', str(e))
            finally:
                self._is_loading = False
    async def load_latest_save(self, room_id: int) -> Optional[SaveData]:
        Загружает последнее сохранение для комнаты.
        """
        if not saves:
        
        latest = max(saves, key=lambda s: s.saved_at)
    
    # ===== УПРАВЛЕНИЕ СОХРАНЕНИЯМИ =====
    
    async def get_saves(self, limit: int = 100) -> List[SaveMetadata]:
        Получает список всех сохранений.
        saves = []
        
        # Читаем файлы метаданных
        metadata_dir = self.save_dir / "metadata"
            for meta_file in metadata_dir.glob("*.json"):
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        saves.append(metadata)
                except Exception as e:
        
        # Сортируем по времени
        saves.sort(key=lambda s: s.saved_at, reverse=True)
        return saves[:limit]
    async def get_saves_for_room(self, room_id: int) -> List[SaveMetadata]:
        Получает сохранения для комнаты.
        """
        return [s for s in all_saves if s.room_id == room_id]
    async def delete_save(self, save_id: str) -> bool:
        """
        Удаляет сохранение.
        """
            # Удаляем файл
            save_path = self._find_save_file(save_id)
                save_path.unlink()
            # Удаляем метаданные
            metadata_file = self.save_dir / "metadata" / f"{save_id}.json"
                metadata_file.unlink()
            # Удаляем из кэша
            if save_id in self._cache:
            
            self._logger.info(f"Save deleted: {save_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to delete save: {e}")
    
    async def cleanup_old_saves(self, max_age_days: int = 30) -> int:
        """
        """
        cutoff = datetime.now() - timedelta(days=max_age_days)
        
        for save in saves:
            if save.saved_at < cutoff and save.is_autosave:
                    deleted += 1
        self._logger.info(f"Cleaned up {deleted} old saves")
        return deleted
    
    # ===== ВНУТРЕННИЕ МЕТОДЫ =====
    def _generate_save_id(self) -> str:
        """Генерирует ID сохранения."""
        return f"save_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
    def _get_save_path(self, save_id: str, is_autosave: bool) -> Path:
        """Возвращает путь к файлу сохранения."""
        subdir = "autosave" if is_autosave else "manual"
        return self.save_dir / subdir / f"{save_id}.json.gz"
    def _find_save_file(self, save_id: str) -> Optional[Path]:
        """Находит файл сохранения."""
            path = self.save_dir / subdir / f"{save_id}.json.gz"
                return path
            # Проверяем без сжатия
            path = self.save_dir / subdir / f"{save_id}.json"
            if path.exists():
        return None
    
    def _serialize(self, save_data: SaveData) -> bytes:
        """Сериализует данные."""
        json_str = json.dumps(data, default=str, indent=2)
        
        # Сжимаем
        compressed = gzip.compress(json_str.encode('utf-8'))
    
    def _deserialize(self, data: bytes) -> SaveData:
        # Распаковываем
            json_str = gzip.decompress(data).decode('utf-8')
        except:
            # Возможно, без сжатия
            json_str = data.decode('utf-8')
        data_dict = json.loads(json_str)
        return SaveData.from_dict(data_dict)
    def _calculate_checksum(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
    
    def _verify_checksum(self, data: bytes) -> bool:
        """Проверяет контрольную сумму."""
        # Простая реализация: извлекаем checksum из метаданных
        try:
            json_str = gzip.decompress(data).decode('utf-8')
            data_dict = json.loads(json_str)
            if stored_checksum:
                # Убираем checksum из данных для вычисления
                data_dict['metadata']['checksum'] = ''
                data_without_checksum = gzip.compress(json.dumps(data_dict).encode('utf-8'))
                computed = hashlib.sha256(data_without_checksum).hexdigest()
                return computed == stored_checksum
            return True
        except:
    
        """Асинхронно записывает файл."""
        def sync_write():
            with open(path, 'wb') as f:
                f.write(data)
        await asyncio.get_event_loop().run_in_executor(None, sync_write)
    
    async def _read_file(self, path: Path) -> bytes:
        """Асинхронно читает файл."""
            with open(path, 'rb') as f:
                return f.read()
        return await asyncio.get_event_loop().run_in_executor(None, sync_read)
    async def _cleanup_autosaves(self, room_id: int) -> None:
        """Очищает старые автосохранения."""
        autosaves = [s for s in saves if s.is_autosave]
        if len(autosaves) > self.max_autosaves:
            # Сортируем по времени и удаляем самые старые
            to_delete = autosaves[:-self.max_autosaves]
            for save in to_delete:
                await self.delete_save(save.save_id)
    # ===== СОБЫТИЯ =====
    def on(self, event: str, callback: Callable) -> None:
        """Подписывается на событие."""
            self._listeners[event] = []
    
    def off(self, event: str, callback: Callable) -> None:
        if event in self._listeners:
            self._listeners[event].remove(callback)
    
    async def _notify_listeners(self, event: str, data: Any) -> None:
        if event in self._listeners:
            for listener in self._listeners[event]:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        await listener(data)
                    else:
                        listener(data)
                except Exception as e:

# ============================================================
# 24.3. SNAPSHOT MANAGER
# ============================================================
class SnapshotManager:
    """
    Управление снимками состояния для быстрого восстановления.
    """
    
    def __init__(self, save_system: SaveSystem):
        self.save_system = save_system
        self._logger = logging.getLogger("snapshot_manager")
    def create_snapshot(self, room_id: int, data: Dict[str, Any]) -> str:
        """
        Создаёт снимок состояния.
        """
        snapshot_id = f"snapshot_{room_id}_{datetime.now().timestamp()}"
        self._snapshots[snapshot_id] = {
            'room_id': room_id,
            'created_at': datetime.now()
        }
        
        self._logger.info(f"Snapshot created: {snapshot_id}")
    
    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает снимок.
        return self._snapshots.get(snapshot_id)
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        Удаляет снимок.
        """
        if snapshot_id in self._snapshots:
            del self._snapshots[snapshot_id]
            return True
    
    def clear_room_snapshots(self, room_id: int) -> int:
        """
        Очищает снимки комнаты.
        to_delete = [
            sid for sid, snap in self._snapshots.items()
            if snap['room_id'] == room_id
        ]
        for sid in to_delete:
        return len(to_delete)

# ============================================================
# 24.4. AUTO SAVE MANAGER

class AutoSaveManager:
    """
    Управление автоматическим сохранением.
    """
    
    def __init__(self, save_system: SaveSystem):
        self.save_system = save_system
        self._tasks: Dict[int, asyncio.Task] = {}
        self._enabled: Dict[int, bool] = {}
    
    def enable_autosave(self, room_id: int, interval_seconds: int = 300) -> None:
        Включает автосохранение.
        self._enabled[room_id] = True
        self._intervals[room_id] = interval_seconds
        
        if room_id not in self._tasks or self._tasks[room_id].done():
        
        self._logger.info(f"Autosave enabled for room {room_id}")
    def disable_autosave(self, room_id: int) -> None:
        Отключает автосохранение.
        """
        self._enabled[room_id] = False
        if room_id in self._tasks:
            del self._tasks[room_id]
        
        self._logger.info(f"Autosave disabled for room {room_id}")
    
    async def trigger_autosave(self, room_id: int, trigger: str = "manual") -> bool:
        """
        Принудительно запускает автосохранение.
        # Получаем данные для сохранения
        data = {
            'room_id': room_id,
            'game_state': 'exploration'
        }
        
            room_id,
            is_autosave=True,
            autosave_trigger=trigger
    
    async def _autosave_loop(self, room_id: int) -> None:
        """
        Цикл автосохранения.
        """
        while self._enabled.get(room_id, False):
                await asyncio.sleep(self._intervals.get(room_id, 300))
                
                if not self._enabled.get(room_id, False):
                    break
                
                await self.trigger_autosave(room_id, "time_interval")
                
            except asyncio.CancelledError:
                break
                self._logger.error(f"Autosave loop error: {e}")

# ============================================================
# 24.5. ТЕСТЫ
# ============================================================

async def test_save_system():
    print("\n" + "="*60)
    print("="*60)
    
    # Создаём систему
    save_system = SaveSystem(save_dir="test_saves")
    # Тестовые данные
    test_data = {
        'room_id': 1,
        'room_name': 'Test Room',
        'gm_name': 'Test GM',
        'game_state': 'exploration',
        'room_lifecycle': {
            'players': [{'id': 1, 'name': 'Player1'}]
        },
        'game_state': {
            'state': 'exploration'
        'scenario_engine': {
            'current_scene': 'tavern',
        },
        'characters': {
            '1': {'name': 'Warrior', 'hp': 50},
            '2': {'name': 'Mage', 'hp': 30}
        },
        'combat_system': {},
        'effects': {},
        'inventory': {},
        'map_engine': {},
        'event_system': {},
        'dialogue_system': {},
        'custom_data': {}
    
    print("\n💾 Тест 1: Сохранение игры")
    
    metadata = await save_system.save_game(
        room_id=1,
        data=test_data,
        is_autosave=False,
        description="Test save"
    )
    
        print(f"   ✅ Сохранено: {metadata.save_id}")
        print(f"   Размер: {metadata.file_size} байт")
    
    # Тест 2: Список сохранений
    print("\n📋 Тест 2: Список сохранений")
    
    saves = await save_system.get_saves(limit=10)
    print(f"   Найдено сохранений: {len(saves)}")
        print(f"   - {save.save_id}: {save.room_name} ({save.saved_at})")
    
    # Тест 3: Загрузка
    print("\n📂 Тест 3: Загрузка игры")
    if metadata:
        loaded_data = await save_system.load_game(metadata.save_id)
            print(f"   ✅ Загружено: {loaded_data.metadata.save_id}")
            print(f"   Игроков: {loaded_data.metadata.players_count}")
            print(f"   Персонажей: {loaded_data.metadata.characters_count}")
    
    # Тест 4: Автосохранение
    
    autosave_manager = AutoSaveManager(save_system)
    autosave_manager.enable_autosave(room_id=1, interval_seconds=2)
    
    # Ждём одно автосохранение
    await asyncio.sleep(3)
    
    saves_after = await save_system.get_saves(limit=10)
    autosaves = [s for s in saves_after if s.is_autosave]
    
    autosave_manager.disable_autosave(1)
    
    # Тест 5: Очистка
    
    deleted = await save_system.cleanup_old_saves(max_age_days=0.01)  # Очень маленький срок
    
    print("\n✅ Все тесты пройдены!")
    print("="*60)

# ============================================================
# 24.6. ГЛОБАЛЬНЫЙ ИНСТАНС

save_system = SaveSystem()
autosave_manager = AutoSaveManager(save_system)
snapshot_manager = SnapshotManager(save_system)

# ============================================================
# 24.7. ЗАПУСК ТЕСТОВ
# ============================================================

    asyncio.run(test_save_system())
