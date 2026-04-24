from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.database import (
    get_db, User, Driver, Vehicle, Trip, Rating,
    RideStatus, VehicleType, UserRole
)
from app.schemas.trips import (
    FareEstimateRequest, BookRideRequest,
    CancelRideRequest, RateTripRequest, TripOut, DriverBasic
)
from app.utils.fare import calculate_fare, get_surge_multiplier
from app.utils.notifications import push, push_trip_event, NotificationType
from app.utils import wallet as wallet_svc
from app.routes.promo import _validate_promo, record_promo_usage
from app.utils.dependencies import get_current_user, get_current_driver

router = APIRouter(prefix="/trips", tags=["Trips"])


# ════════════════════════════════════════════════════════════
#  FARE ESTIMATE  (no auth needed)
# ════════════════════════════════════════════════════════════
@router.post("/estimate", summary="Get fare estimate for all vehicle types")
def estimate_fare(data: FareEstimateRequest):
    """Returns fare breakdown for all 5 vehicle types at once."""
    result = {}
    distance_km  = None
    duration_min = None

    for vtype in VehicleType:
        calc = calculate_fare(
            data.pickup_lat, data.pickup_lng,
            data.drop_lat,   data.drop_lng,
            vtype
        )
        result[vtype.value] = {
            "estimated_fare": calc["estimated_fare"],
            "breakdown"     : calc["breakdown"],
        }
        if distance_km is None:
            distance_km  = calc["distance_km"]
            duration_min = calc["duration_min"]

    return {
        **result,
        "distance_km" : distance_km,
        "duration_min": duration_min,
    }


# ════════════════════════════════════════════════════════════
#  BOOK A RIDE  (rider)
# ════════════════════════════════════════════════════════════
@router.post("/book", summary="Book a ride")
def book_ride(
    data        : BookRideRequest,
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db)
):
    if current_user.role not in [UserRole.rider, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only riders can book rides.")

    # Check no active trip already
    active = db.query(Trip).filter(
        Trip.rider_id == current_user.id,
        Trip.status.in_([
            RideStatus.requested, RideStatus.accepted,
            RideStatus.arrived,   RideStatus.started
        ])
    ).first()
    if active:
        raise HTTPException(status_code=400, detail=f"You already have an active trip (#{active.id}).")

    # 1. Surge pricing
    surge      = get_surge_multiplier(db)
    surge_mult = surge["multiplier"]

    # 2. Calculate fare with surge
    calc = calculate_fare(
        data.pickup_lat, data.pickup_lng,
        data.drop_lat,   data.drop_lng,
        data.vehicle_type, surge_multiplier=surge_mult
    )
    estimated_fare = calc["estimated_fare"]
    discount_amount = 0.0
    promo_obj       = None

    # 3. Apply promo code if provided
    if data.promo_code:
        try:
            discount_amount, promo_obj = _validate_promo(
                db, current_user, data.promo_code, estimated_fare, data.vehicle_type
            )
            estimated_fare = round(estimated_fare - discount_amount, 2)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # 4. Wallet payment check
    if data.payment_method.value == "wallet":
        if current_user.wallet_balance < estimated_fare:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient wallet balance. Available ₹{current_user.wallet_balance}, Required ₹{estimated_fare}"
            )

    # 5. Find nearest driver
    driver = find_nearest_driver(db, data.pickup_lat, data.pickup_lng, data.vehicle_type)

    trip = Trip(
        rider_id         = current_user.id,
        driver_id        = driver.id if driver else None,
        pickup_address   = data.pickup_address,
        pickup_lat       = data.pickup_lat,
        pickup_lng       = data.pickup_lng,
        drop_address     = data.drop_address,
        drop_lat         = data.drop_lat,
        drop_lng         = data.drop_lng,
        vehicle_type     = data.vehicle_type,
        payment_method   = data.payment_method,
        estimated_fare   = estimated_fare,
        distance_km      = calc["distance_km"],
        duration_min     = calc["duration_min"],
        surge_multiplier = surge_mult,
        discount_amount  = discount_amount,
        promo_code       = data.promo_code.upper() if data.promo_code else None,
        status           = RideStatus.accepted if driver else RideStatus.requested,
        accepted_at      = datetime.utcnow() if driver else None,
    )
    db.add(trip)
    db.flush()

    # 6. Record promo usage
    if promo_obj:
        record_promo_usage(db, promo_obj, current_user.id, trip.id)

    # 7. Send notification to rider
    push(db, current_user.id,
         NotificationType.ride_accepted if driver else NotificationType.system,
         trip_id=trip.id,
         custom_msg="Driver found! Your ride is confirmed." if driver else "Looking for a driver near you...")

    db.commit()
    db.refresh(trip)

    return {
        "trip_id"        : trip.id,
        "status"         : trip.status,
        "estimated_fare" : trip.estimated_fare,
        "distance_km"    : trip.distance_km,
        "duration_min"   : trip.duration_min,
        "surge"          : {"active": surge["is_surge"], "multiplier": surge_mult, "reason": surge["reason"]},
        "promo_applied"  : discount_amount > 0,
        "discount"       : discount_amount,
        "driver_found"   : driver is not None,
        "driver"         : _driver_info(driver) if driver else None,
        "message"        : "Driver found! Ride accepted." if driver else "Searching for nearby driver...",
    }


