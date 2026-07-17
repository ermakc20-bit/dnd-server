from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, joinedload
from datetime import datetime
import hashlib
import json
import secrets
import os
import uuid
import random
import math
import re
from typing import Dict, Optional, List, Any, Set
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# 1. ENUMS
# ============================================================

class RoomState(str, Enum):
    PREPARATION = "preparation"
    CHARACTER_SELECTION = "character_selection"
    WAITING_FOR_PLAYERS = "waiting_for_players"
    EXPLORATION = "exploration"
    DIALOG = "dialog"
    CHECK = "check"
    COMBAT = "combat"
    CUTSCENE = "cutscene"
    PAUSED = "paused"
    FINISHED = "finished"

class ActionCategory(str, Enum):
    MOVE = "move"
    ATTACK = "attack"
    USE_SKILL = "use_skill"
    USE_ITEM = "use_item"
    TALK = "talk"
    INTERACT = "interact"
    OPEN_DOOR = "open_door"
    READ = "read"
    CHECK = "check"
    CAST_SPELL = "cast_spell"
    DIALOGUE = "dialogue"
    COMBAT_ACTION = "combat_action"
    ADMIN = "admin"

class UIPanelType(str, Enum):
    CHARACTER = "character"
    ACTION_BAR = "action_bar"
    INVENTORY = "inventory"
    DESCRIPTION = "description"
    COMBAT_LOG = "combat_log"
    CHAT = "chat"
    INITIATIVE = "initiative"
    DICE_OVERLAY = "dice_overlay"
    NOTIFICATIONS = "notifications"
    CONTEXT_MENU = "context_menu"
    TOOLTIP = "tooltip"

# ============================================================
# 2. БАЗА ДАННЫХ
# ============================================================

Base = declarative_base()
engine = create_engine('sqlite:///dnd_game.db', connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    login = Column(String, unique=True)
    email = Column(String, unique=True)
    password_hash = Column(String)
    role = Column(String, default='unassigned')
    created_at = Column(DateTime, default=datetime.now)

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), default='')
    nickname = Column(String(100), default='')
    portrait = Column(String(255), default='')
    token = Column(String(255), default='')
    description = Column(Text, default='')
    biography = Column(Text, default='')
    class_name = Column(String(100), default='')
    race = Column(String(100), default='')
    background = Column(String(100), default='')
    alignment = Column(String(50), default='')
    armor_class = Column(Integer, default=10)
    speed = Column(Integer, default=30)
    max_hp = Column(Integer, default=20)
    current_hp = Column(Integer, default=20)
    temporary_hp = Column(Integer, default=0)
    currency = Column(JSON, default='{}')
    stats = Column(JSON, default='{}')
    skills = Column(JSON, default='[]')
    inventory = Column(JSON, default='[]')
    equipment = Column(JSON, default='{}')
    effects = Column(JSON, default='[]')
    player_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'), nullable=True)
    is_npc = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey('users.id'))

class CustomSkill(Base):
    __tablename__ = 'custom_skills'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(255), default='')
    description = Column(Text, default='')
    dice_formula = Column(String(50), default='1d20')
    damage_formula = Column(String(50), default='')
    saving_throw = Column(String(50), default='')
    target_type = Column(String(50), default='single')
    cost_type = Column(String(50), default='action')
    cost_value = Column(Integer, default=1)
    cooldown = Column(Integer, default=0)
    effects = Column(JSON, default='[]')
    animation = Column(String(100), default='')
    created_by = Column(Integer, ForeignKey('users.id'))
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    created_at = Column(DateTime, default=datetime.now)

class GameRoom(Base):
    __tablename__ = 'game_rooms'
    id = Column(Integer, primary_key=True)
    room_id = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, default='')
    gm_id = Column(Integer, ForeignKey('users.id'))
    password_hash = Column(String, nullable=True)
    state = Column(String(20), default=RoomState.PREPARATION)
    max_players = Column(Integer, default=6)
    is_private = Column(Boolean, default=False)
    current_map = Column(String(255), default='')
    current_scene = Column(String(100), default='')
    current_round = Column(Integer, default=0)
    current_turn = Column(Integer, default=0)
    current_player_id = Column(Integer, nullable=True)
    initiative_order = Column(JSON, default='[]')
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    gm = relationship("User", foreign_keys=[gm_id])
    tokens = relationship("GameToken", backref="room", cascade="all, delete-orphan")
    players = relationship("RoomPlayer", backref="room", cascade="all, delete-orphan")
    custom_skills = relationship("CustomSkill", backref="room", cascade="all, delete-orphan")
    characters = relationship("Character", backref="room", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", backref="room", cascade="all, delete-orphan")

class RoomPlayer(Base):
    __tablename__ = 'room_players'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    role = Column(String(20), default='player')
    is_ready = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.now)

