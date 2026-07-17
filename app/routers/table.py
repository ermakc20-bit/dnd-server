from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.database import SessionLocal
from app.models import GameTable, Settings, User, Character
from app.core.security import get_current_user

router = APIRouter()

@router.get("/join/{link}", response_class=HTMLResponse)
async def join_table(request: Request, link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/join/{link}", status_code=303)
    db = SessionLocal()
    table = db.query(GameTable).filter_by(link=link, is_active=True).first()
    if not table:
        db.close()
        return HTMLResponse(content="<h2>❌ Стол не найден</h2><a href='/'>На главную</a>", status_code=404)
    setting = db.query(Settings).filter_by(id=table.setting_id).first()
    gm = db.query(User).filter_by(id=table.gm_id).first()
    characters = db.query(Character).filter_by(setting_id=table.setting_id, player_id=user.id, is_npc=False).all()
    db.close()
    
    characters_html = ""
    for char in characters:
        avatar = char.avatar_url if char.avatar_url else '/static/images/default_avatar.png'
        characters_html += f'''
        <div class="char-card" onclick="selectCharacter({char.id})" data-charid="{char.id}">
            <img src="{avatar}" alt="{char.name}">
            <div class="name">{char.name}</div>
            <div class="class">Lv.{char.level} {char.class_name}</div>
        </div>
        '''
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Присоединение к столу</title>
    <style>
    body {{ background: #1a1a2e; color: #eee; font-family: Arial; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }}
    .box {{ background: #2a2a3e; padding: 40px; border-radius: 12px; width: 500px; text-align: center; }}
    h2 {{ color: #c9a87c; }}
    .info {{ color: #aaa; margin: 10px 0; }}
    .char-grid {{ display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; margin: 20px 0; }}
    .char-card {{ background: #1a1a2e; border-radius: 8px; padding: 15px; width: 120px; cursor: pointer; border: 2px solid transparent; transition: all 0.3s; }}
    .char-card:hover {{ border-color: #c7a252; transform: scale(1.05); }}
    .char-card img {{ width: 80px; height: 80px; border-radius: 50%; object-fit: cover; }}
    .char-card .name {{ font-weight: bold; margin-top: 8px; }}
    .btn {{ background: #c7a252; color: #1a1a2e; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; text-decoration: none; display: inline-block; margin-top: 20px; }}
    .btn:hover {{ background: #f0d5a0; }}
    .btn-secondary {{ background: #6c7a89; color: #fff; }}
    .btn-secondary:hover {{ background: #5a6a7a; }}
    .error-text {{ color: #ff6b6b; }}
    </style>
    </head>
    <body>
    <div class="box">
        <h2>🎲 Присоединение к столу</h2>
        <div class="info"><strong>Стол:</strong> {table.name}</div>
        <div class="info"><strong>Мастер:</strong> {gm.login}</div>
        <div class="info"><strong>Сеттинг:</strong> {setting.name}</div>
        <hr>
    """
    if characters:
        return HTMLResponse(content=f"""
        <p>Выберите персонажа:</p>
        <div class="char-grid">{characters_html}</div>
        <button id="joinBtn" class="btn" onclick="joinGame()" disabled>Войти в игру</button>
        <a href="/player_dashboard/{user.id}/{setting.theme}" class="btn btn-secondary">Создать персонажа</a>
        <script>
        let selectedCharId = null;
        function selectCharacter(id) {{
            document.querySelectorAll('.char-card').forEach(el => el.style.borderColor = 'transparent');
            const card = document.querySelector(`.char-card[data-charid="${{id}}"]`);
            if (card) {{
                card.style.borderColor = '#4caf50';
                selectedCharId = id;
                document.getElementById('joinBtn').disabled = false;
            }}
        }}
        function joinGame() {{
            if (!selectedCharId) return;
            alert('✅ Вход в игру с персонажем ID: ' + selectedCharId + '\\n(Здесь будет игровая комната)');
        }}
        </script>
        """)
    else:
        return HTMLResponse(content=f"""
        <p class="error-text">У вас нет персонажей в этом сеттинге.</p>
        <a href="/player_dashboard/{user.id}/{setting.theme}" class="btn">Создать персонажа</a>
        </div>
        </body>
        </html>
        """)
