from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator
from typing import Optional
from datetime import datetime
from app.models.database import get_db, User, PromoCode, PromoUsage, VehicleType
from app.utils.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/promo", tags=["Promo Codes"])

# ── Schemas ───────────────────────────────────────────────
class CreatePromoRequest(BaseModel):
    code           : str
    description    : Optional[str] = None
    discount_type  : str              # "percent" or "flat"
    discount_value : float
    min_fare       : float = 0.0
    max_discount   : Optional[float] = None
    usage_limit    : Optional[int]   = None
    valid_from     : str              # YYYY-MM-DD
    valid_until    : str              # YYYY-MM-DD
    vehicle_type   : Optional[VehicleType] = None

    @validator("discount_type")
    def check_type(cls, v):
        if v not in ["percent", "flat"]:
            raise ValueError("discount_type must be 'percent' or 'flat'")
        return v

    @validator("discount_value")
    def check_value(cls, v):
        if v <= 0:
            raise ValueError("discount_value must be positive")
        return v

class ApplyPromoRequest(BaseModel):
    code         : str
    fare         : float
    vehicle_type : VehicleType


# ── Rider: validate a promo ───────────────────────────────
@router.post("/apply", summary="Check and apply a promo code")
def apply_promo(
    data        : ApplyPromoRequest,
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db)
):
    discount, promo = _validate_promo(db, current_user, data.code, data.fare, data.vehicle_type)
    final_fare = round(max(0, data.fare - discount), 2)
    return {
        "valid"        : True,
        "code"         : promo.code,
        "description"  : promo.description,
        "original_fare": data.fare,
        "discount"     : discount,
        "final_fare"   : final_fare,
    }


# ── Rider: list active promos ─────────────────────────────
@router.get("/active", summary="List available promo codes")
def list_active_promos(
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db)
):
    now    = datetime.utcnow()
    promos = db.query(PromoCode).filter(
        PromoCode.is_active    == True,
        PromoCode.valid_from   <= now,
        PromoCode.valid_until  >= now,
    ).all()
    return [_fmt_promo(p) for p in promos]


# ── Admin: create promo ───────────────────────────────────
@router.post("/admin/create", summary="Admin: create a promo code")
def create_promo(
    data  : CreatePromoRequest,
    admin = Depends(require_admin),
    db    : Session = Depends(get_db)
):
    if db.query(PromoCode).filter(PromoCode.code == data.code.upper()).first():
        raise HTTPException(status_code=400, detail="Promo code already exists.")
    try:
        valid_from  = datetime.strptime(data.valid_from,  "%Y-%m-%d")
        valid_until = datetime.strptime(data.valid_until, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD")

    promo = PromoCode(
        code           = data.code.upper().strip(),
        description    = data.description,
        discount_type  = data.discount_type,
        discount_value = data.discount_value,
        min_fare       = data.min_fare,
        max_discount   = data.max_discount,
        usage_limit    = data.usage_limit,
        valid_from     = valid_from,
        valid_until    = valid_until,
        vehicle_type   = data.vehicle_type,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return {"message": f"Promo '{promo.code}' created!", **_fmt_promo(promo)}


@router.patch("/admin/{promo_id}/deactivate", summary="Admin: deactivate a promo")
def deactivate_promo(promo_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo not found.")
    promo.is_active = False
    db.commit()
    return {"message": f"Promo '{promo.code}' deactivated."}


@router.get("/admin/all", summary="Admin: list all promos with usage stats")
def list_all_promos(admin=Depends(require_admin), db: Session = Depends(get_db)):
    promos = db.query(PromoCode).order_by(PromoCode.created_at.desc()).all()
    return [_fmt_promo(p, admin_view=True) for p in promos]


# ── Internal: validate + record usage ────────────────────
def _validate_promo(db, user, code, fare, vehicle_type) -> tuple:
    """Returns (discount_amount, promo_object). Raises HTTPException on failure."""
    now   = datetime.utcnow()
    promo = db.query(PromoCode).filter(PromoCode.code == code.upper()).first()

    if not promo or not promo.is_active:
        raise HTTPException(status_code=400, detail="Invalid or inactive promo code.")
    if now < promo.valid_from or now > promo.valid_until:
        raise HTTPException(status_code=400, detail="Promo code has expired.")
    if promo.usage_limit and promo.used_count >= promo.usage_limit:
        raise HTTPException(status_code=400, detail="Promo code usage limit reached.")
    if fare < promo.min_fare:
        raise HTTPException(status_code=400, detail=f"Minimum fare ₹{promo.min_fare} required for this promo.")
    if promo.vehicle_type and promo.vehicle_type != vehicle_type:
        raise HTTPException(status_code=400, detail=f"This promo is only valid for {promo.vehicle_type} rides.")

    # Check if user already used this promo
    already_used = db.query(PromoUsage).filter(
        PromoUsage.promo_id == promo.id,
        PromoUsage.user_id  == user.id
    ).first()
    if already_used:
        raise HTTPException(status_code=400, detail="You have already used this promo code.")

    # Calculate discount
    if promo.discount_type == "percent":
        discount = round(fare * promo.discount_value / 100, 2)
        if promo.max_discount:
            discount = min(discount, promo.max_discount)
    else:
        discount = min(promo.discount_value, fare)

    return discount, promo


def record_promo_usage(db, promo, user_id, trip_id=None):
    """Call this after booking is confirmed to record usage."""
    usage = PromoUsage(promo_id=promo.id, user_id=user_id, trip_id=trip_id)
    db.add(usage)
    promo.used_count += 1


def _fmt_promo(p, admin_view=False):
    data = {
        "id"            : p.id,
        "code"          : p.code,
        "description"   : p.description,
        "discount_type" : p.discount_type,
        "discount_value": p.discount_value,
        "min_fare"      : p.min_fare,
        "max_discount"  : p.max_discount,
        "valid_from"    : p.valid_from,
        "valid_until"   : p.valid_until,
        "vehicle_type"  : p.vehicle_type,
        "is_active"     : p.is_active,
    }
    if admin_view:
        data.update({"usage_limit": p.usage_limit, "used_count": p.used_count})
    return data
