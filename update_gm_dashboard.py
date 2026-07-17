# -------- GM-ПАНЕЛЬ (С КАТЕГОРИЯМИ И АВАТАРКАМИ) --------
@app.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user.id != user_id or user.role != 'gm':
        return RedirectResponse(url="/login", status_code=303)
    
    session = Session()
    settings = session.query(Settings).all()
    tables = session.query(GameTable).filter_by(gm_id=user_id, is_active=True).all()
    session.close()
    
    # Группируем столы по сеттингам
    settings_dict = {}
    for table in tables:
        setting_id = table.setting_id
        if setting_id not in settings_dict:
            setting_name = "Неизвестный"
            for s in settings:
                if s.id == setting_id:
                    setting_name = s.name
                    break
            settings_dict[setting_id] = {"name": setting_name, "tables": []}
        settings_dict[setting_id]["tables"].append(table)
    
    settings_options = ""
    for s in settings:
        settings_options += f'<option value="{s.id}">{s.name}</option>'
    
    # Генерируем HTML для категорий
    categories_html = ""
    if settings_dict:
        for setting_id, data in settings_dict.items():
            # Аватарка сеттинга (из спецсимволов)
            icons = {
                "Викторианский Лондон": "🕯️",
                "Опричники": "⚔️",
                "Кастомный сценарий": "🌌"
            }
            icon = icons.get(data["name"], "🎲")
            setting_name = data["name"]
            
            categories_html += f'''
            <div class="setting-category">
                <div class="category-header">
                    <span class="category-icon">{icon}</span>
                    <span class="category-name">{setting_name}</span>
                    <span class="category-count">({len(data["tables"])})</span>
                </div>
                <div class="tables-grid">
            '''
            for table in data["tables"]:
                categories_html += f'''
                <div class="table-card">
                    <div class="table-icon">🎲</div>
                    <div class="table-info">
                        <div class="table-name">{table.name}</div>
                        <div class="table-link">/join/{table.link}</div>
                    </div>
                    <div class="table-actions">
                        <button onclick="copyLink('/join/{table.link}')" class="btn btn-small" title="Копировать ссылку">📋</button>
                        <button onclick="deleteTable({table.id})" class="btn btn-small btn-danger" title="Удалить стол">🗑️</button>
                    </div>
                </div>
                '''
            categories_html += '''
                </div>
            </div>
            '''
    else:
        categories_html = '<p style="color: #6b4c3b; text-align: center; padding: 30px;">У вас пока нет созданных столов. Нажмите "Создать игру" выше.</p>'
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>GM Панель</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #1a1a2e; color: #eee; font-family: 'Segoe UI', Arial, sans-serif; min-height: 100vh; }}
        .header {{ background: #2a2a3e; padding: 15px 25px; display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #c7a252; }}
        .user-info {{ display: flex; align-items: center; gap: 15px; }}
        .avatar {{ width: 40px; height: 40px; border-radius: 50%; background: #c7a252; color: #1a1a2e; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 18px; }}
        .username {{ font-weight: bold; font-size: 18px; }}
        .role-badge {{ background: #c7a252; color: #1a1a2e; padding: 2px 10px; border-radius: 12px; font-size: 12px; }}
        .logout-btn {{ color: #ff6b6b; text-decoration: none; }}
        .main-content {{ padding: 20px; max-width: 1200px; margin: 0 auto; }}
        .action-panel {{ background: #16162a; padding: 20px; border-radius: 12px; margin-bottom: 20px; display: flex; gap: 15px; flex-wrap: wrap; align-items: center; }}
        .btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; text-decoration: none; transition: all 0.2s; }}
        .btn-primary {{ background: #c7a252; color: #1a1a2e; }}
        .btn-primary:hover {{ background: #f0d5a0; }}
        .btn-small {{ padding: 6px 12px; font-size: 12px; border: none; border-radius: 4px; cursor: pointer; }}
        .btn-danger {{ background: #ff6b6b; color: #fff; }}
        .btn-danger:hover {{ background: #ff4444; }}
        .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); }}
        .modal-content {{ background: #2a2a3e; margin: 10% auto; padding: 30px; width: 400px; border-radius: 12px; }}
        .close {{ float: right; font-size: 28px; cursor: pointer; color: #aaa; }}
        .close:hover {{ color: #fff; }}
        input, select {{ width: 100%; padding: 10px; margin: 10px 0; border: none; border-radius: 6px; font-size: 14px; background: #3a3a4e; color: #fff; }}
        
        .setting-category {{ margin-bottom: 25px; }}
        .category-header {{ display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid #2a2a3e; margin-bottom: 15px; }}
        .category-icon {{ font-size: 24px; }}
        .category-name {{ font-weight: bold; color: #c9a87c; font-size: 18px; }}
        .category-count {{ color: #6b4c3b; font-size: 14px; }}
        .tables-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; margin-left: 20px; }}
        .table-card {{ background: #2a2a3e; border-radius: 12px; padding: 15px; display: flex; align-items: center; gap: 15px; border: 1px solid #3a3a4e; transition: all 0.3s; }}
        .table-card:hover {{ border-color: #c7a252; transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
        .table-icon {{ font-size: 28px; color: #c7a252; }}
        .table-info {{ flex: 1; }}
        .table-name {{ font-weight: bold; color: #c9a87c; }}
        .table-link {{ font-size: 11px; color: #6b4c3b; font-family: monospace; margin-top: 2px; }}
        .table-actions {{ display: flex; gap: 8px; }}
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
    <div class="main-content">
    <div class="action-panel">
    <button onclick="openModal()" class="btn btn-primary"><i class="fas fa-plus"></i> Создать игру</button>
    </div>
    
    {categories_html}
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
                alert('✅ Игра "' + name + '" создана! Ссылка: /join/' + data.link);
                closeModal();
                location.reload();
            }} else {{
                alert('❌ Ошибка: ' + data.message);
            }}
        }})
        .catch(e => alert('Ошибка: ' + e.message));
    }}
    
    function copyLink(link) {{
        const fullLink = window.location.origin + link;
        navigator.clipboard.writeText(fullLink).then(() => {{
            alert('✅ Ссылка скопирована: ' + fullLink);
        }}).catch(() => {{
            alert('📋 Ссылка: ' + fullLink);
        }});
    }}
    
    function deleteTable(tableId) {{
        if (!confirm('Удалить этот стол?')) return;
        fetch('/api/table/delete', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ table_id: tableId }})
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                alert('✅ Стол удалён');
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