class GameToken(Base):
    __tablename__ = 'game_tokens'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    name = Column(String, default='')
    avatar_url = Column(String, default='')
    role = Column(String, default='NPC')
    owner_id = Column(Integer, nullable=True)
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=True)
    x = Column(Float, default=0)
    y = Column(Float, default=0)
    is_visible = Column(Boolean, default=True)
    layer = Column(String, default='common')
    description = Column(String, default='')
    created_at = Column(DateTime, default=datetime.now)

class ActionLog(Base):
    __tablename__ = 'action_logs'
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('game_rooms.id'))
    timestamp = Column(DateTime, default=datetime.now)
    action_type = Column(String(50))
    actor_id = Column(Integer, nullable=True)
    actor_name = Column(String(100), default='')
    character_id = Column(Integer, nullable=True)
    character_name = Column(String(100), default='')
    target_id = Column(Integer, nullable=True)
    target_name = Column(String(100), default='')
    action_data = Column(Text, default='{}')
    roll_result = Column(Text, default='{}')
    result = Column(String(20), default='')
    message = Column(Text, default='')
    visibility = Column(String(20), default='public')
    gm_modified = Column(Boolean, default=False)

# ============================================================
# 3. UI FRAMEWORK (КЛИЕНТСКАЯ ЧАСТЬ В HTML/JS)
# ============================================================

