import os
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import select, String, DateTime, func
from jose import JWTError, jwt
from prometheus_fastapi_instrumentator import Instrumentator

# ── Config ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY   = os.getenv("SECRET_KEY", "default_secret")
ALGORITHM    = "HS256"

# ── DB setup ─────────────────────────────────────────────────────────────────
engine           = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base             = declarative_base()

# ── ORM model ────────────────────────────────────────────────────────────────
class UserProfile(Base):
    """
    Extended user profile table.
    Auth Service owns the credentials (users table).
    User Service owns the profile data (user_profiles table).
    The 'username' column is the shared key between the two services.
    """
    __tablename__ = "user_profiles"

    id:           Mapped[int]      = mapped_column(primary_key=True, index=True)
    username:     Mapped[str]      = mapped_column(String(50), unique=True, index=True, nullable=False)
    email:        Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name:    Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

# ── Pydantic schemas ──────────────────────────────────────────────────────────
class ProfileOut(BaseModel):
    username:      str
    email:         Optional[str]  = None
    full_name:     Optional[str]  = None
    registered_at: datetime

    model_config = {"from_attributes": True}

class ProfileUpdate(BaseModel):
    email:     Optional[str] = None
    full_name: Optional[str] = None

# ── App & observability ───────────────────────────────────────────────────────
app = FastAPI(title="User Service", description="Profile store for the e-commerce platform")
Instrumentator().instrument(app).expose(app)

bearer_scheme = HTTPBearer()

# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ── Helpers ───────────────────────────────────────────────────────────────────
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def decode_token(token: str) -> str:
    """Decode JWT and return the username ('sub' claim). Raises 401 on failure."""
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return username
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    username = decode_token(credentials.credentials)
    result   = await db.execute(select(UserProfile).where(UserProfile.username == username))
    profile  = result.scalars().first()

    # Auto-provision profile on first authenticated request (lazy creation)
    if profile is None:
        profile = UserProfile(username=username)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    return profile

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/api/users/me", response_model=ProfileOut, summary="Get my profile")
async def get_my_profile(current_user: UserProfile = Depends(get_current_user)):
    """
    Returns the extended profile of the authenticated user.
    Requires a valid Bearer JWT issued by Auth Service.
    """
    return current_user

@app.put("/api/users/me", response_model=ProfileOut, summary="Update my profile")
async def update_my_profile(
    data: ProfileUpdate,
    current_user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update email and/or full_name for the authenticated user.
    """
    if data.email is not None:
        current_user.email = data.email
    if data.full_name is not None:
        current_user.full_name = data.full_name

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user

@app.get("/api/users/", response_model=list[ProfileOut], summary="List all profiles (admin)")
async def list_profiles(db: AsyncSession = Depends(get_db)):
    """Admin endpoint — returns all user profiles (no auth for simplicity in dev)."""
    result   = await db.execute(select(UserProfile))
    profiles = result.scalars().all()
    return profiles

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "user"}
