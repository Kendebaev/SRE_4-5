import os
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Payment Service")
Instrumentator().instrument(app).expose(app)

# ── In-memory payment store (no DB dependency for simplicity) ────────────────
payments_db: dict[str, dict] = {}


# ── Schemas ──────────────────────────────────────────────────────────────────
class PaymentRequest(BaseModel):
    order_id: str = Field(description="The order ID this payment is for")
    amount: float = Field(gt=0, description="Payment amount in USD")
    currency: str = Field(default="USD", description="Currency code")
    method: str = Field(default="card", description="Payment method (card, paypal, crypto)")


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    amount: float
    currency: str
    method: str
    status: str
    created_at: str


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "payment"}


@app.post("/api/payments/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(payment: PaymentRequest):
    """Simulate processing a payment. Always succeeds for demo purposes."""
    payment_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    record = {
        "payment_id": payment_id,
        "order_id": payment.order_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "method": payment.method,
        "status": "completed",
        "created_at": now,
    }
    payments_db[payment_id] = record
    return record


@app.get("/api/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str):
    """Retrieve a payment by its ID."""
    record = payments_db.get(payment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Payment not found")
    return record


@app.get("/api/payments/")
async def list_payments():
    """List all payments."""
    return list(payments_db.values())