# HTML-шаблон для игрового интерфейса
UI_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>D&D VTT — {{ room.name }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
        /* ===== БАЗОВЫЕ ПЕРЕМЕННЫЕ ===== */
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #2a2a3e;
            --bg-panel: #16162a;
            --bg-hover: #3a3a4e;
            --accent: #c7a252;
            --accent-hover: #f0d5a0;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --border-color: #3a3a4e;
            --shadow: rgba(0,0,0,0.8);
            --radius: 8px;
            --panel-transition: 0.3s ease;
        }

        /* ===== ГЛОБАЛЬНЫЕ СТИЛИ ===== */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Segoe UI', Arial, sans-serif;
            height: 100vh;
            overflow: hidden;
            user-select: none;
        }

        /* ===== GAME CONTAINER ===== */
        .game-container {
            display: grid;
            grid-template-columns: 280px 1fr 320px;
            grid-template-rows: 1fr auto;
            height: 100vh;
            gap: 0;
            background: var(--bg-primary);
        }

        /* ===== ЛЕВАЯ ПАНЕЛЬ ===== */
        .left-panel {
            grid-row: 1 / 2;
            grid-column: 1 / 2;
            background: var(--bg-panel);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 12px;
            gap: 8px;
            overflow-y: auto;
        }

        /* ===== ПАНЕЛЬ ПЕРСОНАЖА ===== */
        .character-panel {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 12px;
            border: 1px solid var(--border-color);
            flex-shrink: 0;
        }
        .character-panel .portrait {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: var(--bg-hover);
            border: 2px solid var(--accent);
            background-size: cover;
            background-position: center;
            flex-shrink: 0;
        }
        .character-panel .info { flex: 1; }
        .character-panel .name { font-weight: bold; color: var(--accent); font-size: 16px; }
        .character-panel .class { font-size: 12px; color: var(--text-secondary); }
        .character-panel .hp-bar {
            height: 6px;
            background: var(--bg-hover);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 4px;
        }
        .character-panel .hp-bar .fill {
            height: 100%;
            background: #4caf50;
            transition: width 0.3s ease;
        }
        .character-panel .hp-text { font-size: 12px; color: var(--text-secondary); }
        .character-panel .effects {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
            margin-top: 4px;
        }
        .character-panel .effect-icon {
            width: 24px;
            height: 24px;
            border-radius: 4px;
            background: var(--bg-hover);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            border: 1px solid var(--border-color);
            position: relative;
        }
        .character-panel .effect-icon .duration {
            position: absolute;
            bottom: -6px;
            right: -6px;
            font-size: 8px;
            background: var(--bg-primary);
            padding: 0 3px;
            border-radius: 2px;
        }

        /* ===== ПАНЕЛЬ ДЕЙСТВИЙ ===== */
        .action-bar {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 8px;
            border: 1px solid var(--border-color);
            flex-shrink: 0;
        }
        .action-bar .actions {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 4px;
        }
        .action-bar .action-btn {
            padding: 6px 4px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-hover);
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
            text-align: center;
        }
        .action-bar .action-btn:hover {
            background: var(--accent);
            color: var(--bg-primary);
            border-color: var(--accent);
        }
        .action-bar .action-btn:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }
        .action-bar .action-btn .icon { font-size: 16px; display: block; }
        .action-bar .action-btn .label { font-size: 9px; }

        /* ===== ПРАВАЯ ПАНЕЛЬ ===== */
        .right-panel {
            grid-row: 1 / 2;
            grid-column: 3 / 4;
            background: var(--bg-panel);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 8px;
            gap: 6px;
            overflow-y: auto;
        }

        /* ===== ЦЕНТРАЛЬНАЯ ОБЛАСТЬ ===== */
        .center-area {
            grid-row: 1 / 2;
            grid-column: 2 / 3;
            position: relative;
            background: var(--bg-primary);
            overflow: hidden;
        }
        .center-area .map-container {
            width: 100%;
            height: 100%;
            background: var(--bg-primary);
            position: relative;
        }
        .center-area .map-container canvas {
            width: 100%;
            height: 100%;
            display: block;
        }

        /* ===== ИНИЦИАТИВА (оверлей) ===== */
        .initiative-overlay {
            position: absolute;
            top: 12px;
            right: 12px;
            background: var(--bg-secondary);
            border-radius: var(--radius);
            padding: 12px;
            border: 1px solid var(--border-color);
            min-width: 200px;
            display: none;
            z-index: 10;
        }
        .initiative-overlay.visible { display: block; }
        .initiative-overlay .title { font-weight: bold; color: var(--accent); font-size: 14px; margin-bottom: 6px; }
        .initiative-overlay .item {
            display: flex;
            justify-content: space-between;
            padding: 3px 6px;
            border-radius: 3px;
            font-size: 12px;
        }
        .initiative-overlay .item.active {
            background: var(--accent);
            color: var(--bg-primary);
        }
        .initiative-overlay .item .turn { font-weight: bold; }

        /* ===== ЧАТ ===== */
        .chat-window {
            flex: 1;
            background: var(--bg-secondary);
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            min-height: 150px;
        }
        .chat-window .header {
            padding: 6px 10px;
            border-bottom: 1px solid var(--border-color);
            font-weight: bold;
            color: var(--accent);
            font-size: 13px;
            display: flex;
            justify-content: space-between;
        }
        .chat-window .messages {
            flex: 1;
            overflow-y: auto;
            padding: 6px 8px;
            font-size: 12px;
            max-height: 300px;
        }
        .chat-window .messages .msg {
            padding: 2px 6px;
            margin-bottom: 2px;
            border-radius: 3px;
        }
        .chat-window .messages .msg.system { color: var(--text-secondary); font-style: italic; }
        .chat-window .messages .msg.player { color: var(--accent); }
        .chat-window .messages .msg.combat { color: #ff6b6b; }
        .chat-window .messages .msg.gm { color: #ffd93d; }
        .chat-window .input-area {
            display: flex;
            padding: 4px;
            border-top: 1px solid var(--border-color);
            gap: 4px;
        }
        .chat-window .input-area input {
            flex: 1;
            padding: 4px 8px;
            border: none;
            border-radius: 3px;
            background: var(--bg-hover);
            color: var(--text-primary);
            font-size: 12px;
        }
        .chat-window .input-area input:focus { outline: 2px solid var(--accent); }
        .chat-window .input-area button {
            padding: 4px 12px;
            border: none;
            border-radius: 3px;
            background: var(--accent);
            color: var(--bg-primary);
            font-weight: bold;
            cursor: pointer;
        }
        .chat-window .input-area button:hover { background: var(--accent-hover); }

        /* ===== DICE OVERLAY ===== */
        .dice-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 1000;
            display: none;
        }
        .dice-overlay.visible { display: block; }
        .dice-overlay .dice-container {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .dice-overlay .die {
            width: 60px;
            height: 60px;
            background: var(--bg-secondary);
            border: 2px solid var(--accent);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: bold;
            color: var(--text-primary);
            animation: dice-roll 0.8s ease-out;
            box-shadow: 0 0 30px rgba(199, 162, 82, 0.3);
        }
        .dice-overlay .die.critical { border-color: #ffd93d; color: #ffd93d; box-shadow: 0 0 40px rgba(255, 217, 61, 0.5); }
        .dice-overlay .die.fumble { border-color: #ff6b6b; color: #ff6b6b; box-shadow: 0 0 40px rgba(255, 107, 107, 0.5); }
        @keyframes dice-roll {
            0% { transform: rotate(0deg) scale(0); opacity: 0; }
            50% { transform: rotate(720deg) scale(1.5); opacity: 1; }
            100% { transform: rotate(0deg) scale(1); opacity: 1; }
        }

        /* ===== УВЕДОМЛЕНИЯ ===== */
        .notifications {
            position: fixed;
            top: 60px;
            right: 12px;
            z-index: 999;
            display: flex;
            flex-direction: column;
            gap: 6px;
            max-width: 320px;
        }
        .notification {
            padding: 10px 14px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            box-shadow: 0 4px 20px var(--shadow);
            animation: slide-in 0.3s ease-out;
            font-size: 13px;
        }
        .notification .title { font-weight: bold; color: var(--accent); }
        .notification .desc { color: var(--text-secondary); font-size: 12px; }
        @keyframes slide-in {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }

        /* ===== КОНТЕКСТНОЕ МЕНЮ ===== */
        .context-menu {
            display: none;
            position: fixed;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 4px 0;
            min-width: 180px;
            z-index: 9999;
            box-shadow: 0 8px 30px var(--shadow);
        }
        .context-menu.visible { display: block; }
        .context-menu .item {
            padding: 6px 14px;
            color: var(--text-primary);
            cursor: pointer;
            font-size: 13px;
            transition: background 0.2s;
        }
        .context-menu .item:hover { background: var(--bg-hover); }
        .context-menu .divider {
            height: 1px;
            background: var(--border-color);
            margin: 4px 8px;
        }

        /* ===== СОСТОЯНИЯ ИНТЕРФЕЙСА ===== */
        .state-indicator {
            position: fixed;
            top: 8px;
            left: 50%;
            transform: translateX(-50%);
            padding: 4px 16px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            z-index: 50;
            background: var(--bg-secondary);
            border: 1px solid var(--accent);
            color: var(--accent);
            pointer-events: none;
        }

        /* ===== АДАПТИВНОСТЬ ===== */
        @media (max-width: 1024px) {
            .game-container {
                grid-template-columns: 220px 1fr 260px;
            }
        }
        @media (max-width: 768px) {
            .game-container {
                grid-template-columns: 1fr;
                grid-template-rows: auto 1fr auto;
            }
            .left-panel, .right-panel {
                display: none;
            }
            .left-panel.mobile-visible, .right-panel.mobile-visible {
                display: flex;
            }
        }

        /* ===== SCROLLBAR ===== */
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: var(--bg-panel); }
        ::-webkit-scrollbar-thumb { background: var(--accent); border-radius: 2px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--accent-hover); }
    </style>
</head>
<body>
    <!-- ИНДИКАТОР СОСТОЯНИЯ -->
    <div class="state-indicator" id="stateIndicator">⏳ {{ room.state }}</div>

    <!-- УВЕДОМЛЕНИЯ -->
    <div class="notifications" id="notifications"></div>

    <!-- DICE OVERLAY -->
    <div class="dice-overlay" id="diceOverlay">
        <div class="dice-container" id="diceContainer"></div>
    </div>

    <!-- КОНТЕКСТНОЕ МЕНЮ -->
    <div class="context-menu" id="contextMenu"></div>

    <!-- ОСНОВНОЙ КОНТЕЙНЕР -->
    <div class="game-container">
        <!-- ЛЕВАЯ ПАНЕЛЬ -->
        <div class="left-panel" id="leftPanel">
            <!-- ПАНЕЛЬ ПЕРСОНАЖА -->
            <div class="character-panel" id="characterPanel">
                <div style="display:flex; gap:10px; align-items:center;">
                    <div class="portrait" id="characterPortrait" style="background-image: url('{{ character.portrait or '/static/images/default_avatar.png' }}');"></div>
                    <div class="info">
                        <div class="name" id="characterName">{{ character.name or 'Без имени' }}</div>
                        <div class="class" id="characterClass">{{ character.class_name or 'Нет класса' }}</div>
                        <div class="hp-text" id="characterHp">❤️ {{ character.current_hp or 0 }}/{{ character.max_hp or 20 }}</div>
                        <div class="hp-bar"><div class="fill" id="characterHpBar" style="width: {{ (character.current_hp or 0) / (character.max_hp or 1) * 100 }}%;"></div></div>
                        <div class="effects" id="characterEffects"></div>
                    </div>
                </div>
            </div>

            <!-- ПАНЕЛЬ ДЕЙСТВИЙ -->
            <div class="action-bar" id="actionBar">
                <div class="actions" id="actionButtons">
                    <button class="action-btn" data-action="attack" onclick="executeAction('attack')">
                        <span class="icon">⚔️</span>
                        <span class="label">Атака</span>
                    </button>
                    <button class="action-btn" data-action="spell" onclick="executeAction('spell')">
                        <span class="icon">🔮</span>
                        <span class="label">Заклинание</span>
                    </button>
                    <button class="action-btn" data-action="heal" onclick="executeAction('heal')">
                        <span class="icon">💚</span>
                        <span class="label">Лечение</span>
                    </button>
                    <button class="action-btn" data-action="skill" onclick="executeAction('skill')">
                        <span class="icon">🎯</span>
                        <span class="label">Навык</span>
                    </button>
                    <button class="action-btn" data-action="item" onclick="executeAction('item')">
                        <span class="icon">📦</span>
                        <span class="label">Предмет</span>
                    </button>
                    <button class="action-btn" data-action="talk" onclick="executeAction('talk')">
                        <span class="icon">💬</span>
                        <span class="label">Диалог</span>
                    </button>
                    <button class="action-btn" data-action="check" onclick="executeAction('check')">
                        <span class="icon">🔍</span>
                        <span class="label">Проверка</span>
                    </button>
                    <button class="action-btn" data-action="inventory" onclick="toggleInventory()">
                        <span class="icon">🎒</span>
                        <span class="label">Инвентарь</span>
                    </button>
                    <button class="action-btn" data-action="description" onclick="toggleDescription()">
                        <span class="icon">📄</span>
                        <span class="label">Описание</span>
                    </button>
                </div>
            </div>
        </div>

        <!-- ЦЕНТРАЛЬНАЯ ОБЛАСТЬ -->
        <div class="center-area">
            <div class="map-container" id="mapContainer">
                <canvas id="mapCanvas"></canvas>
                <!-- Токены будут добавляться динамически -->
                <div id="tokensLayer"></div>
            </div>

            <!-- ИНИЦИАТИВА (оверлей) -->
            <div class="initiative-overlay" id="initiativePanel">
                <div class="title">⚔️ Инициатива</div>
                <div id="initiativeList"></div>
            </div>
        </div>

        <!-- ПРАВАЯ ПАНЕЛЬ -->
        <div class="right-panel" id="rightPanel">
            <!-- ЧАТ -->
            <div class="chat-window" id="chatWindow">
                <div class="header">
                    <span>💬 Чат</span>
                    <span style="font-size:11px;color:var(--text-secondary);" id="chatCount">0</span>
                </div>
                <div class="messages" id="chatMessages"></div>
                <div class="input-area">
                    <input type="text" id="chatInput" placeholder="Сообщение..." onkeydown="if(event.key==='Enter') sendChat()">
                    <button onclick="sendChat()">➤</button>
                </div>
            </div>

            <!-- БОЕВОЙ ЖУРНАЛ -->
            <div class="chat-window" id="combatLog" style="flex:0.7;min-height:100px;">
                <div class="header"><span>📜 Боевой журнал</span></div>
                <div class="messages" id="combatLogMessages" style="max-height:120px;"></div>
            </div>
        </div>
    </div>

    <script>
        // ============================================================
        // 1. UI MANAGER
        // ============================================================

        class UIManager {
            constructor() {
                this.panels = {};
                this.state = '{{ room.state }}';
                this.character = {{ character.to_dict()|tojson if character else '{}' }};
                this.isGm = {{ 'true' if is_gm else 'false' }};
                this.roomId = '{{ room.room_id }}';
                this.ws = null;
                this.initWebSocket();
                this.initEventListeners();
                this.updateUI();
            }

            // ===== WEBSOCKET =====
            initWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                this.ws = new WebSocket(`${protocol}//${window.location.host}/ws/room/${this.roomId}`);
                
                this.ws.onopen = () => {
                    this.addChatMessage('Система', 'Подключено к серверу', 'system');
                };
                
                this.ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.handleWebSocketMessage(data);
                    } catch (e) {
                        console.error('WebSocket error:', e);
                    }
                };
                
                this.ws.onclose = () => {
                    this.addChatMessage('Система', 'Отключено от сервера', 'system');
                };
            }

            handleWebSocketMessage(data) {
                switch(data.type) {
                    case 'room_state_changed':
                        this.state = data.state;
                        this.updateUI();
                        this.showNotification('Состояние игры', `Переход в ${data.state_name}`, 'info');
                        break;
                    case 'chat':
                        this.addChatMessage(data.username, data.text, 'player');
                        break;
                    case 'move':
                        this.updateTokenPosition(data.token_id, data.x, data.y);
                        break;
                    case 'action_result':
                        this.addCombatLog(data.message || 'Действие выполнено', data.result || {});
                        break;
                    case 'character_update':
                        if (data.character_id === this.character.id) {
                            this.character = data.character;
                            this.updateCharacterPanel();
                        }
                        break;
                    case 'roll_result':
                        this.showDiceAnimation(data.results || [], data.total || 0);
                        break;
                    case 'notification':
                        this.showNotification(data.title, data.message, data.type || 'info');
                        break;
                    case 'error':
                        this.showNotification('Ошибка', data.message, 'error');
                        break;
                }
            }

            // ===== UI ОБНОВЛЕНИЯ =====
            updateUI() {
                // Обновляем индикатор состояния
                document.getElementById('stateIndicator').textContent = `🎮 ${this.state}`;
                
                // Обновляем видимость панелей
                this.updatePanelsVisibility();
                
                // Обновляем доступность действий
                this.updateActionsAvailability();
                
                // Обновляем инициативу
                if (this.state === 'combat') {
                    document.getElementById('initiativePanel').classList.add('visible');
                } else {
                    document.getElementById('initiativePanel').classList.remove('visible');
                }
            }

            updatePanelsVisibility() {
                const combatOnly = ['initiativePanel'];
                const explorationOnly = ['actionBar'];
                
                switch(this.state) {
                    case 'combat':
                        document.getElementById('initiativePanel').classList.add('visible');
                        break;
                    default:
                        document.getElementById('initiativePanel').classList.remove('visible');
                        break;
                }
            }

            updateActionsAvailability() {
                const buttons = document.querySelectorAll('.action-btn');
                const disabledStates = ['cutscene', 'paused', 'finished'];
                const isDisabled = disabledStates.includes(this.state);
                
                buttons.forEach(btn => {
                    btn.disabled = isDisabled || (this.state === 'character_selection' && btn.dataset.action !== 'talk');
                });
            }

            // ===== ПАНЕЛЬ ПЕРСОНАЖА =====
            updateCharacterPanel() {
                const c = this.character;
                document.getElementById('characterName').textContent = c.name || 'Без имени';
                document.getElementById('characterClass').textContent = c.class_name || 'Нет класса';
                document.getElementById('characterHp').textContent = `❤️ ${c.current_hp || 0}/${c.max_hp || 20}`;
                
                const hpPercent = ((c.current_hp || 0) / (c.max_hp || 1)) * 100;
                document.getElementById('characterHpBar').style.width = `${Math.min(100, hpPercent)}%`;
                
                if (c.portrait) {
                    document.getElementById('characterPortrait').style.backgroundImage = `url('${c.portrait}')`;
                }
                
                // Эффекты
                const effectsContainer = document.getElementById('characterEffects');
                effectsContainer.innerHTML = '';
                if (c.effects && c.effects.length > 0) {
                    c.effects.forEach(effect => {
                        const el = document.createElement('div');
                        el.className = 'effect-icon';
                        el.innerHTML = `${effect.icon || '✨'}<span class="duration">${effect.remaining_turns || 0}</span>`;
                        el.title = effect.name || 'Эффект';
                        effectsContainer.appendChild(el);
                    });
                }
            }

            // ===== ЧАТ =====
            addChatMessage(username, text, type = 'player') {
                const container = document.getElementById('chatMessages');
                const msg = document.createElement('div');
                msg.className = `msg ${type}`;
                msg.textContent = type === 'system' ? `⚙ ${text}` : `${username}: ${text}`;
                container.appendChild(msg);
                container.scrollTop = container.scrollHeight;
                document.getElementById('chatCount').textContent = container.children.length;
            }

            sendChat() {
                const input = document.getElementById('chatInput');
                const text = input.value.trim();
                if (!text || !this.ws) return;
                
                this.ws.send(JSON.stringify({
                    type: 'chat',
                    text: text,
                    username: '{{ user.login }}',
                    user_id: {{ user.id }}
                }));
                input.value = '';
            }

            // ===== БОЕВОЙ ЖУРНАЛ =====
            addCombatLog(message, data) {
                const container = document.getElementById('combatLogMessages');
                const msg = document.createElement('div');
                msg.className = 'msg combat';
                msg.textContent = `⚔️ ${message}`;
                container.appendChild(msg);
                container.scrollTop = container.scrollHeight;
            }

            // ===== УВЕДОМЛЕНИЯ =====
            showNotification(title, message, type = 'info') {
                const container = document.getElementById('notifications');
                const notif = document.createElement('div');
                notif.className = 'notification';
                notif.innerHTML = `<div class="title">${title}</div><div class="desc">${message}</div>`;
                if (type === 'error') {
                    notif.style.borderColor = '#ff6b6b';
                }
                container.appendChild(notif);
                
                setTimeout(() => {
                    notif.style.opacity = '0';
                    notif.style.transition = 'opacity 0.3s';
                    setTimeout(() => notif.remove(), 300);
                }, 4000);
            }

            // ===== АНИМАЦИЯ КУБИКОВ =====
            showDiceAnimation(results, total) {
                const overlay = document.getElementById('diceOverlay');
                const container = document.getElementById('diceContainer');
                container.innerHTML = '';
                
                results.forEach((result, index) => {
                    const die = document.createElement('div');
                    die.className = 'die';
                    die.textContent = result;
                    if (result === 20) die.classList.add('critical');
                    if (result === 1) die.classList.add('fumble');
                    die.style.animationDelay = `${index * 0.1}s`;
                    container.appendChild(die);
                });
                
                overlay.classList.add('visible');
                
                setTimeout(() => {
                    overlay.classList.remove('visible');
                    container.innerHTML = '';
                }, 3000);
            }

            // ===== ТОКЕНЫ =====
            updateTokenPosition(tokenId, x, y) {
                const token = document.querySelector(`[data-token-id="${tokenId}"]`);
                if (token) {
                    token.style.transform = `translate(${x}px, ${y}px)`;
                }
            }

            // ===== ДЕЙСТВИЯ =====
            executeAction(action) {
                if (!this.ws) return;
                
                this.ws.send(JSON.stringify({
                    type: 'action',
                    action_type: action,
                    user_id: {{ user.id }},
                    character_id: {{ character.id if character else 0 }}
                }));
            }

            // ===== ИНИЦИАЛИЗАЦИЯ =====
            initEventListeners() {
                // Клик по карте для контекстного меню
                document.getElementById('mapContainer').addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    this.showContextMenu(e.clientX, e.clientY);
                });
                
                // Закрытие контекстного меню
                document.addEventListener('click', () => {
                    document.getElementById('contextMenu').classList.remove('visible');
                });
            }

            showContextMenu(x, y) {
                const menu = document.getElementById('contextMenu');
                menu.style.left = `${x}px`;
                menu.style.top = `${y}px`;
                menu.innerHTML = `
                    <div class="item" onclick="uiManager.executeAction('attack')">⚔️ Атаковать</div>
                    <div class="item" onclick="uiManager.executeAction('check')">🔍 Проверить</div>
                    <div class="item" onclick="uiManager.executeAction('talk')">💬 Поговорить</div>
                    <div class="divider"></div>
                    <div class="item" onclick="uiManager.executeAction('interact')">🖐️ Взаимодействовать</div>
                `;
                menu.classList.add('visible');
            }

            // ===== ИНВЕНТАРЬ И ОПИСАНИЕ =====
            toggleInventory() {
                // Открыть инвентарь (в будущем)
                this.showNotification('Инвентарь', 'Открыт инвентарь', 'info');
            }

            toggleDescription() {
                // Открыть описание (в будущем)
                this.showNotification('Описание', 'Открыто описание персонажа', 'info');
            }
        }

        // ============================================================
        // 2. ГЛОБАЛЬНЫЕ ФУНКЦИИ ДЛЯ HTML
        // ============================================================

        let uiManager;

        function executeAction(action) {
            if (uiManager) uiManager.executeAction(action);
        }

        function sendChat() {
            if (uiManager) uiManager.sendChat();
        }

        function toggleInventory() {
            if (uiManager) uiManager.toggleInventory();
        }

        function toggleDescription() {
            if (uiManager) uiManager.toggleDescription();
        }

        // ============================================================
        // 3. ЗАПУСК
        // ============================================================

        document.addEventListener('DOMContentLoaded', () => {
            uiManager = new UIManager();
            uiManager.updateCharacterPanel();
        });
    </script>
