
# ── Surge Pricing Config ──────────────────────────────────
SURGE_RULES = [
    # (hour_start, hour_end, min_active_trips, multiplier, label)
    (8,  10, 5,  1.5, "Morning Peak"),
    (17, 20, 5,  1.5, "Evening Peak"),
    (20, 23, 8,  1.3, "Night Demand"),
    (0,   5, 2,  1.2, "Late Night"),
]

def get_surge_multiplier(db=None, hour: int = None) -> dict:
    """
    Returns surge multiplier based on time of day and optionally
    active trip count in DB.
    """
    from datetime import datetime
    if hour is None:
        hour = datetime.utcnow().hour + 5   # IST offset

    multiplier = 1.0
    reason     = "Normal fare"

    for (h_start, h_end, min_trips, mult, label) in SURGE_RULES:
        if h_start <= hour < h_end:
            active_trips = 0
            if db:
                from app.models.database import Trip, RideStatus
                active_trips = db.query(Trip).filter(
                    Trip.status.in_([RideStatus.requested, RideStatus.accepted, RideStatus.started])
                ).count()
            if active_trips >= min_trips or db is None:
                multiplier = mult
                reason     = label
            break

    return {"multiplier": multiplier, "reason": reason, "is_surge": multiplier > 1.0}

import math
from app.models.database import VehicleType

# ── Base fare config (₹) ──────────────────────────────────
FARE_CONFIG = {
    VehicleType.bike:  {"base": 15, "per_km": 7,  "per_min": 1,   "min_fare": 30},
    VehicleType.auto:  {"base": 20, "per_km": 10, "per_min": 1.5, "min_fare": 40},
    VehicleType.mini:  {"base": 30, "per_km": 12, "per_min": 2,   "min_fare": 60},
    VehicleType.sedan: {"base": 40, "per_km": 15, "per_min": 2.5, "min_fare": 80},
    VehicleType.suv:   {"base": 60, "per_km": 20, "per_min": 3,   "min_fare": 120},
}

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in KM between two GPS coordinates."""
    R = 6371  # Earth radius in km
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lng / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def estimate_duration(distance_km: float, vehicle_type: VehicleType) -> int:
    """Estimate trip duration in minutes based on avg city speed."""
    speeds = {
        VehicleType.bike:  30,
        VehicleType.auto:  25,
        VehicleType.mini:  28,
        VehicleType.sedan: 28,
        VehicleType.suv:   28,
    }
    speed = speeds.get(vehicle_type, 28)
    return max(5, int((distance_km / speed) * 60))

def calculate_fare(
    pickup_lat: float, pickup_lng: float,
    drop_lat: float,   drop_lng: float,
    vehicle_type: VehicleType,
    surge_multiplier: float = 1.0
) -> dict:
    distance_km  = haversine_distance(pickup_lat, pickup_lng, drop_lat, drop_lng)
    duration_min = estimate_duration(distance_km, vehicle_type)
    config       = FARE_CONFIG[vehicle_type]

    fare = (config["base"] +
            distance_km  * config["per_km"] +
            duration_min * config["per_min"])

    fare = max(fare, config["min_fare"])
    fare = round(fare * surge_multiplier, 2)

    return {
        "estimated_fare":   fare,
        "distance_km":      distance_km,
        "duration_min":     duration_min,
        "surge_multiplier": surge_multiplier,
        "breakdown": {
            "base_fare":     config["base"],
            "distance_fare": round(distance_km  * config["per_km"],  2),
            "time_fare":     round(duration_min * config["per_min"], 2),
        }
    }
