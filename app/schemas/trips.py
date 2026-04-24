from pydantic import BaseModel, validator
from typing import Optional, List
from app.models.database import VehicleType, RideStatus, PaymentMethod
from datetime import datetime

# ── Fare Estimate (before booking) ────────────────────────
class FareEstimateRequest(BaseModel):
    pickup_lat   : float
    pickup_lng   : float
    drop_lat     : float
    drop_lng     : float

class FareEstimateResponse(BaseModel):
    bike  : dict
    auto  : dict
    mini  : dict
    sedan : dict
    suv   : dict
    distance_km  : float
    duration_min : int

# ── Book Ride ──────────────────────────────────────────────
class BookRideRequest(BaseModel):
    pickup_address : str
    pickup_lat     : float
    pickup_lng     : float
    drop_address   : str
    drop_lat       : float
    drop_lng       : float
    vehicle_type   : VehicleType
    payment_method : PaymentMethod = PaymentMethod.cash
    promo_code     : str = None

# ── Trip Response ──────────────────────────────────────────
class DriverBasic(BaseModel):
    id           : int
    full_name    : str
    phone        : str
    avg_rating   : float
    vehicle_type : str
    brand        : str
    model        : str
    color        : str
    plate_number : str

    class Config:
        from_attributes = True

class TripOut(BaseModel):
    id               : int
    pickup_address   : str
    pickup_lat       : float
    pickup_lng       : float
    drop_address     : str
    drop_lat         : float
    drop_lng         : float
    vehicle_type     : str
    status           : str
    payment_method   : str
    estimated_fare   : float
    actual_fare      : Optional[float]
    distance_km      : Optional[float]
    duration_min     : Optional[int]
    surge_multiplier : float
    requested_at     : datetime
    accepted_at      : Optional[datetime]
    started_at       : Optional[datetime]
    completed_at     : Optional[datetime]
    cancelled_at     : Optional[datetime]
    cancel_reason    : Optional[str]
    driver           : Optional[DriverBasic] = None

    class Config:
        from_attributes = True

# ── Cancel Ride ────────────────────────────────────────────
class CancelRideRequest(BaseModel):
    reason : Optional[str] = "Cancelled by user"

# ── Rate Trip ──────────────────────────────────────────────
class RateTripRequest(BaseModel):
    score   : int
    comment : Optional[str] = None

    @validator("score")
    def validate_score(cls, v):
        if v < 1 or v > 5:
            raise ValueError("Score must be between 1 and 5")
        return v
