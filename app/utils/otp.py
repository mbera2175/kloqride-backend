import random
import string
import os
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.database import OTPRecord, User

# ── Config ────────────────────────────────────────────────
OTP_EXPIRY_MINUTES = 10
MAX_ATTEMPTS       = 3
DEV_MODE           = os.getenv("DEV_MODE", "True").lower() == "true"
FAST2SMS_API_KEY   = os.getenv("FAST2SMS_API_KEY", "")

# ── SMS Provider ──────────────────────────────────────────
def send_sms(phone: str, message: str) -> bool:
    if not FAST2SMS_API_KEY or DEV_MODE:
        print(f"📱 [SMS to {phone}]: {message}")
        return True
    try:
        response = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers={"authorization": FAST2SMS_API_KEY},
            data={
                "message": message,
                "language": "english",
                "route": "q",
                "numbers": phone
            },
            timeout=10
        )
        result = response.json()
        print(f"Fast2SMS response: {result}")
        return result.get("return") == True
    except Exception as e:
        print(f"SMS error: {e}")
        return False


def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def create_otp(db: Session, phone: str, purpose: str = "login", user_id: int = None) -> dict:
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

    message = f"Your Kloq Ride OTP is {code}. Valid for {OTP_EXPIRY_MINUTES} minutes. Do not share with anyone."
    send_sms(phone, message)

    response = {"message": f"OTP sent to {phone[-4:].rjust(len(phone), '*')}"}
    if DEV_MODE:
        response["dev_otp"] = code
    return response


def verify_otp(db: Session, phone: str, code: str, purpose: str = "login") -> OTPRecord:
    record = db.query(OTPRecord).filter(
        OTPRecord.phone   == phone,
        OTPRecord.is_used == False,
        OTPRecord.purpose == purpose,
    ).order_by(OTPRecord.created_at.desc()).first()

    if not record:
        raise ValueError("No active OTP found. Please request a new one.")

    if datetime.utcnow() > record.expires_at:
        record.is_used = True
        db.commit()
        raise ValueError("OTP has expired. Please request a new one.")

    record.attempts += 1
    if record.attempts > MAX_ATTEMPTS:
        record.is_used = True
        db.commit()
        raise ValueError("Too many wrong attempts. Please request a new OTP.")

    if record.otp_code != code.strip():
        db.commit()
        remaining = MAX_ATTEMPTS - record.attempts
        raise ValueError(f"Wrong OTP. {remaining} attempt(s) remaining.")

    record.is_used = True
    db.commit()
    return record
