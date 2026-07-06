"""Razorpay billing endpoints."""
import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_permissions
from app.models import Invoice, Organization, PaymentEvent, Subscription, User
from app.schemas import CreateOrderRequest

router = APIRouter(prefix="/billing", tags=["billing"])

PLAN_PRICES_INR = {
    "starter": 4999_00,      # ₹4,999 in paise
    "pro": 14999_00,         # ₹14,999
    "enterprise": 49999_00,  # ₹49,999
}


def _razorpay_client():
    try:
        import razorpay

        return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    except Exception:
        return None


@router.get("/plans")
def list_plans(user: User = Depends(require_permissions("billing.view"))):
    return {
        "plans": [
            {"id": "starter", "name": "Starter", "price_inr": 4999, "features": ["Up to 500 students", "5 modules", "Community support"]},
            {"id": "pro", "name": "Pro", "price_inr": 14999, "features": ["Up to 5,000 students", "All modules", "AI Assistant", "Email support"]},
            {"id": "enterprise", "name": "Enterprise", "price_inr": 49999, "features": ["Unlimited students", "Multi-campus", "Custom SLA", "Dedicated manager"]},
        ]
    }


@router.get("/subscription")
def get_subscription(user: User = Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    sub = db.execute(select(Subscription).where(Subscription.organization_id == user.organization_id)).scalar_one_or_none()
    if not sub:
        return {"subscription": None}
    return {
        "subscription": {
            "id": sub.id,
            "plan": sub.plan,
            "status": sub.status,
            "seats": sub.seats,
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "trial_end": sub.trial_end,
        }
    }


@router.get("/invoices")
def list_invoices(user: User = Depends(require_permissions("billing.view")), db: Session = Depends(get_db)):
    invoices = db.execute(
        select(Invoice).where(Invoice.organization_id == user.organization_id).order_by(Invoice.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": i.id,
            "amount": i.amount / 100.0,
            "currency": i.currency,
            "status": i.status,
            "description": i.description,
            "razorpay_order_id": i.razorpay_order_id,
            "created_at": i.created_at,
        }
        for i in invoices
    ]


@router.post("/orders")
def create_order(body: CreateOrderRequest, user: User = Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    amount = PLAN_PRICES_INR.get(body.plan)
    if not amount:
        raise HTTPException(400, "Invalid plan")

    client = _razorpay_client()
    razorpay_order_id = None
    if client and not settings.RAZORPAY_KEY_ID.endswith("placeholder"):
        try:
            order = client.order.create({"amount": amount, "currency": "INR", "payment_capture": 1})
            razorpay_order_id = order["id"]
        except Exception as exc:  # continue offline; keeps demo usable without keys
            razorpay_order_id = f"order_offline_{exc.__class__.__name__}"

    invoice = Invoice(
        organization_id=user.organization_id,
        razorpay_order_id=razorpay_order_id,
        amount=amount,
        currency="INR",
        status="created",
        description=f"Upgrade to {body.plan}",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return {
        "order_id": razorpay_order_id,
        "invoice_id": invoice.id,
        "amount": amount,
        "currency": "INR",
        "key_id": settings.RAZORPAY_KEY_ID,
        "plan": body.plan,
    }


@router.post("/orders/{invoice_id}/mock-pay")
def mock_pay(invoice_id: str, user: User = Depends(require_permissions("billing.manage")), db: Session = Depends(get_db)):
    """Development-only endpoint to mark an invoice paid without live Razorpay credentials."""
    inv = db.get(Invoice, invoice_id)
    if not inv or inv.organization_id != user.organization_id:
        raise HTTPException(404, "Invoice not found")
    inv.status = "paid"
    inv.razorpay_payment_id = f"pay_mock_{inv.id[:8]}"

    org = db.get(Organization, user.organization_id)
    sub = db.execute(select(Subscription).where(Subscription.organization_id == org.id)).scalar_one_or_none()
    plan_from_desc = (inv.description or "").split("to ")[-1].strip() or "pro"
    if sub:
        sub.plan = plan_from_desc
        sub.status = "active"
    org.plan = plan_from_desc
    db.commit()
    return {"ok": True, "invoice_status": inv.status, "plan": plan_from_desc}


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    secret = settings.RAZORPAY_WEBHOOK_SECRET.encode()
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        # Log but don't crash - webhook secret may be placeholder
        db.add(PaymentEvent(event_type="webhook.invalid_signature", payload={"raw": payload.decode(errors="ignore")[:1000]}))
        db.commit()
        raise HTTPException(400, "Invalid signature")

    import json

    try:
        data = json.loads(payload)
    except Exception:
        raise HTTPException(400, "Invalid payload")
    db.add(PaymentEvent(event_type=data.get("event", "unknown"), payload=data))
    db.commit()
    return {"ok": True}
