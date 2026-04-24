from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

DATABASE_URL = "sqlite:///./kloqride.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserRole(str, enum.Enum):
    rider  = "rider"
    driver = "driver"
    admin  = "admin"

class RideStatus(str, enum.Enum):
    requested = "requested"
    accepted  = "accepted"
    arrived   = "arrived"
    started   = "started"
    completed = "completed"
    cancelled = "cancelled"

class VehicleType(str, enum.Enum):
    bike  = "bike"
    auto  = "auto"
    mini  = "mini"
    sedan = "sedan"
    suv   = "suv"

class PaymentMethod(str, enum.Enum):
    cash   = "cash"
    upi    = "upi"
    wallet = "wallet"

class User(Base):
    __tablename__ = "users"
    id             = Column(Integer, primary_key=True, index=True)
    full_name      = Column(String(100), nullable=False)
    phone          = Column(String(15), unique=True, index=True, nullable=False)
    email          = Column(String(100), unique=True, index=True, nullable=True)
    password_hash  = Column(String(200), nullable=True)
    role           = Column(Enum(UserRole), default=UserRole.rider)
    language       = Column(String(10), default="bn")
    profile_pic    = Column(String(200), nullable=True)
    wallet_balance = Column(Float, default=0.0)
    is_active      = Column(Boolean, default=True)
    is_verified    = Column(Boolean, default=False)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rider_trips    = relationship("Trip",      foreign_keys="Trip.rider_id",   back_populates="rider")
    driver_profile = relationship("Driver",    back_populates="user",           uselist=False)
    ratings_given  = relationship("Rating",    foreign_keys="Rating.rater_id", back_populates="rater")
    otps           = relationship("OTPRecord",           back_populates="user", cascade="all, delete")
    notifications  = relationship("Notification",        back_populates="user", cascade="all, delete")
    wallet_transactions = relationship("WalletTransaction", back_populates="user", cascade="all, delete")

class OTPRecord(Base):
    __tablename__ = "otp_records"
    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    phone      = Column(String(15), index=True, nullable=False)
    otp_code   = Column(String(6),  nullable=False)
    purpose    = Column(String(20), default="login")   # login | register
    is_used    = Column(Boolean,    default=False)
    attempts   = Column(Integer,    default=0)
    expires_at = Column(DateTime,   nullable=False)
    created_at = Column(DateTime,   default=datetime.utcnow)
    user       = relationship("User", back_populates="otps")

class Driver(Base):
    __tablename__ = "drivers"
    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), unique=True)
    license_number = Column(String(50), unique=True, nullable=False)
    license_expiry = Column(DateTime,   nullable=False)
    is_online      = Column(Boolean,    default=False)
    is_approved    = Column(Boolean,    default=False)
    current_lat    = Column(Float,      nullable=True)
    current_lng    = Column(Float,      nullable=True)
    total_trips    = Column(Integer,    default=0)
    total_earnings = Column(Float,      default=0.0)
    avg_rating     = Column(Float,      default=5.0)
    city           = Column(String(50), default="Bardhaman")
    created_at     = Column(DateTime,   default=datetime.utcnow)
    user           = relationship("User",    back_populates="driver_profile")
    vehicle        = relationship("Vehicle", back_populates="driver", uselist=False)
    trips          = relationship("Trip",    foreign_keys="Trip.driver_id", back_populates="driver")

class Vehicle(Base):
    __tablename__ = "vehicles"
    id           = Column(Integer, primary_key=True, index=True)
    driver_id    = Column(Integer, ForeignKey("drivers.id"), unique=True)
    vehicle_type = Column(Enum(VehicleType), nullable=False)
    brand        = Column(String(50), nullable=False)
    model        = Column(String(50), nullable=False)
    color        = Column(String(30), nullable=False)
    plate_number = Column(String(20), unique=True, nullable=False)
    year         = Column(Integer,    nullable=False)
    is_active    = Column(Boolean,    default=True)
    created_at   = Column(DateTime,   default=datetime.utcnow)
    driver       = relationship("Driver", back_populates="vehicle")

