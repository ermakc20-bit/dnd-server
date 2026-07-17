from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, joinedload
from datetime import datetime
import hashlib
import json
import secrets
import os
import uuid
from typing import Dict, Optional, List
from dataclasses import dataclass, field

Base = declarative_base()
engine = create_engine('sqlite:///dnd_game.db', connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    login = Column(String, unique=True)
    email = Column(String, unique=True)
    password_hash = Column(String)
    role = Column(String, default='unassigned')
    created_at = Column(DateTime, default=datetime.now)

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    theme = Column(String)
    background_image = Column(String)

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    surname = Column(String(50), default='')
    nickname = Column(String(50), default='')
    avatar = Column(String(255), default='')
    description = Column(Text, default='')
    biography = Column(Text, default='')
    age = Column(Integer, default=0)
    gender = Column(String(20), default='')
    race = Column(String(50), default='')
    class_name = Column(String(50), default='')
    background = Column(String(50), default='')
    alignment = Column(String(20), default='')
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    max_hp = Column(Integer, default=20)
    current_hp = Column(Integer, default=20)
    temporary_hp = Column(Integer, default=0)
    armor_class = Column(Integer, default=12)
    initiative_bonus = Column(Integer, default=0)
    speed = Column(Integer, default=30)
    strength = Column(Integer, default=10)
    dexterity = Column(Integer, default=10)
    constitution = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    wisdom = Column(Integer, default=10)
    charisma = Column(Integer, default=10)
    str_save = Column(Integer, default=0)
    dex_save = Column(Integer, default=0)
    con_save = Column(Integer, default=0)
    int_save = Column(Integer, default=0)
    wis_save = Column(Integer, default=0)
    cha_save = Column(Integer, default=0)
    mana = Column(Integer, default=0)
    energy = Column(Integer, default=0)
    rage = Column(Integer, default=0)
    luck = Column(Integer, default=0)
    inspiration = Column(Boolean, default=False)
    hit_dice = Column(String(10), default='1d8')
    height = Column(Float, default=0.0)
    weight = Column(Float, default=0.0)
    eye_color = Column(String(20), default='')
    hair_color = Column(String(20), default='')
    skin_color = Column(String(20), default='')
    avatar_path = Column(String(255), default='')
    token_path = Column(String(255), default='')
    portrait_path = Column(String(255), default='')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey('users.id'))
    owner = relationship("User", foreign_keys=[created_by])

class CharacterSkill(Base):
    __tablename__ = 'character_skills'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    skill_id = Column(Integer)
    is_prepared = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    cooldown = Column(Integer, default=0)
    character = relationship("Character", backref="skills")

class CharacterInventory(Base):
    __tablename__ = 'character_inventory'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    item_id = Column(Integer)
    quantity = Column(Integer, default=1)
    equipped = Column(Boolean, default=False)
    character = relationship("Character", backref="inventory")

class CharacterEffect(Base):
    __tablename__ = 'character_effects'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'))
    effect_id = Column(Integer)
    duration = Column(Integer, default=0)
    remaining_turns = Column(Integer, default=0)
    stacks = Column(Integer, default=1)
    character = relationship("Character", backref="effects")

class GameTable(Base):
    __tablename__ = 'game_tables'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    gm_id = Column(Integer, ForeignKey('users.id'))
    setting_id = Column(Integer, ForeignKey('settings.id'))
    link = Column(String, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    gm = relationship("User")
    setting = relationship("Settings")
    map_image = Column(String, default='')
    map_x = Column(Float, default=0.0)
    map_y = Column(Float, default=0.0)
    map_width = Column(Float, default=40)
    map_height = Column(Float, default=30)
    map_opacity = Column(Float, default=1.0)
    map_rotation = Column(Float, default=0.0)
    map_layer = Column(String, default='map')

class GameToken(Base):
    __tablename__ = 'game_tokens'
    id = Column(Integer, primary_key=True)
    table_link = Column(String, ForeignKey('game_tables.link'))
    name = Column(String, default='')
    avatar_url = Column(String, default='')
    role = Column(String, default='NPC')
    owner_name = Column(String, default='')
    x = Column(Float, default=0)
    y = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    is_visible = Column(Boolean, default=True)
    layer = Column(String, default='common')
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    table = relationship("GameTable", backref="tokens")
    character = relationship("Character", backref="tokens")
    description = Column(String, default='')
    strength = Column(Integer, default=10)
    dexterity = Column(Integer, default=10)
    constitution = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    wisdom = Column(Integer, default=10)
    charisma = Column(Integer, default=10)
    hp = Column(Integer, default=20)
    max_hp = Column(Integer, default=20)
    ac = Column(Integer, default=12)
    level = Column(Integer, default=1)
    race = Column(String, default='')
    class_name = Column(String, default='')

class PlayerGame(Base):
    __tablename__ = 'player_games'
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('users.id'))
    table_link = Column(String, ForeignKey('game_tables.link'))
    joined_at = Column(DateTime, default=datetime.now)
    player = relationship("User", foreign_keys=[player_id])
    table = relationship("GameTable", foreign_keys=[table_link])

