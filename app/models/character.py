from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from app.core.database import Base
import datetime

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    player_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=True)
    setting_id = Column(Integer, ForeignKey('settings.id'))
    name = Column(String)
    gender = Column(String)
    class_name = Column(String, default='Воин')
    description = Column(String, default='')
    avatar_url = Column(String, default='')
    level = Column(Integer, default=1)
    strength = Column(Integer, default=10)
    dexterity = Column(Integer, default=10)
    constitution = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    wisdom = Column(Integer, default=10)
    charisma = Column(Integer, default=10)
    hp = Column(Integer, default=20)
    max_hp = Column(Integer, default=20)
    ac = Column(Integer, default=12)
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    is_npc = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