class Trip(Base):
    __tablename__ = "trips"
    id               = Column(Integer, primary_key=True, index=True)
    rider_id         = Column(Integer, ForeignKey("users.id"))
    driver_id        = Column(Integer, ForeignKey("drivers.id"), nullable=True)
    pickup_address   = Column(String(300), nullable=False)
    pickup_lat       = Column(Float, nullable=False)
    pickup_lng       = Column(Float, nullable=False)
    drop_address     = Column(String(300), nullable=False)
    drop_lat         = Column(Float, nullable=False)
    drop_lng         = Column(Float, nullable=False)
    vehicle_type     = Column(Enum(VehicleType),   nullable=False)
    status           = Column(Enum(RideStatus),    default=RideStatus.requested)
    payment_method   = Column(Enum(PaymentMethod), default=PaymentMethod.cash)
    estimated_fare   = Column(Float,   nullable=False)
    actual_fare      = Column(Float,   nullable=True)
    distance_km      = Column(Float,   nullable=True)
    duration_min     = Column(Integer, nullable=True)
    surge_multiplier = Column(Float,   default=1.0)
    requested_at     = Column(DateTime, default=datetime.utcnow)
    accepted_at      = Column(DateTime, nullable=True)
    arrived_at       = Column(DateTime, nullable=True)
    started_at       = Column(DateTime, nullable=True)
    completed_at     = Column(DateTime, nullable=True)
    cancelled_at     = Column(DateTime, nullable=True)
    cancel_reason    = Column(String(200), nullable=True)
    promo_code       = Column(String(20),  nullable=True)
    discount_amount  = Column(Float,       default=0.0)
    rider            = relationship("User",   foreign_keys=[rider_id],  back_populates="rider_trips")
    driver           = relationship("Driver", foreign_keys=[driver_id], back_populates="trips")
    rating           = relationship("Rating", back_populates="trip",    uselist=False)

class Rating(Base):
    __tablename__ = "ratings"
    id         = Column(Integer, primary_key=True, index=True)
    trip_id    = Column(Integer, ForeignKey("trips.id"),  unique=True)
    rater_id   = Column(Integer, ForeignKey("users.id"))
    rated_id   = Column(Integer, ForeignKey("users.id"))
    score      = Column(Integer, nullable=False)
    comment    = Column(Text,    nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    trip       = relationship("Trip", back_populates="rating")
    rater      = relationship("User", foreign_keys=[rater_id], back_populates="ratings_given")


class NotificationType(str, enum.Enum):
    ride_accepted   = "ride_accepted"
    ride_arrived    = "ride_arrived"
    ride_started    = "ride_started"
    ride_completed  = "ride_completed"
    ride_cancelled  = "ride_cancelled"
    payment         = "payment"
    promo           = "promo"
    system          = "system"

class Notification(Base):
    __tablename__ = "notifications"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    title       = Column(String(100), nullable=False)
    message     = Column(String(500), nullable=False)
    notif_type  = Column(Enum(NotificationType), default=NotificationType.system)
    is_read     = Column(Boolean, default=False)
    trip_id     = Column(Integer, ForeignKey("trips.id"), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    user        = relationship("User", back_populates="notifications")

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount      = Column(Float, nullable=False)
    txn_type    = Column(String(20), nullable=False)  # credit | debit | refund
    description = Column(String(200), nullable=False)
    trip_id     = Column(Integer, ForeignKey("trips.id"), nullable=True)
    balance_after = Column(Float, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    user        = relationship("User", back_populates="wallet_transactions")

class PromoCode(Base):
    __tablename__ = "promo_codes"
    id              = Column(Integer, primary_key=True, index=True)
    code            = Column(String(20), unique=True, nullable=False)
    description     = Column(String(200), nullable=True)
    discount_type   = Column(String(10), nullable=False)   # percent | flat
    discount_value  = Column(Float, nullable=False)
    min_fare        = Column(Float, default=0.0)
    max_discount    = Column(Float, nullable=True)
    usage_limit     = Column(Integer, nullable=True)
    used_count      = Column(Integer, default=0)
    valid_from      = Column(DateTime, nullable=False)
    valid_until     = Column(DateTime, nullable=False)
    is_active       = Column(Boolean, default=True)
    vehicle_type    = Column(Enum(VehicleType), nullable=True)  # None = all types
    created_at      = Column(DateTime, default=datetime.utcnow)
    usages          = relationship("PromoUsage", back_populates="promo")

class PromoUsage(Base):
    __tablename__ = "promo_usages"
    id          = Column(Integer, primary_key=True, index=True)
    promo_id    = Column(Integer, ForeignKey("promo_codes.id"))
    user_id     = Column(Integer, ForeignKey("users.id"))
    trip_id     = Column(Integer, ForeignKey("trips.id"), nullable=True)
    used_at     = Column(DateTime, default=datetime.utcnow)
    promo       = relationship("PromoCode", back_populates="usages")

def create_tables():
    Base.metadata.create_all(bind=engine)
