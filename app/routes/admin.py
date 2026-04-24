from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional

from app.models.database import (
    get_db, User, Driver, Vehicle, Trip, Rating,
    RideStatus, UserRole, VehicleType
)
from app.utils.dependencies import require_admin
from app.utils.security import hash_password

router = APIRouter(prefix="/admin", tags=["Admin"])


# ════════════════════════════════════════════════════════════
#  DASHBOARD STATS
# ════════════════════════════════════════════════════════════
@router.get("/dashboard", summary="Platform overview stats")
def dashboard(admin=Depends(require_admin), db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)

    total_riders  = db.query(User).filter(User.role == UserRole.rider).count()
    total_drivers = db.query(Driver).count()
    online_drivers= db.query(Driver).filter(Driver.is_online == True).count()
    pending_approval = db.query(Driver).filter(Driver.is_approved == False).count()

    total_trips    = db.query(Trip).count()
    active_trips   = db.query(Trip).filter(Trip.status.in_([
        RideStatus.requested, RideStatus.accepted,
        RideStatus.arrived, RideStatus.started
    ])).count()

    completed_trips = db.query(Trip).filter(Trip.status == RideStatus.completed).count()
    cancelled_trips = db.query(Trip).filter(Trip.status == RideStatus.cancelled).count()

    # Today's stats
    today_trips = db.query(Trip).filter(
        func.date(Trip.requested_at) == today
    ).count()
    today_revenue = db.query(func.sum(Trip.actual_fare)).filter(
        func.date(Trip.completed_at) == today,
        Trip.status == RideStatus.completed
    ).scalar() or 0.0

    # Month stats
    month_revenue = db.query(func.sum(Trip.actual_fare)).filter(
        Trip.requested_at >= month_start,
        Trip.status == RideStatus.completed
    ).scalar() or 0.0

    total_revenue = db.query(func.sum(Trip.actual_fare)).filter(
        Trip.status == RideStatus.completed
    ).scalar() or 0.0

    completion_rate = round((completed_trips / total_trips * 100), 1) if total_trips else 0

    return {
        "users": {
            "total_riders"     : total_riders,
            "total_drivers"    : total_drivers,
            "online_drivers"   : online_drivers,
            "pending_approval" : pending_approval,
        },
        "trips": {
            "total"           : total_trips,
            "active_now"      : active_trips,
            "completed"       : completed_trips,
            "cancelled"       : cancelled_trips,
            "completion_rate" : f"{completion_rate}%",
            "today"           : today_trips,
        },
        "revenue": {
            "today"    : round(today_revenue, 2),
            "this_month": round(month_revenue, 2),
            "total"    : round(total_revenue, 2),
        }
    }


# ════════════════════════════════════════════════════════════
#  DRIVER MANAGEMENT
# ════════════════════════════════════════════════════════════
@router.get("/drivers", summary="List all drivers")
def list_drivers(
    admin     = Depends(require_admin),
    db        : Session = Depends(get_db),
    approved  : Optional[bool] = None,
    city      : Optional[str]  = None,
    limit     : int = 20,
    offset    : int = 0
):
    q = db.query(Driver)
    if approved is not None:
        q = q.filter(Driver.is_approved == approved)
    if city:
        q = q.filter(Driver.city.ilike(f"%{city}%"))
    drivers = q.order_by(Driver.created_at.desc()).offset(offset).limit(limit).all()
    return [_driver_detail(d) for d in drivers]


@router.patch("/drivers/{driver_id}/approve", summary="Approve a driver")
def approve_driver(
    driver_id : int,
    admin     = Depends(require_admin),
    db        : Session = Depends(get_db)
):
    driver = _get_driver(db, driver_id)
    if driver.is_approved:
        return {"message": "Driver already approved.", "driver_id": driver_id}
    driver.is_approved = True
    db.commit()
    return {
        "message"  : f"Driver {driver.user.full_name} approved successfully!",
        "driver_id": driver_id,
        "phone"    : driver.user.phone
    }


@router.patch("/drivers/{driver_id}/reject", summary="Reject / suspend a driver")
def reject_driver(
    driver_id : int,
    admin     = Depends(require_admin),
    db        : Session = Depends(get_db)
):
    driver = _get_driver(db, driver_id)
    driver.is_approved = False
    driver.is_online   = False
    db.commit()
    return {"message": f"Driver {driver.user.full_name} suspended.", "driver_id": driver_id}


