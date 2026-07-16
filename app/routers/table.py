from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.database import SessionLocal
from app.models import GameTable, Settings, User, Character
from app.core.security import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/join/{link}", response_class=HTMLResponse)
async def join_table(request: Request, link: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/join/{link}", status_code=303)
    db = SessionLocal()
    table = db.query(GameTable).filter_by(link=link, is_active=True).first()
    if not table:
        db.close()
        return templates.TemplateResponse("error.html", {"request": request, "message": "Стол не найден"})
    setting = db.query(Settings).filter_by(id=table.setting_id).first()
    gm = db.query(User).filter_by(id=table.gm_id).first()
    characters = db.query(Character).filter_by(setting_id=table.setting_id, player_id=user.id, is_npc=False).all()
    db.close()
    return templates.TemplateResponse("join_table.html", {
        "request": request,
        "table": table,
        "setting": setting,
        "gm": gm,
        "characters": characters,
        "user": user
    })
