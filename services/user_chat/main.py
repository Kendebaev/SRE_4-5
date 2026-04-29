import os
from datetime import datetime
from typing import List, Optional, Dict, Set
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import select, String, Integer, DateTime, func
from prometheus_fastapi_instrumentator import Instrumentator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

app = FastAPI(title="User & Chat Service")
Instrumentator().instrument(app).expose(app)

class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ProfileCreate(BaseModel):
    user_id: int
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class ProfileResponse(ProfileCreate):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

# --- Connection Manager for WebSockets ---
class ConnectionManager:
    def __init__(self):
        # Maps room_id -> set of connected WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
        self.active_connections[room_id].add(websocket)
        logger.info(f"Client connected to room {room_id}. Total: {len(self.active_connections[room_id])}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

    async def broadcast(self, message: str, room_id: str):
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                await connection.send_text(message)

manager = ConnectionManager()

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# --- REST Endpoints for Profiles ---
@app.get("/api/users/", response_model=List[ProfileResponse])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile))
    return result.scalars().all()

@app.get("/api/users/{id}", response_model=ProfileResponse)
async def get_profile(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile).where(Profile.id == id))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@app.post("/api/users/", response_model=ProfileResponse, status_code=201)
async def create_profile(profile: ProfileCreate, db: AsyncSession = Depends(get_db)):
    db_profile = Profile(**profile.dict())
    db.add(db_profile)
    await db.commit()
    await db.refresh(db_profile)
    return db_profile

@app.put("/api/users/{id}", response_model=ProfileResponse)
async def update_profile(id: int, profile: ProfileCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile).where(Profile.id == id))
    db_profile = result.scalars().first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    for var, value in vars(profile).items():
        setattr(db_profile, var, value) if value else None
        
    await db.commit()
    await db.refresh(db_profile)
    return db_profile

# --- WebSocket Endpoint for Chat ---
@app.websocket("/api/chat/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Client: {data}", room_id)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        await manager.broadcast("Client left the chat", room_id)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "user_chat"}