# ===== CHARACTER RUNTIME =====

@dataclass
class CharacterRuntime:
    runtime_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: int = 0
    player_id: int = 0
    table_link: str = ''
    current_hp: int = 20
    temporary_hp: int = 0
    current_ac: int = 12
    initiative: int = 0
    movement_left: int = 30
    mana: int = 0
    energy: int = 0
    rage: int = 0
    luck: int = 0
    inspiration: bool = False
    hit_dice: str = '1d8'
    hit_dice_used: int = 0
    action_used: bool = False
    bonus_action_used: bool = False
    reaction_used: bool = False
    is_alive: bool = True
    is_unconscious: bool = False
    is_concentrating: bool = False
    concentration_spell: str = ''
    visibility: str = 'visible'
    death_saves_success: int = 0
    death_saves_fail: int = 0
    active_effects: List[Dict] = field(default_factory=list)
    cooldowns: Dict[str, int] = field(default_factory=dict)
    conditions: List[str] = field(default_factory=list)
    inventory_runtime: List[Dict] = field(default_factory=list)
    equipped_items: Dict[str, int] = field(default_factory=dict)
    x: float = 0
    y: float = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            'runtime_id': self.runtime_id,
            'character_id': self.character_id,
            'player_id': self.player_id,
            'current_hp': self.current_hp,
            'temporary_hp': self.temporary_hp,
            'current_ac': self.current_ac,
            'initiative': self.initiative,
            'movement_left': self.movement_left,
            'mana': self.mana,
            'energy': self.energy,
            'rage': self.rage,
            'luck': self.luck,
            'inspiration': self.inspiration,
            'hit_dice': self.hit_dice,
            'hit_dice_used': self.hit_dice_used,
            'action_used': self.action_used,
            'bonus_action_used': self.bonus_action_used,
            'reaction_used': self.reaction_used,
            'is_alive': self.is_alive,
            'is_unconscious': self.is_unconscious,
            'is_concentrating': self.is_concentrating,
            'concentration_spell': self.concentration_spell,
            'visibility': self.visibility,
            'death_saves_success': self.death_saves_success,
            'death_saves_fail': self.death_saves_fail,
            'active_effects': self.active_effects,
            'cooldowns': self.cooldowns,
            'conditions': self.conditions,
            'inventory_runtime': self.inventory_runtime,
            'equipped_items': self.equipped_items,
            'x': self.x,
            'y': self.y,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }

    def take_damage(self, damage: int) -> int:
        if self.temporary_hp > 0:
            temp_damage = min(damage, self.temporary_hp)
            self.temporary_hp -= temp_damage
            damage -= temp_damage
            if self.temporary_hp < 0:
                self.temporary_hp = 0
        if damage > 0:
            self.current_hp -= damage
            if self.current_hp < 0:
                self.current_hp = 0
        if self.current_hp <= 0:
            self.is_alive = False
            self.is_unconscious = True
        self.last_updated = datetime.now()
        return damage

    def heal(self, amount: int) -> int:
        max_hp = 20
        old_hp = self.current_hp
        self.current_hp = min(max_hp, self.current_hp + amount)
        if self.current_hp > 0:
            self.is_alive = True
            self.is_unconscious = False
        self.last_updated = datetime.now()
        return self.current_hp - old_hp

    def use_action(self) -> bool:
        if self.action_used:
            return False
        self.action_used = True
        self.last_updated = datetime.now()
        return True

    def use_bonus_action(self) -> bool:
        if self.bonus_action_used:
            return False
        self.bonus_action_used = True
        self.last_updated = datetime.now()
        return True

    def use_reaction(self) -> bool:
        if self.reaction_used:
            return False
        self.reaction_used = True
        self.last_updated = datetime.now()
        return True

    def reset_actions(self):
        self.action_used = False
        self.bonus_action_used = False
        self.reaction_used = False
        self.movement_left = 30
        self.last_updated = datetime.now()

    def start_concentration(self, spell_name: str) -> bool:
        if self.is_concentrating:
            return False
        self.is_concentrating = True
        self.concentration_spell = spell_name
        self.last_updated = datetime.now()
        return True

    def break_concentration(self):
        self.is_concentrating = False
        self.concentration_spell = ''
        self.last_updated = datetime.now()

    def add_condition(self, condition: str):
        if condition not in self.conditions:
            self.conditions.append(condition)
            self.last_updated = datetime.now()

    def remove_condition(self, condition: str):
        if condition in self.conditions:
            self.conditions.remove(condition)
            self.last_updated = datetime.now()


