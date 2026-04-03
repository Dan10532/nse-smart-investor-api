import json
from typing import List
from fastapi import WebSocket

connections: List[WebSocket] = []


async def broadcast(data: dict):
    if not connections:
        return

    message = json.dumps(data)
    dead = []

    for conn in connections:
        try:
            await conn.send_text(message)
        except Exception:
            # Connection is dead — mark for removal
            dead.append(conn)

    # Clean up dead connections
    for conn in dead:
        try:
            connections.remove(conn)
        except ValueError:
            pass


async def send_to(websocket: WebSocket, data: dict):
    """Send a message to a single specific connection."""
    try:
        await websocket.send_text(json.dumps(data))
    except Exception:
        if websocket in connections:
            connections.remove(websocket)
