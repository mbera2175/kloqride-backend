from pydantic import BaseModel, validator
from typing import Optional
from app.models.database import VehicleType
from datetime import datetime

class SendOTPRequest(BaseModel):
    phone: str

    @validator("phone")
    def validate_phone(cls, v):
        v = v.strip().replace(" ", "").replace("-", "")
        if not v.lstrip("+").isdigit() or len(v.lstrip("+")) < 10:
            raise ValueError("Invalid phone number")
        return v

# ── OTP Login ──────────────────────────────────────────────
class VerifyOTPLogin(BaseModel):
    phone : str
    otp   : str

# ── Password Login ─────────────────────────────────────────
class PasswordLoginRequest(BaseModel):
    phone    : str
    password : str

# ── Register Rider (OTP + optional password) ──────────────
class RiderRegister(BaseModel):
    phone     : str
    otp       : str
    full_name : str
    email     : Optional[str] = None
    language  : Optional[str] = "bn"
    password  : Optional[str] = None   # optional — user can set password later

    @validator("password")
    def validate_password(cls, v):
        if v and len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

# ── Register Driver (OTP + optional password) ─────────────
class DriverRegister(BaseModel):
    phone          : str
    otp            : str
    full_name      : str
    email          : Optional[str] = None
    language       : Optional[str] = "bn"
    password       : Optional[str] = None
    license_number : str
    license_expiry : str
    city           : Optional[str] = "Bardhaman"
    vehicle_type   : VehicleType
    brand          : str
    model          : str
    color          : str
    plate_number   : str
    year           : int

# ── Set / Change Password ──────────────────────────────────
class SetPasswordRequest(BaseModel):
    phone        : str
    otp          : str          # must verify OTP to set password
    new_password : str

    @validator("new_password")
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

# ── Responses ──────────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token   : str
    token_type     : str = "bearer"
    user_id        : int
    full_name      : str
    role           : str
    language       : str
    is_new_user    : bool = False
    has_password   : bool = False   # tells frontend whether password is set

class UserOut(BaseModel):
    id             : int
    full_name      : str
    phone          : str
    email          : Optional[str]
    role           : str
    language       : str
    wallet_balance : float
    is_verified    : bool
    has_password   : bool = False
    created_at     : datetime

    class Config:
        from_attributes = True
