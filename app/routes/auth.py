from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.database import get_db, User, Driver, Vehicle, UserRole
from app.schemas.auth import (
    SendOTPRequest, VerifyOTPLogin, PasswordLoginRequest,
    RiderRegister, DriverRegister, SetPasswordRequest,
    TokenResponse, UserOut
)
from app.utils.otp import create_otp, verify_otp
from app.utils.security import hash_password, verify_password, create_access_token
from app.utils.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

def _token_response(user: User, is_new: bool = False) -> TokenResponse:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token = token,
        user_id      = user.id,
        full_name    = user.full_name,
        role         = user.role,
        language     = user.language,
        is_new_user  = is_new,
        has_password = user.password_hash is not None,
    )

# ════════════════════════════════════════════════════════════
#  OTP FLOW
# ════════════════════════════════════════════════════════════

@router.post("/otp/send", summary="Send OTP to phone")
def send_otp(data: SendOTPRequest, db: Session = Depends(get_db)):
    """
    Send a 6-digit OTP via SMS.
    Returns user_exists=true  → show Login screen
    Returns user_exists=false → show Register screen
    """
    user    = db.query(User).filter(User.phone == data.phone).first()
    purpose = "login" if user else "register"
    result  = create_otp(db, data.phone, purpose=purpose, user_id=user.id if user else None)
    result["user_exists"] = user is not None
    result["purpose"]     = purpose
    return result


@router.post("/otp/login", response_model=TokenResponse, summary="Login via OTP")
def otp_login(data: VerifyOTPLogin, db: Session = Depends(get_db)):
    """Verify OTP and log in existing user."""
    try:
        verify_otp(db, data.phone, data.otp, purpose="login")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = db.query(User).filter(User.phone == data.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please register first.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    user.is_verified = True
    db.commit()
    return _token_response(user)


# ════════════════════════════════════════════════════════════
#  PASSWORD FLOW
# ════════════════════════════════════════════════════════════

@router.post("/password/login", response_model=TokenResponse, summary="Login via Password")
def password_login(data: PasswordLoginRequest, db: Session = Depends(get_db)):
    """Login with phone + password."""
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user:
        raise HTTPException(status_code=401, detail="Phone number not registered.")
    if not user.password_hash:
        raise HTTPException(status_code=400, detail="No password set. Please use OTP login.")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    return _token_response(user)


@router.post("/password/set", summary="Set or reset password via OTP")
def set_password(data: SetPasswordRequest, db: Session = Depends(get_db)):
    """
    Set a new password after verifying OTP.
    Works for: first-time password setup OR forgot password reset.
    """
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="Phone not registered.")

    # Verify OTP first (purpose=login so they can always reset)
    try:
        verify_otp(db, data.phone, data.otp, purpose="login")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password set successfully. You can now login with password."}


# ════════════════════════════════════════════════════════════
#  REGISTER
# ════════════════════════════════════════════════════════════

@router.post("/register/rider", response_model=TokenResponse, status_code=201)
def register_rider(data: RiderRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.phone == data.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered. Please login.")
    try:
        verify_otp(db, data.phone, data.otp, purpose="register")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if data.email and db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already in use.")

    user = User(
        full_name     = data.full_name.strip(),
        phone         = data.phone,
        email         = data.email,
        password_hash = hash_password(data.password) if data.password else None,
        role          = UserRole.rider,
        language      = data.language or "bn",
        is_verified   = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user, is_new=True)


@router.post("/register/driver", response_model=TokenResponse, status_code=201)
def register_driver(data: DriverRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.phone == data.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered. Please login.")
    try:
        verify_otp(db, data.phone, data.otp, purpose="register")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        expiry = datetime.strptime(data.license_expiry, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="License expiry must be YYYY-MM-DD")
    if expiry < datetime.utcnow():
        raise HTTPException(status_code=400, detail="License is expired.")
    if db.query(Vehicle).filter(Vehicle.plate_number == data.plate_number.upper()).first():
        raise HTTPException(status_code=400, detail="Vehicle plate already registered.")

    user = User(
        full_name     = data.full_name.strip(),
        phone         = data.phone,
        email         = data.email,
        password_hash = hash_password(data.password) if data.password else None,
        role          = UserRole.driver,
        language      = data.language or "bn",
        is_verified   = True,
    )
    db.add(user)
    db.flush()

    driver = Driver(
        user_id        = user.id,
        license_number = data.license_number.upper(),
        license_expiry = expiry,
        city           = data.city or "Bardhaman",
        is_approved    = False,
    )
    db.add(driver)
    db.flush()

    vehicle = Vehicle(
        driver_id    = driver.id,
        vehicle_type = data.vehicle_type,
        brand        = data.brand.strip(),
        model        = data.model.strip(),
        color        = data.color.strip(),
        plate_number = data.plate_number.upper().strip(),
        year         = data.year,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(user)
    return _token_response(user, is_new=True)


# ════════════════════════════════════════════════════════════
#  PROFILE & DRIVER CONTROLS
# ════════════════════════════════════════════════════════════

@router.get("/me", response_model=UserOut)
def get_my_profile(current_user: User = Depends(get_current_user)):
    current_user.has_password = current_user.password_hash is not None
    return current_user


@router.patch("/driver/toggle-online")
def toggle_online(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can use this.")
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver or not driver.is_approved:
        raise HTTPException(status_code=403, detail="Driver not approved yet.")
    driver.is_online = not driver.is_online
    db.commit()
    return {"is_online": driver.is_online}


@router.patch("/driver/location")
def update_location(lat: float, lng: float, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "driver":
        raise HTTPException(status_code=403, detail="Only drivers can update location.")
    driver = db.query(Driver).filter(Driver.user_id == current_user.id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")
    driver.current_lat = lat
    driver.current_lng = lng
    db.commit()
    return {"message": "Location updated", "lat": lat, "lng": lng}