# ════════════════════════════════════════════════════════════
#  DRIVER ACTIONS
# ════════════════════════════════════════════════════════════

@router.get("/pending", summary="Driver: see pending ride requests")
def get_pending_trips(
    driver      : Driver  = Depends(get_current_driver),
    db          : Session = Depends(get_db)
):
    """Driver sees unassigned ride requests of their vehicle type."""
    trips = db.query(Trip).filter(
        Trip.status      == RideStatus.requested,
        Trip.driver_id   == None,
        Trip.vehicle_type == driver.vehicle.vehicle_type
    ).order_by(Trip.requested_at.asc()).all()
    return [_trip_summary(t) for t in trips]


@router.patch("/{trip_id}/accept", summary="Driver: accept a trip")
def accept_trip(
    trip_id : int,
    driver  : Driver  = Depends(get_current_driver),
    db      : Session = Depends(get_db)
):
    trip = _get_trip(db, trip_id)
    if trip.status != RideStatus.requested:
        raise HTTPException(status_code=400, detail="Trip is no longer available.")
    if trip.driver_id and trip.driver_id != driver.id:
        raise HTTPException(status_code=400, detail="Trip already taken by another driver.")

    trip.driver_id  = driver.id
    trip.status     = RideStatus.accepted
    trip.accepted_at = datetime.utcnow()
    db.commit()
    return {"message": "Trip accepted!", "trip_id": trip.id, "status": trip.status}


@router.patch("/{trip_id}/arrived", summary="Driver: mark arrived at pickup")
def mark_arrived(
    trip_id : int,
    driver  : Driver  = Depends(get_current_driver),
    db      : Session = Depends(get_db)
):
    trip = _get_driver_trip(db, trip_id, driver.id)
    if trip.status != RideStatus.accepted:
        raise HTTPException(status_code=400, detail="Trip must be in accepted state.")
    trip.status     = RideStatus.arrived
    trip.arrived_at = datetime.utcnow()
    db.commit()
    return {"message": "Marked as arrived.", "trip_id": trip.id}


@router.patch("/{trip_id}/start", summary="Driver: start the trip")
def start_trip(
    trip_id : int,
    driver  : Driver  = Depends(get_current_driver),
    db      : Session = Depends(get_db)
):
    trip = _get_driver_trip(db, trip_id, driver.id)
    if trip.status not in [RideStatus.accepted, RideStatus.arrived]:
        raise HTTPException(status_code=400, detail="Trip must be accepted/arrived to start.")
    trip.status     = RideStatus.started
    trip.started_at = datetime.utcnow()
    db.commit()
    return {"message": "Trip started!", "trip_id": trip.id}