# ===== CHARACTER RUNTIME MANAGER =====

class CharacterRuntimeManager:
    def __init__(self):
        self._runtimes: Dict[str, CharacterRuntime] = {}
        self._character_runtimes: Dict[int, str] = {}
        self._player_runtimes: Dict[int, str] = {}
        self._table_runtimes: Dict[str, List[str]] = {}

    def create_runtime(self, character_id: int, player_id: int, table_link: str) -> CharacterRuntime:
        if character_id in self._character_runtimes:
            return self.get_runtime_by_character(character_id)
        session = Session()
        character = session.query(Character).filter_by(id=character_id).first()
        session.close()
        if not character:
            raise ValueError(f"Character {character_id} not found")
        runtime = CharacterRuntime(
            character_id=character_id,
            player_id=player_id,
            table_link=table_link,
            current_hp=character.current_hp,
            current_ac=character.armor_class,
            mana=character.mana,
            energy=character.energy,
            rage=character.rage,
            luck=character.luck,
            inspiration=character.inspiration,
            hit_dice=character.hit_dice
        )
        self._runtimes[runtime.runtime_id] = runtime
        self._character_runtimes[character_id] = runtime.runtime_id
        self._player_runtimes[player_id] = runtime.runtime_id
        if table_link not in self._table_runtimes:
            self._table_runtimes[table_link] = []
        self._table_runtimes[table_link].append(runtime.runtime_id)
        return runtime

    def get_runtime(self, runtime_id: str) -> Optional[CharacterRuntime]:
        return self._runtimes.get(runtime_id)

    def get_runtime_by_character(self, character_id: int) -> Optional[CharacterRuntime]:
        runtime_id = self._character_runtimes.get(character_id)
        if runtime_id:
            return self._runtimes.get(runtime_id)
        return None

    def get_runtime_by_player(self, player_id: int) -> Optional[CharacterRuntime]:
        runtime_id = self._player_runtimes.get(player_id)
        if runtime_id:
            return self._runtimes.get(runtime_id)
        return None

    def get_table_runtimes(self, table_link: str) -> List[CharacterRuntime]:
        runtime_ids = self._table_runtimes.get(table_link, [])
        return [self._runtimes[rid] for rid in runtime_ids if rid in self._runtimes]

    def update_runtime(self, runtime_id: str, **kwargs) -> Optional[CharacterRuntime]:
        runtime = self._runtimes.get(runtime_id)
        if not runtime:
            return None
        for key, value in kwargs.items():
            if hasattr(runtime, key):
                setattr(runtime, key, value)
        runtime.last_updated = datetime.now()
        return runtime

    def delete_runtime(self, runtime_id: str) -> bool:
        runtime = self._runtimes.pop(runtime_id, None)
        if not runtime:
            return False
        self._character_runtimes.pop(runtime.character_id, None)
        self._player_runtimes.pop(runtime.player_id, None)
        if runtime.table_link in self._table_runtimes:
            self._table_runtimes[runtime.table_link] = [
                rid for rid in self._table_runtimes[runtime.table_link] 
                if rid != runtime_id
            ]
        return True

    def delete_table_runtimes(self, table_link: str):
        runtime_ids = self._table_runtimes.pop(table_link, [])
        for runtime_id in runtime_ids:
            runtime = self._runtimes.pop(runtime_id, None)
            if runtime:
                self._character_runtimes.pop(runtime.character_id, None)
                self._player_runtimes.pop(runtime.player_id, None)

    def save_runtime_to_character(self, runtime_id: str) -> bool:
        runtime = self._runtimes.get(runtime_id)
        if not runtime:
            return False
        session = Session()
        try:
            character = session.query(Character).filter_by(id=runtime.character_id).first()
            if not character:
                return False
            character.current_hp = runtime.current_hp
            character.temporary_hp = runtime.temporary_hp
            character.armor_class = runtime.current_ac
            character.mana = runtime.mana
            character.energy = runtime.energy
            character.rage = runtime.rage
            character.luck = runtime.luck
            character.inspiration = runtime.inspiration
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error saving runtime: {e}")
            return False
        finally:
            session.close()


