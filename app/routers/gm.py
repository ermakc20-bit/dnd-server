from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.database import SessionLocal
from app.models import Settings
from app.core.security import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/gm_dashboard/{user_id}", response_class=HTMLResponse)
async def gm_dashboard(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user.id != user_id or user.role != 'gm':
        return RedirectResponse(url="/login", status_code=303)
    db = SessionLocal()
    settings = db.query(Settings).all()
    db.close()
    return templates.TemplateResponse("gm_dashboard.html", {"request": request, "user": user, "settings": settings})
