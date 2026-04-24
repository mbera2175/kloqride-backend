import random
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.database import OTPRecord, User

# ── Config ────────────────────────────────────────────────
OTP_EXPIRY_MINUTES = 10
MAX_ATTEMPTS       = 3
DEV_MODE           = True   # Set False in production → real SMS only

# ── SMS Provider (plug in Twilio / MSG91 / Fast2SMS here) ─
def send_sms(phone: str, message: str) -> bool:
    """
    Plug your SMS provider here.
    
    Example with Fast2SMS (popular in India):
    ─────────────────────────────────────────
    import requests
    response = requests.post("https://www.fast2sms.com/dev/bulkV2", 
        headers={"authorization": "YOUR_API_KEY"},
        data={"message": message, "language": "english", "route": "q", "numbers": phone}
    )
    return response.json().get("return") == True

    Example with Twilio:
    ─────────────────────────────────────────
    from twilio.rest import Client
    client = Client("ACCOUNT_SID", "AUTH_TOKEN")
    client.messages.create(body=message, from_="+1XXXXXXXXXX", to=f"+91{phone}")
    return True
    """
    # DEV MODE: just print instead of sending
    print(f"📱 [SMS to {phone}]: {message}")
    return True


def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def create_otp(db: Session, phone: str, purpose: str = "login", user_id: int = None) -> dict:
    """
    Invalidate any old unused OTPs for this phone, then create a fresh one.
    Returns the OTP (visible in DEV_MODE, hidden in production).
    """
    # Expire old OTPs for this phone
    db.query(OTPRecord).filter(
        OTPRecord.phone   == phone,
        OTPRecord.is_used == False
    ).update({"is_used": True})
    db.flush()

    code       = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    record = OTPRecord(
        phone      = phone,
        user_id    = user_id,
        otp_code   = code,
        purpose    = purpose,
        expires_at = expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Send SMS
    message = f"Your Kloq Ride OTP is {code}. Valid for {OTP_EXPIRY_MINUTES} minutes. Do not share with anyone."
    send_sms(phone, message)

    response = {"message": f"OTP sent to {phone[-4:].rjust(len(phone), '*')}"}
    if DEV_MODE:
        response["dev_otp"] = code   # Remove this line in production!
    return response


def verify_otp(db: Session, phone: str, code: str, purpose: str = "login") -> OTPRecord:
    """
    Verifies OTP. Raises ValueError on failure.
    Returns the valid OTPRecord on success.
    """
    record = db.query(OTPRecord).filter(
        OTPRecord.phone   == phone,
        OTPRecord.is_used == False,
        OTPRecord.purpose == purpose,
    ).order_by(OTPRecord.created_at.desc()).first()

    if not record:
        raise ValueError("No active OTP found. Please request a new one.")

    # Check expiry
    if datetime.utcnow() > record.expires_at:
        record.is_used = True
        db.commit()
        raise ValueError("OTP has expired. Please request a new one.")

    # Check attempts
    record.attempts += 1
    if record.attempts > MAX_ATTEMPTS:
        record.is_used = True
        db.commit()
        raise ValueError("Too many wrong attempts. Please request a new OTP.")

    # Check code
    if record.otp_code != code.strip():
        db.commit()
        remaining = MAX_ATTEMPTS - record.attempts
        raise ValueError(f"Wrong OTP. {remaining} attempt(s) remaining.")

    # Success — mark used
    record.is_used = True
    db.commit()
    return record
