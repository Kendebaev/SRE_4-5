import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import select, String, DateTime, func, Numeric, Integer
from prometheus_fastapi_instrumentator import Instrumentator

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

app = FastAPI(title="Product Service")
Instrumentator().instrument(app).expose(app)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: int = 0

class ProductResponse(ProductCreate):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Auto-seed mock data for the store
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Product))
        if not result.scalars().first():
            seeds = [
                Product(name="Apple",            description="Fresh red apples, 1kg bag",                  price=2.99,    stock=200),
                Product(name="Banana",            description="Organic bananas, bunch of 6",                price=1.49,    stock=150),
                Product(name="USB-C Hub",         description="7-in-1 USB-C hub with HDMI and SD reader",  price=34.99,   stock=40),
                Product(name="Notebook 200pg",    description="A5 lined notebook, 200 pages",              price=4.99,    stock=100),
                Product(name="Coffee Beans 500g", description="Dark roast single-origin coffee beans",     price=12.99,   stock=60),
                Product(name="Wireless Mouse",    description="Ergonomic 2.4GHz wireless mouse",           price=24.99,   stock=35),
                Product(name="Laptop Stand",      description="Adjustable aluminium laptop stand",         price=39.99,   stock=20),
                Product(name="HDMI Cable 2m",     description="4K HDMI 2.0 cable, 2 metres",              price=8.99,    stock=80),
            ]
            session.add_all(seeds)
            await session.commit()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@app.get("/api/products/", response_model=List[ProductResponse])
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    return result.scalars().all()

@app.get("/api/products/{id}", response_model=ProductResponse)
async def get_product(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.post("/api/products/", response_model=ProductResponse, status_code=201)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_db)):
    db_product = Product(**product.dict())
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product

@app.put("/api/products/{id}", response_model=ProductResponse)
async def update_product(id: int, product: ProductCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == id))
    db_product = result.scalars().first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    for var, value in vars(product).items():
        setattr(db_product, var, value) if value else None
        
    await db.commit()
    await db.refresh(db_product)
    return db_product

@app.delete("/api/products/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == id))
    db_product = result.scalars().first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(db_product)
    await db.commit()
    return None

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "product"}