runtime_manager = CharacterRuntimeManager()

# ===== МИГРАЦИЯ =====

def migrate_database():
    session = Session()
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if 'characters' not in inspector.get_table_names():
            print("🔄 Создаём таблицы системы персонажей...")
            Base.metadata.create_all(engine)
            print("✅ Таблицы созданы!")
        columns = [col['name'] for col in inspector.get_columns('game_tokens')]
        if 'character_id' not in columns:
            print("🔄 Добавляем character_id в game_tokens...")
            session.execute("ALTER TABLE game_tokens ADD COLUMN character_id INTEGER REFERENCES characters(id)")
            session.commit()
            print("✅ Связь добавлена!")
    except Exception as e:
        print(f"⚠️ Ошибка миграции: {e}")
    finally:
        session.close()

Base.metadata.create_all(engine)
migrate_database()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AVATAR_DIR = "static/avatars"
MAP_DIR = "static/maps"
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(MAP_DIR, exist_ok=True)

connections = {}

# -------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_by_login_or_email(login_or_email):
    session = Session()
    user = session.query(User).filter((User.login == login_or_email) | (User.email == login_or_email)).first()
    session.close()
    return user

def get_user_by_id(user_id):
    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
    session.close()
    return user

def create_user(login, email, password, role='unassigned'):
    session = Session()
    user = User(login=login, email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id

def get_current_user(request):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None
    try:
        data = serializer.loads(session_cookie, max_age=60 * 60 * 24 * 7)
        user_id = data.get("user_id")
        if user_id:
            return get_user_by_id(user_id)
    except:
        return None
    return None

def generate_table_link():
    return secrets.token_urlsafe(8)

# ===== API: CHARACTERS =====

@app.post("/api/character/create")
async def create_character(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    session = Session()
    try:
        character = Character(
            name=data.get('name', ''),
            surname=data.get('surname', ''),
            nickname=data.get('nickname', ''),
            avatar=data.get('avatar', ''),
            description=data.get('description', ''),
            biography=data.get('biography', ''),
            age=data.get('age', 0),
            gender=data.get('gender', ''),
            race=data.get('race', ''),
            class_name=data.get('class_name', ''),
            background=data.get('background', ''),
            alignment=data.get('alignment', ''),
            level=data.get('level', 1),
            experience=data.get('experience', 0),
            max_hp=data.get('max_hp', 20),
            current_hp=data.get('current_hp', 20),
            temporary_hp=data.get('temporary_hp', 0),
            armor_class=data.get('armor_class', 12),
            initiative_bonus=data.get('initiative_bonus', 0),
            speed=data.get('speed', 30),
            strength=data.get('strength', 10),
            dexterity=data.get('dexterity', 10),
            constitution=data.get('constitution', 10),
            intelligence=data.get('intelligence', 10),
            wisdom=data.get('wisdom', 10),
            charisma=data.get('charisma', 10),
            str_save=data.get('str_save', 0),
            dex_save=data.get('dex_save', 0),
            con_save=data.get('con_save', 0),
            int_save=data.get('int_save', 0),
            wis_save=data.get('wis_save', 0),
            cha_save=data.get('cha_save', 0),
            mana=data.get('mana', 0),
            energy=data.get('energy', 0),
            rage=data.get('rage', 0),
            luck=data.get('luck', 0),
            inspiration=data.get('inspiration', False),
            hit_dice=data.get('hit_dice', '1d8'),
            created_by=user.id
        )
        session.add(character)
        session.commit()
        return {"success": True, "character_id": character.id}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/character/{character_id}")
async def get_character(character_id: int):
    session = Session()
    try:
        character = session.query(Character).filter_by(id=character_id).first()
        if not character:
            return {"success": False, "message": "Персонаж не найден"}
        return {"success": True, "character": {
            "id": character.id,
            "name": character.name,
            "surname": character.surname,
            "nickname": character.nickname,
            "avatar": character.avatar,
            "description": character.description,
            "biography": character.biography,
            "age": character.age,
            "gender": character.gender,
            "race": character.race,
            "class_name": character.class_name,
            "background": character.background,
            "alignment": character.alignment,
            "level": character.level,
            "experience": character.experience,
            "max_hp": character.max_hp,
            "current_hp": character.current_hp,
            "temporary_hp": character.temporary_hp,
            "armor_class": character.armor_class,
            "initiative_bonus": character.initiative_bonus,
            "speed": character.speed,
            "strength": character.strength,
            "dexterity": character.dexterity,
            "constitution": character.constitution,
            "intelligence": character.intelligence,
            "wisdom": character.wisdom,
            "charisma": character.charisma,
            "str_save": character.str_save,
            "dex_save": character.dex_save,
            "con_save": character.con_save,
            "int_save": character.int_save,
            "wis_save": character.wis_save,
            "cha_save": character.cha_save,
            "mana": character.mana,
            "energy": character.energy,
            "rage": character.rage,
            "luck": character.luck,
            "inspiration": character.inspiration,
            "hit_dice": character.hit_dice
        }}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

# ===== API: CHARACTER RUNTIME =====

@app.post("/api/runtime/create")
async def create_runtime(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    character_id = data.get('character_id')
    table_link = data.get('table_link')
    if not character_id or not table_link:
        return {"success": False, "message": "Не указан character_id или table_link"}
    try:
        runtime = runtime_manager.create_runtime(character_id, user.id, table_link)
        return {"success": True, "runtime_id": runtime.runtime_id, "runtime": runtime.to_dict()}
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/runtime/{runtime_id}")
async def get_runtime(runtime_id: str):
    runtime = runtime_manager.get_runtime(runtime_id)
    if not runtime:
        return {"success": False, "message": "Runtime не найден"}
    return {"success": True, "runtime": runtime.to_dict()}

@app.post("/api/runtime/update")
async def update_runtime(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    runtime_id = data.get('runtime_id')
    if not runtime_id:
        return {"success": False, "message": "Не указан runtime_id"}
    update_data = {k: v for k, v in data.items() if k != 'runtime_id'}
    runtime = runtime_manager.update_runtime(runtime_id, **update_data)
    if not runtime:
        return {"success": False, "message": "Runtime не найден"}
    return {"success": True, "runtime": runtime.to_dict()}

@app.post("/api/runtime/save")
async def save_runtime(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    runtime_id = data.get('runtime_id')
    if not runtime_id:
        return {"success": False, "message": "Не указан runtime_id"}
    success = runtime_manager.save_runtime_to_character(runtime_id)
    if not success:
        return {"success": False, "message": "Не удалось сохранить Runtime"}
    return {"success": True, "message": "Runtime сохранён"}

@app.post("/api/runtime/delete")
async def delete_runtime(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    runtime_id = data.get('runtime_id')
    if not runtime_id:
        return {"success": False, "message": "Не указан runtime_id"}
    success = runtime_manager.delete_runtime(runtime_id)
    if not success:
        return {"success": False, "message": "Runtime не найден"}
    return {"success": True, "message": "Runtime удалён"}

# ===== API: TABLES, TOKENS, MAP =====

@app.post("/api/upload_avatar")
async def upload_avatar(file: UploadFile = File(...)):
    try:
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        filename = f"{secrets.token_hex(8)}.{ext}"
        file_path = os.path.join(AVATAR_DIR, filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"success": True, "url": f"/static/avatars/{filename}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/upload_map")
async def upload_map(request: Request, file: UploadFile = File(...)):
    try:
        user = get_current_user(request)
        if not user or user.role != 'gm':
            return {"success": False, "message": "Доступ только для GM"}
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        filename = f"map_{secrets.token_hex(8)}.{ext}"
        file_path = os.path.join(MAP_DIR, filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"success": True, "url": f"/static/maps/{filename}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/set_map")
async def set_map(data: dict):
    session = Session()
    try:
        table = session.query(GameTable).filter_by(link=data['table_link']).first()
        if not table:
            return {"success": False, "message": "Стол не найден"}
        if 'map_x' in data:
            table.map_x = data['map_x']
        if 'map_y' in data:
            table.map_y = data['map_y']
        if 'map_url' in data:
            table.map_image = data['map_url']
        if 'map_width' in data:
            table.map_width = data['map_width']
        if 'map_height' in data:
            table.map_height = data['map_height']
        if 'map_opacity' in data:
            table.map_opacity = data['map_opacity']
        if 'map_rotation' in data:
            table.map_rotation = data['map_rotation']
        if 'map_layer' in data:
            table.map_layer = data['map_layer']
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'map_update',
                        'map_x': table.map_x,
                        'map_y': table.map_y,
                        'map_url': table.map_image,
                        'map_width': table.map_width,
                        'map_height': table.map_height,
                        'map_opacity': table.map_opacity,
                        'map_rotation': table.map_rotation,
                        'map_layer': table.map_layer
                    }))
                except:
                    pass
        return {"success": True, "message": "Карта обновлена"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/create")
async def create_token(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        return {"success": False, "message": "Не авторизован"}
    session = Session()
    try:
        token = GameToken(
            table_link=data['table_link'],
            name=data.get('name', ''),
            avatar_url=data.get('avatar_url', ''),
            role=data.get('role', 'NPC'),
            owner_name='',
            x=float(data.get('x', 0)),
            y=float(data.get('y', 0)),
            is_visible=True,
            layer=data.get('layer', 'common'),
            description=data.get('description', ''),
            character_id=data.get('character_id', None),
            strength=data.get('strength', 10),
            dexterity=data.get('dexterity', 10),
            constitution=data.get('constitution', 10),
            intelligence=data.get('intelligence', 10),
            wisdom=data.get('wisdom', 10),
            charisma=data.get('charisma', 10),
            hp=data.get('hp', 20),
            max_hp=data.get('max_hp', 20),
            ac=data.get('ac', 12),
            level=data.get('level', 1),
            race=data.get('race', ''),
            class_name=data.get('class_name', '')
        )
        session.add(token)
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_add',
                        'token_id': token.id,
                        'layer': token.layer,
                        'character_id': token.character_id
                    }))
                except:
                    pass
        return {"success": True, "token_id": token.id}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/update")
async def update_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.name = data.get('name', token.name)
        token.avatar_url = data.get('avatar_url', token.avatar_url)
        token.description = data.get('description', token.description)
        token.strength = data.get('strength', token.strength)
        token.dexterity = data.get('dexterity', token.dexterity)
        token.constitution = data.get('constitution', token.constitution)
        token.intelligence = data.get('intelligence', token.intelligence)
        token.wisdom = data.get('wisdom', token.wisdom)
        token.charisma = data.get('charisma', token.charisma)
        token.hp = data.get('hp', token.hp)
        token.max_hp = data.get('max_hp', token.max_hp)
        token.ac = data.get('ac', token.ac)
        token.level = data.get('level', token.level)
        token.race = data.get('race', token.race)
        token.class_name = data.get('class_name', token.class_name)
        if 'character_id' in data:
            token.character_id = data['character_id']
        if 'layer' in data:
            token.layer = data['layer']
        session.commit()
        return {"success": True, "message": "Токен обновлён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/delete")
async def delete_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        session.delete(token)
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_delete',
                        'token_id': data['token_id']
                    }))
                except:
                    pass
        return {"success": True, "message": "Токен удалён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/move")
