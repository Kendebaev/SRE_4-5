"""
=============================================================================
NexShop — Микросервис-шаблон (FastAPI + SQLAlchemy + Prometheus)
=============================================================================

ЗАДАЧА СЕРВИСА (пример): Order Service — создание заказов и сохранение в БД.

ЗАМЕНИ:
  - SERVICE_NAME  → имя сервиса ("order", "payment", "notification", …)
  - /api/orders/  → путь к эндпоинтам
  - Модель Order  → свою ORM-модель

АРХИТЕКТУРНЫЕ РЕШЕНИЯ:
  - Стартап НЕ падает при недоступной БД → сервис запускается,
    но все запросы к БД отдают HTTP 500 (для симуляции инцидента).
  - /health делает реальный SELECT 1 к БД и отдаёт 503, если БД мертва.
    Это важно: Prometheus + Grafana увидят деградацию, не просто "контейнер жив".
  - /metrics экспортирует RED-метрики (Rate, Errors, Duration) через
    prometheus-fastapi-instrumentator автоматически для каждого эндпоинта.
"""

import os
import logging
from datetime import datetime
from typing import List

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import select, String, DateTime, Numeric, Integer, text, func
from prometheus_fastapi_instrumentator import Instrumentator

# ─────────────────────────────────────────────────────────────────────────────
# КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

SERVICE_NAME = "order"      # ← ЗАМЕНИ на своё имя
DATABASE_URL = os.getenv("DATABASE_URL")  # asyncpg-совместимый URL

if not DATABASE_URL:
    # Не падаем — просто логируем. Все запросы к БД вернут 500.
    logger.warning("DATABASE_URL не задан! БД недоступна.")

# ─────────────────────────────────────────────────────────────────────────────
# БД: движок и фабрика сессий
#
# pool_pre_ping=True — SQLAlchemy тестирует соединение перед каждым запросом.
# Если БД упала, выбросит исключение вместо "висячего" запроса.
# ─────────────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    DATABASE_URL or "postgresql+asyncpg://dummy:dummy@localhost/dummy",
    echo=False,
    pool_pre_ping=True,
    pool_size=2,      # Экономим RAM на VDS
    max_overflow=3,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


# ─────────────────────────────────────────────────────────────────────────────
# ORM МОДЕЛЬ
# ─────────────────────────────────────────────────────────────────────────────

class Order(Base):
    """Таблица заказов в PostgreSQL."""
    __tablename__ = "orders"

    id:          Mapped[int]      = mapped_column(primary_key=True, index=True)
    user_id:     Mapped[int]      = mapped_column(Integer, index=True)
    product_id:  Mapped[int]      = mapped_column(Integer, index=True)
    quantity:    Mapped[int]      = mapped_column(Integer, default=1)
    total_price: Mapped[float]    = mapped_column(Numeric(10, 2))
    status:      Mapped[str]      = mapped_column(String(20), default="pending")
    created_at:  Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC СХЕМЫ  (Pydantic v2: model_config вместо class Config)
# ─────────────────────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    """Входящий запрос на создание заказа."""
    user_id:     int
    product_id:  int
    quantity:    int   = 1
    total_price: float

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity должен быть > 0")
        return v

    @field_validator("total_price")
    @classmethod
    def price_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("total_price не может быть отрицательным")
        return v


class OrderStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {"pending", "processing", "shipped", "delivered", "cancelled"}
        if v not in allowed:
            raise ValueError(f"Допустимые статусы: {allowed}")
        return v


class OrderResponse(BaseModel):
    """Ответ API — никогда не раскрываем детали ORM напрямую."""
    id:          int
    user_id:     int
    product_id:  int
    quantity:    int
    total_price: float
    status:      str
    created_at:  datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# ПРИЛОЖЕНИЕ FastAPI
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Order Service",
    description="NexShop — управление заказами",
    version="1.0.0",
)

# Prometheus: автоматически создаёт метрики для каждого эндпоинта.
# .expose(app) добавляет GET /metrics
Instrumentator().instrument(app).expose(app)


