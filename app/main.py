from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.database import engine
from app.models import Base
from app.routers import auth, gm, table

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(gm.router)
app.include_router(table.router)

Base.metadata.create_all(bind=engine)