@router.get("/drivers/{driver_id}", summary="Driver full profile")
def driver_profile(
    driver_id : int,
    admin     = Depends(require_admin),
    db        : Session = Depends(get_db)
):
    driver = _get_driver(db, driver_id)
    trips  = db.query(Trip).filter(Trip.driver_id == driver_id).all()
    completed = [t for t in trips if t.status == RideStatus.completed]
    cancelled = [t for t in trips if t.status == RideStatus.cancelled]
    return {
        **_driver_detail(driver),
        "trip_stats": {
            "total"    : len(trips),
            "completed": len(completed),
            "cancelled": len(cancelled),
            "earnings" : driver.total_earnings,
        }
    }


# ════════════════════════════════════════════════════════════
#  USER MANAGEMENT
# ════════════════════════════════════════════════════════════
@router.get("/users", summary="List all users")
def list_users(
    admin  = Depends(require_admin),
    db     : Session = Depends(get_db),
    role   : Optional[str] = None,
    search : Optional[str] = None,
    limit  : int = 20,
    offset : int = 0
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if search:
        q = q.filter(
            User.full_name.ilike(f"%{search}%") |
            User.phone.ilike(f"%{search}%")
        )
    users = q.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return [_user_detail(u) for u in users]


@router.patch("/users/{user_id}/deactivate", summary="Deactivate a user")
def deactivate_user(
    user_id : int,
    admin   = Depends(require_admin),
    db      : Session = Depends(get_db)
):
    user = _get_user(db, user_id)
    if user.role == UserRole.admin:
        raise HTTPException(status_code=403, detail="Cannot deactivate admin accounts.")
    user.is_active = False
    if user.driver_profile:
        user.driver_profile.is_online = False
    db.commit()
    return {"message": f"User {user.full_name} deactivated.", "user_id": user_id}


@router.patch("/users/{user_id}/activate", summary="Reactivate a user")
def activate_user(
    user_id : int,
    admin   = Depends(require_admin),
    db      : Session = Depends(get_db)
):
    user = _get_user(db, user_id)
    user.is_active = True
    db.commit()
    return {"message": f"User {user.full_name} activated.", "user_id": user_id}


# ════════════════════════════════════════════════════════════
#  TRIP MANAGEMENT
# ════════════════════════════════════════════════════════════
@router.get("/trips", summary="All trips with filters")
def list_trips(
    admin       = Depends(require_admin),
    db          : Session = Depends(get_db),
    status      : Optional[str] = None,
    vehicle_type: Optional[str] = None,
    date_from   : Optional[str] = None,   # YYYY-MM-DD
    date_to     : Optional[str] = None,
    limit       : int = 30,
    offset      : int = 0
):
    q = db.query(Trip)
    if status:
        q = q.filter(Trip.status == status)
    if vehicle_type:
        q = q.filter(Trip.vehicle_type == vehicle_type)
    if date_from:
        q = q.filter(Trip.requested_at >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        q = q.filter(Trip.requested_at <= datetime.strptime(date_to, "%Y-%m-%d"))
    trips = q.order_by(Trip.requested_at.desc()).offset(offset).limit(limit).all()
    return [_trip_detail(t) for t in trips]


@router.get("/trips/live", summary="All currently active trips")
def live_trips(admin=Depends(require_admin), db: Session = Depends(get_db)):
    trips = db.query(Trip).filter(Trip.status.in_([
        RideStatus.requested, RideStatus.accepted,
        RideStatus.arrived,   RideStatus.started
    ])).all()
    return {"count": len(trips), "trips": [_trip_detail(t) for t in trips]}


# ════════════════════════════════════════════════════════════
#  ANALYTICS
# ════════════════════════════════════════════════════════════
@router.get("/analytics/revenue", summary="Revenue by day (last N days)")
def revenue_by_day(
    admin = Depends(require_admin),
    db    : Session = Depends(get_db),
    days  : int = 7
):
    result = []
    for i in range(days - 1, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).date()
        rev = db.query(func.sum(Trip.actual_fare)).filter(
            func.date(Trip.completed_at) == day,
            Trip.status == RideStatus.completed
        ).scalar() or 0.0
        cnt = db.query(Trip).filter(
            func.date(Trip.requested_at) == day
        ).count()
        result.append({
            "date"    : str(day),
            "revenue" : round(rev, 2),
            "trips"   : cnt,
        })
    return result


@router.get("/analytics/vehicle-type", summary="Trips by vehicle type")
def trips_by_vehicle(admin=Depends(require_admin), db: Session = Depends(get_db)):
    result = []
    for vtype in VehicleType:
        count = db.query(Trip).filter(Trip.vehicle_type == vtype).count()
        revenue = db.query(func.sum(Trip.actual_fare)).filter(
            Trip.vehicle_type == vtype,
            Trip.status == RideStatus.completed
        ).scalar() or 0.0
        result.append({
            "vehicle_type": vtype.value,
            "total_trips" : count,
            "revenue"     : round(revenue, 2),
        })
    return result


@router.get("/analytics/top-drivers", summary="Top 10 drivers by earnings")
def top_drivers(admin=Depends(require_admin), db: Session = Depends(get_db)):
    drivers = db.query(Driver).filter(
        Driver.is_approved == True
    ).order_by(Driver.total_earnings.desc()).limit(10).all()
    return [{
        "rank"          : i + 1,
        "name"          : d.user.full_name,
        "phone"         : d.user.phone,
        "city"          : d.city,
        "total_trips"   : d.total_trips,
        "total_earnings": d.total_earnings,
        "avg_rating"    : d.avg_rating,
    } for i, d in enumerate(drivers)]


@router.get("/analytics/cancellation", summary="Cancellation analysis")
def cancellation_analysis(admin=Depends(require_admin), db: Session = Depends(get_db)):
    total     = db.query(Trip).count()
    cancelled = db.query(Trip).filter(Trip.status == RideStatus.cancelled).all()
    no_driver = sum(1 for t in cancelled if t.driver_id is None)
    by_reason = {}
    for t in cancelled:
        reason = t.cancel_reason or "No reason"
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return {
        "total_trips"          : total,
        "cancelled_trips"      : len(cancelled),
        "cancellation_rate"    : f"{round(len(cancelled)/total*100, 1) if total else 0}%",
        "cancelled_no_driver"  : no_driver,
        "top_reasons"          : sorted(by_reason.items(), key=lambda x: -x[1])[:5],
    }


# ════════════════════════════════════════════════════════════
#  ADMIN: CREATE ADMIN USER
# ════════════════════════════════════════════════════════════
@router.post("/create-admin", summary="Create a new admin account")
def create_admin(
    full_name: str, phone: str, password: str,
    admin=Depends(require_admin),
    db: Session = Depends(get_db)
):
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered.")
    new_admin = User(
        full_name     = full_name,
        phone         = phone,
        password_hash = hash_password(password),
        role          = UserRole.admin,
        is_verified   = True,
        is_active     = True,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return {"message": "Admin created.", "user_id": new_admin.id, "phone": phone}


# ════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════
def _get_user(db, user_id):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    return u

def _get_driver(db, driver_id):
    d = db.query(Driver).filter(Driver.id == driver_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Driver not found.")
    return d

def _user_detail(u):
    return {
        "id"          : u.id,
        "full_name"   : u.full_name,
        "phone"       : u.phone,
        "email"       : u.email,
        "role"        : u.role,
        "language"    : u.language,
        "is_active"   : u.is_active,
        "is_verified" : u.is_verified,
        "created_at"  : u.created_at,
    }

def _driver_detail(d):
    v = d.vehicle
    return {
        "id"             : d.id,
        "user_id"        : d.user_id,
        "full_name"      : d.user.full_name,
        "phone"          : d.user.phone,
        "city"           : d.city,
        "is_approved"    : d.is_approved,
        "is_online"      : d.is_online,
        "license_number" : d.license_number,
        "license_expiry" : d.license_expiry,
        "avg_rating"     : d.avg_rating,
        "total_trips"    : d.total_trips,
        "total_earnings" : d.total_earnings,
        "vehicle"        : {
            "type"        : v.vehicle_type if v else None,
            "brand"       : v.brand        if v else None,
            "model"       : v.model        if v else None,
            "color"       : v.color        if v else None,
            "plate_number": v.plate_number if v else None,
            "year"        : v.year         if v else None,
        } if v else None,
        "joined_at"      : d.created_at,
    }

def _trip_detail(t):
    return {
        "id"            : t.id,
        "status"        : t.status,
        "rider"         : t.rider.full_name  if t.rider  else None,
        "rider_phone"   : t.rider.phone      if t.rider  else None,
        "driver"        : t.driver.user.full_name if t.driver else "Unassigned",
        "driver_phone"  : t.driver.user.phone     if t.driver else None,
        "pickup"        : t.pickup_address,
        "drop"          : t.drop_address,
        "vehicle_type"  : t.vehicle_type,
        "estimated_fare": t.estimated_fare,
        "actual_fare"   : t.actual_fare,
        "distance_km"   : t.distance_km,
        "payment_method": t.payment_method,
        "requested_at"  : t.requested_at,
        "completed_at"  : t.completed_at,
        "cancel_reason" : t.cancel_reason,
    }
