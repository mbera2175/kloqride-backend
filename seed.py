"""
Run once to create the default admin account.
Usage: python seed.py
"""
from app.models.database import SessionLocal, create_tables, User, UserRole
from app.utils.security import hash_password

def seed():
    create_tables()
    db = SessionLocal()

    # Check if admin exists
    admin = db.query(User).filter(User.phone == "9000000000").first()
    if admin:
        print("⚠️  Admin already exists")
        db.close()
        return

    admin = User(
        full_name     = "Kloq Admin",
        phone         = "9000000000",
        email         = "admin@kloqride.com",
        password_hash = hash_password("admin@kloq123"),
        role          = UserRole.admin,
        language      = "bn",
        is_active     = True,
        is_verified   = True,
    )
    db.add(admin)
    db.commit()
    print("✅ Admin created")
    print("   Phone   : 9000000000")
    print("   Password: admin@kloq123")
    db.close()

if __name__ == "__main__":
    seed()