# ─────────────────────────────────────────────────────────────────────────────
# ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК
#
# Ловим любой Exception и возвращаем 500, вместо того чтобы упасть.
# Критично для SRE-симуляции: сервис остаётся живым, Prometheus видит ошибки.
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ─────────────────────────────────────────────────────────────────────────────
# LIFECYCLE
#
# Сервис НЕ падает при ошибке БД на старте.
# Это позволяет симулировать инцидент:
#   - контейнер жив, /health → 503
#   - Prometheus продолжает собирать метрики "сервис работает с ошибками"
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup() -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ БД инициализирована, таблицы созданы.")
    except Exception as e:
        # НАМЕРЕННО не re-raise — сервис стартует даже без БД
        logger.error(
            f"✗ Не удалось инициализировать БД при старте "
            f"(ожидаемо при симуляции инцидента): {e}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ЗАВИСИМОСТЬ: сессия БД
# ─────────────────────────────────────────────────────────────────────────────

async def get_db() -> AsyncSession:
    """
    FastAPI Dependency — предоставляет сессию БД.
    При недоступной БД выбрасывает исключение →
    global_exception_handler вернёт HTTP 500.
    """
    async with AsyncSessionLocal() as session:
        yield session


# ─────────────────────────────────────────────────────────────────────────────
# ЭНДПОИНТЫ
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Observability"])
async def health() -> dict:
    """
    Healthcheck — делает SELECT 1 к БД.

    Возвращает 200 если БД доступна, 503 если нет.
    Prometheus интерпретирует 503 как DOWN → алерт в Grafana.
    """
    if not DATABASE_URL:
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "error": "DATABASE_URL not configured"},
        )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "service": SERVICE_NAME}
    except Exception as e:
        logger.error(f"Healthcheck failed — БД недоступна: {e}")
        raise HTTPException(
            status_code=503,
            detail={"status": "unhealthy", "service": SERVICE_NAME, "error": str(e)},
        )


@app.get("/api/orders/", response_model=List[OrderResponse], tags=["Orders"])
async def list_orders(db: AsyncSession = Depends(get_db)) -> List[Order]:
    """Возвращает все заказы из БД."""
    try:
        result = await db.execute(select(Order).order_by(Order.created_at.desc()))
        return result.scalars().all()
    except Exception as e:
        logger.error(f"list_orders error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/{order_id}", response_model=OrderResponse, tags=["Orders"])
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)) -> Order:
    try:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalars().first()
        if not order:
            raise HTTPException(status_code=404, detail=f"Заказ #{order_id} не найден")
        return order
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_order({order_id}) error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/", response_model=OrderResponse, status_code=201, tags=["Orders"])
async def create_order(order: OrderCreate, db: AsyncSession = Depends(get_db)) -> Order:
    """
    Создаёт заказ и сохраняет в БД.
    При недоступной БД вернёт HTTP 500 — ключевое поведение для SRE-симуляции.
    """
    try:
        db_order = Order(**order.model_dump())
        db.add(db_order)
        await db.commit()
        await db.refresh(db_order)
        logger.info(f"Создан заказ #{db_order.id} для user_id={db_order.user_id}")
        return db_order
    except Exception as e:
        await db.rollback()
        logger.error(f"create_order error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/orders/{order_id}/status", response_model=OrderResponse, tags=["Orders"])
async def update_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> Order:
    try:
        result = await db.execute(select(Order).where(Order.id == order_id))
        db_order = result.scalars().first()
        if not db_order:
            raise HTTPException(status_code=404, detail=f"Заказ #{order_id} не найден")
        db_order.status = status_update.status
        await db.commit()
        await db.refresh(db_order)
        logger.info(f"Заказ #{order_id} → статус '{status_update.status}'")
        return db_order
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"update_order_status({order_id}) error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/orders/{order_id}", status_code=204, tags=["Orders"])
async def delete_order(order_id: int, db: AsyncSession = Depends(get_db)) -> None:
    try:
        result = await db.execute(select(Order).where(Order.id == order_id))
        db_order = result.scalars().first()
        if not db_order:
            raise HTTPException(status_code=404, detail=f"Заказ #{order_id} не найден")
        await db.delete(db_order)
        await db.commit()
        logger.info(f"Заказ #{order_id} удалён")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"delete_order({order_id}) error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