@router.patch("/{trip_id}/complete", summary="Driver: complete the trip")
def complete_trip(
    trip_id : int,
    driver  : Driver  = Depends(get_current_driver),
    db      : Session = Depends(get_db)
):
    trip = _get_driver_trip(db, trip_id, driver.id)
    if trip.status != RideStatus.started:
        raise HTTPException(status_code=400, detail="Trip must be started to complete.")

    # Finalize fare
    actual_fare = round(trip.estimated_fare * trip.surge_multiplier, 2)
    trip.status        = RideStatus.completed
    trip.completed_at  = datetime.utcnow()
    trip.actual_fare   = actual_fare

    # Update driver stats
    driver.total_trips    += 1
    driver.total_earnings += actual_fare

    # Wallet payment
    if trip.payment_method.value == "wallet":
        rider = trip.rider
        wallet_svc.debit(db, rider, actual_fare,
                         description=f"Trip #{trip.id} payment", trip_id=trip.id)
        wallet_svc.credit(db, driver.user, actual_fare,
                          description=f"Trip #{trip.id} earnings", trip_id=trip.id)

    # Notifications
    push_trip_event(db, trip, NotificationType.ride_completed)
    db.commit()

    return {
        "message"    : "Trip completed!",
        "trip_id"    : trip.id,
        "actual_fare": actual_fare,
        "payment"    : trip.payment_method,
    }


# ════════════════════════════════════════════════════════════
#  CANCEL  (rider or driver)
# ════════════════════════════════════════════════════════════
@router.patch("/{trip_id}/cancel", summary="Cancel a trip")
def cancel_trip(
    trip_id     : int,
    data        : CancelRideRequest,
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db)
):
    trip = _get_trip(db, trip_id)

    # Authorize — rider or driver of this trip
    is_rider  = trip.rider_id == current_user.id
    is_driver = (trip.driver and trip.driver.user_id == current_user.id)
    if not (is_rider or is_driver or current_user.role == UserRole.admin):
        raise HTTPException(status_code=403, detail="Not authorized to cancel this trip.")

    if trip.status in [RideStatus.completed, RideStatus.cancelled]:
        raise HTTPException(status_code=400, detail=f"Trip is already {trip.status}.")
    if trip.status == RideStatus.started:
        raise HTTPException(status_code=400, detail="Cannot cancel a trip that has started.")

    trip.status        = RideStatus.cancelled
    trip.cancelled_at  = datetime.utcnow()
    trip.cancel_reason = data.reason

    # Refund wallet if applicable
    if trip.payment_method.value == "wallet" and trip.status.value in ["accepted","arrived"]:
        wallet_svc.refund(db, trip.rider, trip.estimated_fare,
                          description=f"Refund for cancelled trip #{trip.id}", trip_id=trip.id)

    push_trip_event(db, trip, NotificationType.ride_cancelled)
    db.commit()
    return {"message": "Trip cancelled.", "trip_id": trip.id, "reason": data.reason}


# ════════════════════════════════════════════════════════════
#  HISTORY & TRACKING
# ════════════════════════════════════════════════════════════
@router.get("/my", summary="Rider: my trip history")
def my_trips(
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db),
    limit       : int     = 20,
    offset      : int     = 0
):
    trips = (
        db.query(Trip)
        .filter(Trip.rider_id == current_user.id)
        .order_by(Trip.requested_at.desc())
        .offset(offset).limit(limit)
        .all()
    )
    return [_trip_summary(t) for t in trips]


@router.get("/driver/my", summary="Driver: my trip history")
def driver_trips(
    driver: Driver  = Depends(get_current_driver),
    db    : Session = Depends(get_db),
    limit : int = 20,
    offset: int = 0
):
    trips = (
        db.query(Trip)
        .filter(Trip.driver_id == driver.id)
        .order_by(Trip.requested_at.desc())
        .offset(offset).limit(limit)
        .all()
    )
    return [_trip_summary(t) for t in trips]


