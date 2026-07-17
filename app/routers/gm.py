from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.database import SessionLocal
from app.models import Settings
from app.core.security import get_current_user

router = APIRouter()

@router.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user.id != user_id or user.role != 'gm':
        return RedirectResponse(url="/login", status_code=303)
    
    db = SessionLocal()
    settings = db.query(Settings).all()
    db.close()
    
    settings_options = ""
    for s in settings:
        settings_options += f'<option value="{s.id}">{s.name}</option>'
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>GM Панель</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #1a1a2e; color: #eee; font-family: Arial, sans-serif; min-height: 100vh; }}
    .header {{ background: #2a2a3e; padding: 15px 25px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #c7a252; }}
    .user-info {{ display: flex; align-items: center; gap: 15px; }}
    .avatar {{ width: 40px; height: 40px; border-radius: 50%; background: #c7a252; color: #1a1a2e; display: flex; align-items: center; justify-content: center; font-weight: bold; }}
    .username {{ font-weight: bold; font-size: 18px; }}
    .role-badge {{ background: #c7a252; color: #1a1a2e; padding: 2px 10px; border-radius: 12px; font-size: 12px; }}
    .action-panel {{ padding: 20px; display: flex; gap: 15px; flex-wrap: wrap; }}
    .btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; text-decoration: none; transition: all 0.2s; }}
    .btn-primary {{ background: #c7a252; color: #1a1a2e; }}
    .btn-primary:hover {{ background: #f0d5a0; }}
    .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); }}
    .modal-content {{ background: #2a2a3e; margin: 10% auto; padding: 30px; width: 400px; border-radius: 12px; }}
    .close {{ float: right; font-size: 28px; cursor: pointer; color: #aaa; }}
    .close:hover {{ color: #fff; }}
    input, select {{ width: 100%; padding: 10px; margin: 10px 0; border: none; border-radius: 6px; font-size: 14px; background: #3a3a4e; color: #fff; }}
    .logout-btn {{ color: #ff6b6b; text-decoration: none; }}
    </style>
    </head>
    <body>
    <div class="header">
    <div class="user-info">
    <div class="avatar">{user.login[0].upper()}</div>
    <span class="username">{user.login}</span>
    <span class="role-badge">GM</span>
    </div>
    <a href="/logout" class="logout-btn">Выйти</a>
    </div>
    <div class="action-panel">
    <button onclick="openModal()" class="btn btn-primary"><i class="fas fa-plus"></i> Создать игру</button>
    </div>
    <div id="createModal" class="modal">
    <div class="modal-content">
    <span class="close" onclick="closeModal()">&times;</span>
    <h3>Новая игра</h3>
    <input type="text" id="gameName" placeholder="Название игры">
    <select id="gameSetting">
    <option value="">-- Выберите сеттинг --</option>
    {settings_options}
    </select>
    <button onclick="createGame()" class="btn btn-primary" style="width: 100%;">Создать</button>
    </div>
    </div>
    <script>
    function openModal() {{ document.getElementById('createModal').style.display = 'block'; }}
    function closeModal() {{ document.getElementById('createModal').style.display = 'none'; }}
    function createGame() {{
        var name = document.getElementById('gameName').value.trim();
        var settingId = document.getElementById('gameSetting').value;
        if (!name) {{ alert('Введите название'); return; }}
        if (!settingId) {{ alert('Выберите сеттинг'); return; }}
        fetch('/api/table/create', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ name: name, setting_id: parseInt(settingId), gm_id: {user.id} }})
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                alert('✅ Игра создана! Ссылка: /join/' + data.link);
                closeModal();
                location.reload();
            }} else {{
                alert('❌ Ошибка: ' + data.message);
            }}
        }})
        .catch(e => alert('Ошибка: ' + e.message));
    }}
    </script>
    </body>
    </html>
    """)
