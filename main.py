from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()
active_connections = []

@app.get("/")
async def root():
    return {"message": "Добро пожаловать в D&D сервер! Студенческая сборка."}

@app.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    await websocket.accept()
    active_connections.append(websocket)
    await broadcast(f"Игрок {player_name} присоединился к столу!")
    try:
        while True:
            data = await websocket.receive_text()
            await broadcast(f"{player_name}: {data}")
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        await broadcast(f"Игрок {player_name} покинул стол.")

async def broadcast(message: str):
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except:
            pass