@router.get("/{trip_id}", summary="Get trip details")
def get_trip_detail(
    trip_id     : int,
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db)
):
    trip = _get_trip(db, trip_id)
    is_rider  = trip.rider_id == current_user.id
    is_driver = trip.driver and trip.driver.user_id == current_user.id
    if not (is_rider or is_driver or current_user.role == UserRole.admin):
        raise HTTPException(status_code=403, detail="Not authorized.")
    return _trip_summary(trip, detailed=True)


# ════════════════════════════════════════════════════════════
#  RATING
# ════════════════════════════════════════════════════════════
@router.post("/{trip_id}/rate", summary="Rate completed trip")
def rate_trip(
    trip_id     : int,
    data        : RateTripRequest,
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db)
):
    trip = _get_trip(db, trip_id)
    if trip.status != RideStatus.completed:
        raise HTTPException(status_code=400, detail="Can only rate completed trips.")
    if db.query(Rating).filter(Rating.trip_id == trip_id).first():
        raise HTTPException(status_code=400, detail="Trip already rated.")

    is_rider = trip.rider_id == current_user.id
    if not is_rider:
        raise HTTPException(status_code=403, detail="Only the rider can rate this trip.")

    rated_user_id = trip.driver.user_id

    rating = Rating(
        trip_id  = trip.id,
        rater_id = current_user.id,
        rated_id = rated_user_id,
        score    = data.score,
        comment  = data.comment,
    )
    db.add(rating)

    # Update driver avg rating
    all_ratings = db.query(Rating).filter(Rating.rated_id == rated_user_id).all()
    total = sum(r.score for r in all_ratings) + data.score
    count = len(all_ratings) + 1
    trip.driver.avg_rating = round(total / count, 2)
    db.commit()

    return {"message": "Rating submitted!", "score": data.score, "driver_avg": trip.driver.avg_rating}


# ════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════
def _get_trip(db, trip_id):
    t = db.query(Trip).filter(Trip.id == trip_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return t

def _get_driver_trip(db, trip_id, driver_id):
    t = _get_trip(db, trip_id)
    if t.driver_id != driver_id:
        raise HTTPException(status_code=403, detail="This trip is not assigned to you.")
    return t

def _driver_info(driver):
    if not driver:
        return None
    v = driver.vehicle
    return {
        "id"          : driver.id,
        "full_name"   : driver.user.full_name,
        "phone"       : driver.user.phone,
        "avg_rating"  : driver.avg_rating,
        "vehicle_type": v.vehicle_type if v else None,
        "brand"       : v.brand        if v else None,
        "model"       : v.model        if v else None,
        "color"       : v.color        if v else None,
        "plate_number": v.plate_number if v else None,
    }

def _trip_summary(trip, detailed=False):
    d = {
        "id"             : trip.id,
        "status"         : trip.status,
        "pickup_address" : trip.pickup_address,
        "drop_address"   : trip.drop_address,
        "vehicle_type"   : trip.vehicle_type,
        "payment_method" : trip.payment_method,
        "estimated_fare" : trip.estimated_fare,
        "actual_fare"    : trip.actual_fare,
        "distance_km"    : trip.distance_km,
        "duration_min"   : trip.duration_min,
        "requested_at"   : trip.requested_at,
        "completed_at"   : trip.completed_at,
        "cancelled_at"   : trip.cancelled_at,
    }
    if detailed:
        d.update({
            "pickup_lat"   : trip.pickup_lat,
            "pickup_lng"   : trip.pickup_lng,
            "drop_lat"     : trip.drop_lat,
            "drop_lng"     : trip.drop_lng,
            "accepted_at"  : trip.accepted_at,
            "started_at"   : trip.started_at,
            "cancel_reason": trip.cancel_reason,
            "driver"       : _driver_info(trip.driver),
        })
    return d
