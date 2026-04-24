from sqlalchemy.orm import Session
from app.models.database import Driver, Vehicle, VehicleType
from app.utils.fare import haversine_distance
from typing import Optional

SEARCH_RADIUS_KM = 5.0   # search within 5 km

def find_nearest_driver(
    db          : Session,
    pickup_lat  : float,
    pickup_lng  : float,
    vehicle_type: VehicleType,
    exclude_ids : list = []
) -> Optional[Driver]:
    """
    Find the nearest available, approved, online driver
    with the requested vehicle type within SEARCH_RADIUS_KM.
    """
    drivers = (
        db.query(Driver)
        .join(Vehicle, Driver.id == Vehicle.driver_id)
        .filter(
            Driver.is_online   == True,
            Driver.is_approved == True,
            Driver.current_lat != None,
            Driver.current_lng != None,
            Vehicle.vehicle_type == vehicle_type,
            Vehicle.is_active    == True,
        )
        .all()
    )

    best_driver   = None
    best_distance = float("inf")

    for driver in drivers:
        if driver.id in exclude_ids:
            continue
        dist = haversine_distance(
            pickup_lat, pickup_lng,
            driver.current_lat, driver.current_lng
        )
        if dist <= SEARCH_RADIUS_KM and dist < best_distance:
            best_distance = dist
            best_driver   = driver

    return best_driver


def get_nearby_drivers(
    db         : Session,
    lat        : float,
    lng        : float,
    radius_km  : float = SEARCH_RADIUS_KM
) -> list:
    """Return all online drivers within radius with their distance."""
    drivers = (
        db.query(Driver)
        .filter(
            Driver.is_online   == True,
            Driver.is_approved == True,
            Driver.current_lat != None,
            Driver.current_lng != None,
        )
        .all()
    )
    result = []
    for d in drivers:
        dist = haversine_distance(lat, lng, d.current_lat, d.current_lng)
        if dist <= radius_km:
            result.append({"driver": d, "distance_km": dist})
    result.sort(key=lambda x: x["distance_km"])
    return result