</body>
</html>
"""

# ============================================================
# 4. МИГРАЦИЯ
# ============================================================

def migrate_database():
    session = Session()
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if 'game_rooms' not in inspector.get_table_names():
            print("🔄 Создаём таблицы...")
            Base.metadata.create_all(engine)
            print("✅ Таблицы созданы!")
        if 'custom_skills' not in inspector.get_table_names():
            print("🔄 Создаём таблицу Custom Skills...")
            Base.metadata.create_all(engine)
            print("✅ Таблица навыков создана!")
        if 'action_logs' not in inspector.get_table_names():
            print("🔄 Создаём таблицу Action Logs...")
            Base.metadata.create_all(engine)
            print("✅ Таблица логов создана!")
    except Exception as e:
        print(f"⚠️ Ошибка миграции: {e}")
    finally:
        session.close()

Base.metadata.create_all(engine)
migrate_database()

# ============================================================
# 5. FASTAPI
# ============================================================

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AVATAR_DIR = "static/avatars"
MAP_DIR = "static/maps"
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(MAP_DIR, exist_ok=True)

connections = {}

# ============================================================
# 6. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_by_login_or_email(login_or_email):
    session = Session()
    user = session.query(User).filter((User.login == login_or_email) | (User.email == login_or_email)).first()
    session.close()
    return user

def get_user_by_id(user_id):
    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
    session.close()
    return user

def create_user(login, email, password, role='unassigned'):
    session = Session()
    user = User(login=login, email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    return user_id

def get_current_user(request):
    from itsdangerous import URLSafeTimedSerializer
    serializer = URLSafeTimedSerializer("dnd_super_secret_key_2025")
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None
    try:
        data = serializer.loads(session_cookie, max_age=60 * 60 * 24 * 7)
        user_id = data.get("user_id")
        if user_id:
            return get_user_by_id(user_id)
    except:
        return None
    return None

def generate_room_id():
    return secrets.token_urlsafe(8)

# ============================================================
# 7. API
# ============================================================

@app.post("/api/room/create")
async def create_room(request: Request, data: dict):
    user = get_current_user(request)
    if not user or user.role != 'gm':
        return {"success": False, "message": "Только GM может создавать комнаты"}
    
    name = data.get('name', '').strip()
    if not name:
        return {"success": False, "message": "Введите название комнаты"}
    
    session = Session()
    try:
        room_id = generate_room_id()
        room = GameRoom(
            room_id=room_id,
            name=name,
            description=data.get('description', ''),
            gm_id=user.id,
            max_players=data.get('max_players', 6),
            is_private=data.get('is_private', False),
            state=RoomState.PREPARATION
        )
        session.add(room)
        session.commit()
        
        room_player = RoomPlayer(
            room_id=room.id,
            user_id=user.id,
            role='gm',
            is_ready=True
        )
        session.add(room_player)
        session.commit()
        session.refresh(room)
        
        return {
            'success': True,
            'room_id': room.room_id,
            'invite_link': f"/join/{room.room_id}"
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()

@app.get("/room/{room_id}", response_class=HTMLResponse)
async def room_page(request: Request, room_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/room/{room_id}", status_code=303)
    
    session = Session()
    room = session.query(GameRoom).filter_by(room_id=room_id).first()
    if not room:
        session.close()
        return HTMLResponse(content="<h2>❌ Комната не найдена</h2><a href='/'>На главную</a>", status_code=404)
    
    room_player = session.query(RoomPlayer).filter_by(room_id=room.id, user_id=user.id).first()
    if not room_player:
        session.close()
        return HTMLResponse(content="<h2>⛔ Вы не в этой комнате</h2><a href='/'>На главную</a>", status_code=403)
    
    # Получаем персонажа игрока
    character = None
    if room_player.character_id:
        character = session.query(Character).filter_by(id=room_player.character_id).first()
    
    session.close()
    
    # Используем UI шаблон
    from jinja2 import Template
    template = Template(UI_TEMPLATE)
    html = template.render(
        room=room,
        user=user,
        character=character,
        is_gm=room.gm_id == user.id
    )
    
    return HTMLResponse(content=html)

@app.get("/join/{room_id}")
async def join_room(request: Request, room_id: str):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=f"/login?next=/join/{room_id}", status_code=303)
    return RedirectResponse(url=f"/room/{room_id}", status_code=303)

# ============================================================
# 8. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
