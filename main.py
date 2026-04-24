from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.database import create_tables
from app.routes import auth as auth_router
from app.routes import trips as trips_router
from app.routes import admin as admin_router
from app.routes import notifications as notif_router
from app.routes import wallet as wallet_router
from app.routes import promo as promo_router

app = FastAPI(
    title="🚖 Kloq Ride API",
    description="Ride-hailing platform for West Bengal — Bengali first!",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(trips_router.router)
app.include_router(admin_router.router)
app.include_router(notif_router.router)
app.include_router(wallet_router.router)
app.include_router(promo_router.router)

@app.on_event("startup")
def on_startup():
    create_tables()
    print("✅ Kloq Ride DB initialized")

@app.get("/")
def root():
    return {"message": "🚖 Kloq Ride API is running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "ok"}
