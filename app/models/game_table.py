from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import datetime

class GameTable(Base):
    __tablename__ = 'game_tables'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    gm_id = Column(Integer, ForeignKey('users.id'))
    setting_id = Column(Integer, ForeignKey('settings.id'))
    link = Column(String, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    gm = relationship("User")
    setting = relationship("Settings")
