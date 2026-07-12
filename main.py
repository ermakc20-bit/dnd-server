from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import json
import datetime
import random
import os

# -------- НАСТРОЙКА БАЗЫ ДАННЫХ --------
Base = declarative_base()
engine = create_engine('sqlite:///dnd_game.db', connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)

class Player(Base):
    __tablename__ = 'players'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    hp = Column(Integer, default=20)
    max_hp = Column(Integer, default=20)
    ac = Column(Integer, default=12)
    level = Column(Integer, default=1)
    x = Column(Integer, default=0)  # Позиция на карте
    y = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.now)

Base.metadata.create_all(engine)

# -------- НАСТРОЙКА СЕРВЕРА --------
app = FastAPI()
active_connections = {}
game_state = {
    "players": {},  # {имя: {hp, max_hp, ac, level, x, y}}
    "initiative": [],  # список имён в порядке хода
    "turn_index": 0,   # текущий игрок в инициативе
    "map_size": 10     # карта 10x10
}

# -------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------
def get_or_create_player(name):
    session = Session()
    player = session.query(Player).filter_by(name=name).first()
    if not player:
        player = Player(name=name)
        session.add(player)
        session.commit()
    session.close()
    return player

def save_player_to_db(name, hp, ac, level, x, y):
    session = Session()
    player = session.query(Player).filter_by(name=name).first()
    if player:
        player.hp = hp
        player.ac = ac
        player.level = level
        player.x = x
        player.y = y
        session.commit()
    session.close()

async def broadcast(message, exclude=None):
    for name, connection in active_connections.items():
        if name != exclude:
            try:
                await connection.send_text(message)
            except:
                pass

def get_map_state():
    """Создаёт текстовое представление карты"""
    size = game_state["map_size"]
    grid = [["⬜" for _ in range(size)] for _ in range(size)]
    
    # Расставляем игроков
    for name, data in game_state["players"].items():
        x, y = data.get("x", 0), data.get("y", 0)
        if 0 <= x < size and 0 <= y < size:
            grid[y][x] = f"👤{name[0]}"
    
    # Добавляем рамку
    result = "```\nКарта:\n"
    result += "   " + " ".join([str(i) for i in range(size)]) + "\n"
    for y, row in enumerate(grid):
        result += f"{y:2} " + " ".join(row) + "\n"
    result += "```"
    return result

# -------- ОСНОВНЫЕ ЭНДПОИНТЫ --------
@app.get("/")
async def root():
    return {"message": "D&D Сервер v3.0 с картой"}

@app.get("/players")
async def get_players():
    session = Session()
    players = session.query(Player).all()
    result = [{"name": p.name, "hp": p.hp, "max_hp": p.max_hp, "ac": p.ac, "level": p.level, "x": p.x, "y": p.y} for p in players]
    session.close()
    return result