async def move_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.x = float(data['x'])
        token.y = float(data['y'])
        session.commit()
        return {"success": True, "message": "Токен перемещён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/update_layer")
async def update_token_layer(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.layer = data['layer']
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_layer_update',
                        'token_id': token.id,
                        'layer': token.layer
                    }))
                except:
                    pass
        return {"success": True, "message": "Слой обновлён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/toggle_visibility")
async def toggle_token_visibility(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.is_visible = not token.is_visible
        session.commit()
        if data['table_link'] in connections:
            for ws in connections[data['table_link']]:
                try:
                    await ws.send_text(json.dumps({
                        'type': 'token_visibility',
                        'token_id': token.id,
                        'is_visible': token.is_visible
                    }))
                except:
                    pass
        return {"success": True, "is_visible": token.is_visible}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/token/select")
async def select_token(data: dict):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=data['token_id'], table_link=data['table_link']).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        token.owner_name = data.get('player_name', '')
        session.commit()
        player_game = PlayerGame(
            player_id=data.get('player_id'),
            table_link=data['table_link']
        )
        session.add(player_game)
        session.commit()
        return {"success": True, "message": "Токен выбран"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/api/token/get/{token_id}")
async def get_token(token_id: int):
    session = Session()
    try:
        token = session.query(GameToken).filter_by(id=token_id).first()
        if not token:
            return {"success": False, "message": "Токен не найден"}
        return {"success": True, "token": {
            "id": token.id,
            "name": token.name,
            "avatar_url": token.avatar_url,
            "role": token.role,
            "layer": token.layer,
            "character_id": token.character_id,
            "description": token.description,
            "race": token.race,
            "class_name": token.class_name,
            "level": token.level,
            "strength": token.strength,
            "dexterity": token.dexterity,
            "constitution": token.constitution,
            "intelligence": token.intelligence,
            "wisdom": token.wisdom,
            "charisma": token.charisma,
            "hp": token.hp,
            "max_hp": token.max_hp,
            "ac": token.ac
        }}
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/table/create")
async def create_table(data: dict):
    session = Session()
    try:
        link = generate_table_link()
        table = GameTable(
            name=data['name'],
            gm_id=data['gm_id'],
            setting_id=data['setting_id'],
            link=link,
            map_x=0,
            map_y=0,
            map_width=40,
            map_height=30,
            map_opacity=1.0,
            map_layer='map'
        )
        session.add(table)
        session.commit()
        return {"success": True, "link": link}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.post("/api/table/delete")
async def delete_table(data: dict):
    session = Session()
    try:
        table = session.query(GameTable).filter_by(id=data['table_id']).first()
        if not table:
            return {"success": False, "message": "Стол не найден"}
        table.is_active = False
        session.commit()
        return {"success": True, "message": "Стол удалён"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

def init_libraries():
    session = Session()
    if session.query(Settings).first():
        session.close()
        return
    settings_data = [
        {"name": "Викторианский Лондон", "theme": "victorian_vampire", "description": "Туманный Лондон 1888 года.", "background_image": "/static/images/london_street.jpg"},
        {"name": "Опричники", "theme": "oprichniki_witcher", "description": "Русь, магия, охота на нечисть.", "background_image": "/static/images/campfire.jpg"},
        {"name": "Кастомный сценарий", "theme": "custom", "description": "Своя вселенная.", "background_image": "/static/images/custom_default.jpg"}
    ]
    for data in settings_data:
        setting = Settings(**data)
        session.add(setting)
    session.commit()
    session.close()
    print("✅ Библиотеки инициализированы!")

init_libraries()

# -------- СТРАНИЦЫ --------

@app.get("/")
async def root(request: Request):
    user = get_current_user(request)
    if user:
        if user.role == 'gm':
            return RedirectResponse(url=f"/gm_dashboard/{user.id}", status_code=303)
        else:
            return RedirectResponse(url=f"/player_dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, login_or_email: str = Form(...), password: str = Form(...), next: str = Form("")):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
    user = get_user_by_login_or_email(login_or_email)
    if not user or user.password_hash != hash_password(password):
        return HTMLResponse(content="<h2>❌ Неверный логин/email или пароль</h2><a href='/login'>Вернуться</a>", status_code=400)
    session_token = serializer.dumps({"user_id": user.id})
    if next:
        response = RedirectResponse(url=next, status_code=303)
    elif user.role == 'gm':
        response = RedirectResponse(url=f"/gm_dashboard/{user.id}", status_code=303)
    else:
        response = RedirectResponse(url=f"/player_dashboard", status_code=303)
    response.set_cookie(key="session", value=session_token, httponly=True, max_age=604800)
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, login: str = Form(...), email: str = Form(...), password: str = Form(...), password_confirm: str = Form(...), role: str = Form("unassigned")):
    if password != password_confirm:
        return HTMLResponse(content="<h2>Ошибка: Пароли не совпадают</h2><a href='/register'>Назад</a>", status_code=400)
    if len(password) < 8:
        return HTMLResponse(content="<h2>Ошибка: Пароль должен быть не менее 8 символов</h2><a href='/register'>Назад</a>", status_code=400)
    session = Session()
    if session.query(User).filter_by(login=login).first():
        session.close()
        return HTMLResponse(content="<h2>Ошибка: Логин уже занят</h2><a href='/register'>Назад</a>", status_code=400)
    if session.query(User).filter_by(email=email).first():
        session.close()
        return HTMLResponse(content="<h2>Ошибка: Email уже зарегистрирован</h2><a href='/register'>Назад</a>", status_code=400)
    session.close()
    user_id = create_user(login, email, password, role)
    return RedirectResponse(url="/login?registered=true", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response

@app.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user.id != user_id or user.role != 'gm':
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    try:
        settings = session.query(Settings).all()
        tables = session.query(GameTable).options(joinedload(GameTable.setting)).filter_by(gm_id=user_id, is_active=True).all()
        session.close()
        return templates.TemplateResponse("gm_dashboard.html", {
            "request": request,
            "user": user,
            "settings": settings,
            "tables": tables
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

@app.get("/player_dashboard", response_class=HTMLResponse)
async def player_dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    try:
        player_games = session.query(PlayerGame).filter_by(player_id=user.id).all()
        games = []
        for pg in player_games:
            table = session.query(GameTable).filter_by(link=pg.table_link, is_active=True).first()
            if table:
                setting = session.query(Settings).filter_by(id=table.setting_id).first()
                games.append({
                    "name": table.name,
                    "link": table.link,
                    "setting": setting.name if setting else "Неизвестный",
                    "joined_at": pg.joined_at
                })
        session.close()
        return templates.TemplateResponse("player_dashboard.html", {
            "request": request,
            "user": user,
            "games": games
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

@app.get("/join/{link}", response_class=HTMLResponse)
async def join_table(request: Request, link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/join/{link}", status_code=303)
    session = Session()
    try:
        table = session.query(GameTable).filter_by(link=link, is_active=True).first()
        if not table:
            session.close()
            return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
        if user.role == 'gm' and table.gm_id == user.id:
            session.close()
            return RedirectResponse(url=f"/game/{link}", status_code=303)
        tokens = session.query(GameToken).filter_by(
            table_link=link,
            role='player',
            is_active=True,
            owner_name='',
            is_visible=True,
            layer='common'
        ).all()
        session.close()
        return templates.TemplateResponse("join.html", {
            "request": request,
            "user": user,
            "table": table,
            "tokens": tokens
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

@app.get("/game/{table_link}", response_class=HTMLResponse)
async def game_room(request: Request, table_link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    session = Session()
    try:
        table = session.query(GameTable).filter_by(link=table_link, is_active=True).first()
        if not table:
            session.close()
            return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
        is_gm = user.role == 'gm' and table.gm_id == user.id
        if not is_gm:
            token = session.query(GameToken).filter_by(table_link=table_link, owner_name=user.login, is_active=True).first()
            if not token:
                session.close()
                return HTMLResponse(content="<h2>⛔ У вас нет доступа к этому столу</h2><a href='/'>На главную</a>", status_code=403)
        if is_gm:
            tokens = session.query(GameToken).filter_by(table_link=table_link, is_active=True).all()
        else:
            tokens = session.query(GameToken).filter_by(table_link=table_link, is_active=True, layer='common').all()
        session.close()
        return templates.TemplateResponse("game.html", {
            "request": request,
            "user": user,
            "table": table,
            "tokens": tokens,
            "is_gm": is_gm,
            "map_data": {
                'url': table.map_image,
                'x': table.map_x or 0.0,
                'y': table.map_y or 0.0,
                'width': table.map_width,
                'height': table.map_height,
                'opacity': table.map_opacity,
                'rotation': table.map_rotation or 0.0,
                'layer': table.map_layer or 'map'
            }
        })
    except Exception as e:
        session.close()
        return HTMLResponse(content=f"<h2>Ошибка: {e}</h2>", status_code=500)

# -------- WEBSOCKET --------

@app.websocket("/ws/{table_link}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, table_link: str, player_id: int):
    await websocket.accept()
    if table_link not in connections:
        connections[table_link] = []
    connections[table_link].append(websocket)
    user = get_user_by_id(player_id)
    player_name = user.login if user else str(player_id)
    
    # Создаём Runtime для персонажа
    session = Session()
    token = session.query(GameToken).filter_by(table_link=table_link, owner_name=player_name, is_active=True).first()
    session.close()
    
    if token and token.character_id:
        try:
            runtime = runtime_manager.create_runtime(token.character_id, player_id, table_link)
            await websocket.send_text(json.dumps({
                "type": "runtime_created",
                "runtime": runtime.to_dict()
            }))
        except Exception as e:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Ошибка создания Runtime: {e}"
            }))
    
    await websocket.send_text(json.dumps({"type": "system", "text": f"Добро пожаловать в игру {table_link}, {player_name}!"}))
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get('type') == 'move':
                    session = Session()
                    token = session.query(GameToken).filter_by(id=msg['token_id'], table_link=table_link).first()
                    if token:
                        token.x = msg['x']
                        token.y = msg['y']
                        session.commit()
                    session.close()
                    for ws in connections.get(table_link, []):
                        try:
                            if ws != websocket:
                                await ws.send_text(json.dumps({'type': 'move', 'token_id': msg['token_id'], 'x': msg['x'], 'y': msg['y']}))
                        except:
                            pass
                elif msg.get('type') == 'chat':
                    for ws in connections.get(table_link, []):
                        try:
                            await ws.send_text(json.dumps({'type': 'chat', 'sender': player_name, 'text': msg['text']}))
                        except:
                            pass
            except json.JSONDecodeError:
                for ws in connections.get(table_link, []):
                    try:
                        await ws.send_text(json.dumps({'type': 'chat', 'sender': player_name, 'text': data}))
                    except:
                        pass
    except WebSocketDisconnect:
        if table_link in connections:
            connections[table_link].remove(websocket)
            if not connections[table_link]:
                del connections[table_link]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
