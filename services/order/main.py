import os
from datetime import datetime
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import select, String, DateTime, func, Numeric, Integer, text
from prometheus_fastapi_instrumentator import Instrumentator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

app = FastAPI(title="Order Service")
Instrumentator().instrument(app).expose(app)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class OrderCreate(BaseModel):
    user_id: int
    product_id: int
    quantity: int
    total_price: float

class OrderStatusUpdate(BaseModel):
    status: str

class OrderResponse(OrderCreate):
    id: int
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

@app.on_event("startup")
async def startup():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database on startup (this is expected during the incident simulation): {e}")

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@app.get("/api/orders/", response_model=List[OrderResponse])
async def list_orders(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order))
    return result.scalars().all()

@app.get("/api/orders/{id}", response_model=OrderResponse)
async def get_order(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == id))
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.post("/api/orders/", response_model=OrderResponse, status_code=201)
async def create_order(order: OrderCreate, db: AsyncSession = Depends(get_db)):
    db_order = Order(**order.dict())
    db.add(db_order)
    await db.commit()
    await db.refresh(db_order)
    return db_order

@app.patch("/api/orders/{id}/status", response_model=OrderResponse)
async def update_order_status(id: int, status_update: OrderStatusUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == id))
    db_order = result.scalars().first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    db_order.status = status_update.status
    await db.commit()
    await db.refresh(db_order)
    return db_order

@app.get("/health")
async def health():
    try:
        # Crucial for incident simulation: Explicitly check DB connection
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "service": "order"}
    except Exception as e:
        logger.error(f"Healthcheck failed: {e}")
        # Return 503 so Prometheus registers the target as unhealthy
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "error": str(e)})