@app.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    await websocket.accept()
    
    # Загружаем данные игрока
    player_data = get_or_create_player(player_name)
    
    active_connections[player_name] = websocket
    game_state["players"][player_name] = {
        "hp": player_data.hp,
        "max_hp": player_data.max_hp,
        "ac": player_data.ac,
        "level": player_data.level,
        "x": player_data.x,
        "y": player_data.y
    }
    
    await broadcast(f"Игрок {player_name} присоединился к столу!", exclude=player_name)
    await websocket.send_text(f"👋 Добро пожаловать, {player_name}! HP={player_data.hp}, AC={player_data.ac}, позиция=({player_data.x},{player_data.y})")
    await websocket.send_text(get_map_state())
    
    try:
        while True:
            data = await websocket.receive_text()
            
            # -------- КОМАНДА: БРОСОК КУБИКА --------
            if data.startswith("/roll"):
                parts = data.split()
                if len(parts) >= 2:
                    dice = parts[1]
                    if 'd' in dice:
                        count, sides = dice.split('d')
                        count = int(count) if count else 1
                        sides = int(sides)
                        results = [random.randint(1, sides) for _ in range(count)]
                        total = sum(results)
                        await broadcast(f"🎲 {player_name} бросил {dice}: {results} = {total}")
                    else:
                        await websocket.send_text("❌ Неверный формат. Используй: /roll 2d6")
            
            # -------- КОМАНДА: ИЗМЕНИТЬ HP --------
            elif data.startswith("/hp"):
                parts = data.split()
                if len(parts) == 2:
                    new_hp = int(parts[1])
                    p = game_state["players"][player_name]
                    p["hp"] = max(0, min(p["max_hp"], new_hp))
                    await broadcast(f"❤️ {player_name} изменил HP на {p['hp']}/{p['max_hp']}")
                    save_player_to_db(player_name, p["hp"], p["ac"], p["level"], p["x"], p["y"])
            
            # -------- КОМАНДА: ДВИЖЕНИЕ --------
            elif data.startswith("/move"):
                parts = data.split()
                if len(parts) == 3:
                    try:
                        new_x = int(parts[1])
                        new_y = int(parts[2])
                        size = game_state["map_size"]
                        if 0 <= new_x < size and 0 <= new_y < size:
                            p = game_state["players"][player_name]
                            p["x"] = new_x
                            p["y"] = new_y
                            await broadcast(f"🚶 {player_name} переместился на ({new_x}, {new_y})")
                            await broadcast(get_map_state())
                            save_player_to_db(player_name, p["hp"], p["ac"], p["level"], new_x, new_y)
                        else:
                            await websocket.send_text(f"❌ Координаты должны быть от 0 до {size-1}")
                    except ValueError:
                        await websocket.send_text("❌ Используй: /move X Y (числа)")
            
            # -------- КОМАНДА: ПОКАЗАТЬ КАРТУ --------
            elif data == "/map":
                await websocket.send_text(get_map_state())
            
            # -------- КОМАНДА: СТАТУС --------
            elif data == "/status":
                p = game_state["players"][player_name]
                await websocket.send_text(f"📊 {player_name}: HP={p['hp']}/{p['max_hp']}, AC={p['ac']}, Level={p['level']}, позиция=({p['x']},{p['y']})")
            
            # -------- КОМАНДА: ИНИЦИАТИВА --------
            elif data.startswith("/init"):
                parts = data.split()
                if len(parts) >= 2:
                    # /init +10 (добавить бонус к броску)
                    bonus = int(parts[1]) if len(parts) == 2 else 0
                    roll = random.randint(1, 20) + bonus
                    # Добавляем игрока в инициативу (если ещё нет)
                    if player_name not in game_state["initiative"]:
                        game_state["initiative"].append(player_name)
                    await broadcast(f"⚔️ {player_name} бросил инициативу: {roll} (бонус {bonus})")
            
            elif data == "/init_list":
                # Показать очередь инициативы
                init_list = game_state["initiative"]
                if init_list:
                    current = game_state["turn_index"] % len(init_list)
                    msg = "📋 Инициатива:\n"
                    for i, name in enumerate(init_list):
                        marker = "👉 " if i == current else "   "
                        msg += f"{marker}{i+1}. {name}\n"
                    await websocket.send_text(msg)
                else:
                    await websocket.send_text("📋 Инициатива пуста. Используй /init +бонус")
            
            elif data == "/next":
                # Передать ход следующему
                if game_state["initiative"]:
                    game_state["turn_index"] = (game_state["turn_index"] + 1) % len(game_state["initiative"])
                    current = game_state["initiative"][game_state["turn_index"] % len(game_state["initiative"])]
                    await broadcast(f"⏭️ Ход передан {current}!")
                else:
                    await websocket.send_text("📋 Сначала добавь игроков в инициативу через /init")
            
            # -------- КОМАНДА: ИГРОКИ ОНЛАЙН --------
            elif data == "/players":
                online = ", ".join(active_connections.keys())
                await websocket.send_text(f"👥 Игроки онлайн: {online}")
            
            # -------- КОМАНДА: ПОМОЩЬ --------
            elif data == "/help":
                help_text = """📖 Доступные команды:
/roll 2d6 - бросить кубики
/hp 15 - установить HP
/move X Y - переместиться на карте
/map - показать карту
/status - показать свой статус
/init +бонус - бросить инициативу
/init_list - показать очередь
/next - передать ход
/players - игроки онлайн
/help - эта справка"""
                await websocket.send_text(help_text)
            
            # -------- ОБЫЧНОЕ СООБЩЕНИЕ --------
            else:
                await broadcast(f"💬 {player_name}: {data}")
                
    except WebSocketDisconnect:
        del active_connections[player_name]
        if player_name in game_state["players"]:
            del game_state["players"][player_name]
        if player_name in game_state["initiative"]:
            game_state["initiative"].remove(player_name)
        await broadcast(f"Игрок {player_name} покинул стол.")