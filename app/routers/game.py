from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.database import SessionLocal
from app.models import GameTable, Character
from app.core.security import get_current_user

router = APIRouter()

@router.get("/game/{table_link}", response_class=HTMLResponse)
async def game_room(request: Request, table_link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    db = SessionLocal()
    table = db.query(GameTable).filter_by(link=table_link, is_active=True).first()
    if not table:
        db.close()
        return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
    character = db.query(Character).filter_by(player_id=user.id, setting_id=table.setting_id).first()
    db.close()
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Игровая комната</title>
    <style>
    body {{ background: #1a1a2e; color: #eee; font-family: Arial; min-height: 100vh; margin: 0; padding: 20px; }}
    .game-container {{ max-width: 1200px; margin: 0 auto; }}
    .game-header {{ display: flex; justify-content: space-between; align-items: center; padding: 15px 25px; border-bottom: 2px solid #c7a252; }}
    .game-body {{ display: flex; gap: 20px; margin-top: 20px; }}
    .game-map {{ flex: 3; }}
    .game-chat {{ flex: 1; min-width: 250px; }}
    canvas {{ border: 2px solid #4a3528; background: #1a1a2e; width: 100%; }}
    #chatMessages {{ height: 300px; overflow-y: auto; border: 1px solid #4a3528; padding: 10px; background: #0a0a1a; }}
    input {{ width: 100%; padding: 8px; margin-top: 8px; border: none; border-radius: 4px; background: #3a3a4e; color: #fff; }}
    button {{ width: 100%; padding: 8px; margin-top: 5px; border: none; border-radius: 4px; background: #c7a252; color: #1a1a2e; font-weight: bold; cursor: pointer; }}
    .logout-btn {{ color: #ff6b6b; text-decoration: none; }}
    </style>
    </head>
    <body>
    <div class="game-container">
    <div class="game-header">
    <h2>🎲 {table.name}</h2>
    <div>Игрок: {user.login} | Персонаж: {character.name if character else 'Не выбран'}</div>
    <a href="/logout" class="logout-btn">Выйти</a>
    </div>
    <div class="game-body">
    <div class="game-map"><canvas id="gameCanvas" width="800" height="600"></canvas></div>
    <div class="game-chat">
    <div id="chatMessages"></div>
    <input type="text" id="chatInput" placeholder="Введите сообщение...">
    <button onclick="sendMessage()">Отправить</button>
    </div>
    </div>
    </div>
    <script>
    function sendMessage() {{
        const input = document.getElementById('chatInput');
        const messages = document.getElementById('chatMessages');
        if (input.value.trim()) {{
            messages.innerHTML += `<div><strong>Вы:</strong> ${{input.value}}</div>`;
            input.value = '';
            messages.scrollTop = messages.scrollHeight;
        }}
    }}
    </script>
    </body>
    </html>
    """)
