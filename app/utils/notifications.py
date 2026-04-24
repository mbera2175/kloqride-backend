from sqlalchemy.orm import Session
from app.models.database import Notification, NotificationType

# ── Notification messages per event ──────────────────────
MESSAGES = {
    NotificationType.ride_accepted : ("Ride Accepted! 🚗",    "Your driver is on the way to pick you up."),
    NotificationType.ride_arrived  : ("Driver Arrived! 📍",   "Your driver has arrived at the pickup point."),
    NotificationType.ride_started  : ("Trip Started! 🛣️",     "Your trip has begun. Sit back and enjoy!"),
    NotificationType.ride_completed: ("Trip Completed! ✅",   "You have reached your destination. Thank you for riding with Kloq!"),
    NotificationType.ride_cancelled: ("Ride Cancelled ❌",    "Your ride has been cancelled."),
    NotificationType.payment       : ("Payment Update 💰",    ""),
    NotificationType.promo         : ("Promo Applied! 🎉",    ""),
    NotificationType.system        : ("Kloq Ride 🚖",         ""),
}


def push(
    db         : Session,
    user_id    : int,
    notif_type : NotificationType,
    trip_id    : int  = None,
    custom_msg : str  = None,
):
    """Create an in-app notification for a user."""
    title, default_msg = MESSAGES.get(notif_type, ("Kloq Ride", ""))
    message = custom_msg or default_msg

    notif = Notification(
        user_id    = user_id,
        title      = title,
        message    = message,
        notif_type = notif_type,
        trip_id    = trip_id,
    )
    db.add(notif)
    # Note: caller must commit


def push_trip_event(db: Session, trip, notif_type: NotificationType):
    """
    Push notification to both rider and driver for a trip event.
    Driver gets mirror message (e.g. 'Trip completed, ₹X earned').
    """
    push(db, trip.rider_id, notif_type, trip_id=trip.id)

    if trip.driver:
        driver_msgs = {
            NotificationType.ride_completed: f"Trip completed! You earned ₹{trip.actual_fare or trip.estimated_fare}.",
            NotificationType.ride_cancelled: "A ride was cancelled.",
        }
        custom = driver_msgs.get(notif_type)
        push(db, trip.driver.user_id, notif_type, trip_id=trip.id, custom_msg=custom)
