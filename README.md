# 🚖 Kloq Ride — Backend API

A complete ride-hailing backend built with **Python + FastAPI**.  
Built for **West Bengal, India** — Bengali-first platform.

---

## 📁 Project Structure

```
kloqride/
├── main.py                  ← App entry point
├── seed.py                  ← Creates default admin account
├── requirements.txt         ← All dependencies
├── .env.example             ← Environment variable template
└── app/
    ├── models/
    │   └── database.py      ← All database tables (SQLAlchemy)
    ├── routes/
    │   ├── auth.py          ← Login, Register, OTP, Password
    │   ├── trips.py         ← Booking, lifecycle, rating
    │   ├── admin.py         ← Dashboard, analytics, management
    │   ├── notifications.py ← In-app notifications
    │   ├── wallet.py        ← Wallet top-up, payments
    │   └── promo.py         ← Promo codes & discounts
    ├── schemas/
    │   ├── auth.py          ← Auth request/response models
    │   └── trips.py         ← Trip request/response models
    └── utils/
        ├── fare.py          ← Fare calculator + surge pricing
        ├── matching.py      ← Driver matching algorithm
        ├── notifications.py ← Notification push service
        ├── otp.py           ← OTP generation & verification
        ├── security.py      ← JWT + password hashing
        ├── wallet.py        ← Wallet credit/debit/refund
        └── dependencies.py  ← Auth middleware
```

---

## ⚡ Quick Start (Run Locally)

### Step 1 — Install Python
Download Python 3.10+ from https://python.org

### Step 2 — Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4 — Setup Environment
```bash
# Copy the example env file
cp .env.example .env

# Open .env and change SECRET_KEY to something random
```

### Step 5 — Create Admin Account
```bash
python seed.py
```
This creates:
- **Phone:** `9000000000`
- **Password:** `admin@kloq123`

### Step 6 — Run the Server
```bash
uvicorn main:app --reload
```

### Step 7 — Open API Docs
Go to: **http://localhost:8000/docs**

You will see all 55 APIs with a visual interface to test them!

---

## 🔑 Authentication Flow

### New User (Rider)
```
1. POST /auth/otp/send       { "phone": "9876543210" }
   → Returns dev_otp (in DEV_MODE), user_exists: false

2. POST /auth/register/rider {
     "phone": "9876543210",
     "otp": "123456",
     "full_name": "Rahul Das",
     "password": "mypass123"   ← optional
   }
   → Returns JWT token
```

### Existing User Login
```
# Option A — OTP Login
POST /auth/otp/send          { "phone": "9876543210" }
POST /auth/otp/login         { "phone": "...", "otp": "123456" }

# Option B — Password Login
POST /auth/password/login    { "phone": "...", "password": "..." }

# Forgot Password
POST /auth/otp/send          { "phone": "..." }
POST /auth/password/set      { "phone": "...", "otp": "...", "new_password": "..." }
```

### Using the Token
Add this header to all protected API calls:
```
Authorization: Bearer <your_token_here>
```

---

## 🚗 Ride Booking Flow

```
1. GET  fare estimate   POST /trips/estimate
2. Book ride            POST /trips/book
3. Driver accepts       PATCH /trips/{id}/accept
4. Driver arrives       PATCH /trips/{id}/arrived
5. Trip starts          PATCH /trips/{id}/start
6. Trip completes       PATCH /trips/{id}/complete
7. Rider rates driver   POST /trips/{id}/rate
```

---

## 💰 Fare Structure

| Vehicle | Base | Per KM | Per Min | Min Fare |
|---------|------|--------|---------|----------|
| Bike    | ₹15  | ₹7     | ₹1      | ₹30      |
| Auto    | ₹20  | ₹10    | ₹1.5    | ₹40      |
| Mini    | ₹30  | ₹12    | ₹2      | ₹60      |
| Sedan   | ₹40  | ₹15    | ₹2.5    | ₹80      |
| SUV     | ₹60  | ₹20    | ₹3      | ₹120     |

### Surge Pricing
| Time        | Multiplier | Label         |
|-------------|-----------|---------------|
| 8am – 10am  | 1.5x      | Morning Peak  |
| 5pm – 8pm   | 1.5x      | Evening Peak  |
| 10pm – 11pm | 1.3x      | Night Demand  |
| 12am – 5am  | 1.2x      | Late Night    |

---

## 📡 All API Endpoints (55 total)

### 🔐 Auth (9)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /auth/otp/send | Send OTP to phone |
| POST | /auth/otp/login | Login via OTP |
| POST | /auth/password/login | Login via password |
| POST | /auth/password/set | Set/reset password |
| POST | /auth/register/rider | Register new rider |
| POST | /auth/register/driver | Register new driver |
| GET  | /auth/me | My profile |
| PATCH | /auth/driver/toggle-online | Go online/offline |
| PATCH | /auth/driver/location | Update GPS location |

### 🚗 Trips (12)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /trips/estimate | Fare for all vehicle types |
| POST | /trips/book | Book a ride |
| GET  | /trips/pending | Driver: see available trips |
| PATCH | /trips/{id}/accept | Driver accepts |
| PATCH | /trips/{id}/arrived | Driver arrived |
| PATCH | /trips/{id}/start | Start trip |
| PATCH | /trips/{id}/complete | Complete trip |
| PATCH | /trips/{id}/cancel | Cancel trip |
| GET  | /trips/my | Rider: my history |
| GET  | /trips/driver/my | Driver: my history |
| GET  | /trips/{id} | Trip detail |
| POST | /trips/{id}/rate | Rate driver |

### 🔔 Notifications (4)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | /notifications/ | My notifications |
| PATCH  | /notifications/read-all | Mark all read |
| PATCH  | /notifications/{id}/read | Mark one read |
| DELETE | /notifications/clear | Clear read notifications |

### 💰 Wallet (4)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | /wallet/ | Balance + transactions |
| POST | /wallet/add | Top up wallet |
| GET  | /wallet/transactions | Full history |
| POST | /wallet/admin/credit | Admin: credit user |

### 🎟️ Promo Codes (5)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST  | /promo/apply | Validate a promo |
| GET   | /promo/active | List active promos |
| POST  | /promo/admin/create | Admin: create promo |
| PATCH | /promo/admin/{id}/deactivate | Admin: deactivate |
| GET   | /promo/admin/all | Admin: all promos + stats |

### 🛡️ Admin (19)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | /admin/dashboard | Platform overview |
| GET  | /admin/drivers | List all drivers |
| PATCH | /admin/drivers/{id}/approve | Approve driver |
| PATCH | /admin/drivers/{id}/reject | Suspend driver |
| GET  | /admin/drivers/{id} | Driver profile |
| GET  | /admin/users | List all users |
| PATCH | /admin/users/{id}/deactivate | Ban user |
| PATCH | /admin/users/{id}/activate | Unban user |
| GET  | /admin/trips | All trips (filtered) |
| GET  | /admin/trips/live | Active trips now |
| GET  | /admin/analytics/revenue | Revenue by day |
| GET  | /admin/analytics/vehicle-type | By vehicle |
| GET  | /admin/analytics/top-drivers | Top 10 drivers |
| GET  | /admin/analytics/cancellation | Cancellation stats |
| POST | /admin/create-admin | Create admin account |

---

## 🚀 Production Deployment (Step by Step)

### Option A — Railway.app (Easiest)
```
1. Push code to GitHub
2. Go to railway.app → New Project → Deploy from GitHub
3. Add environment variables (DATABASE_URL, SECRET_KEY etc.)
4. Railway gives you a live URL automatically
```

### Option B — Ubuntu Server (VPS)
```bash
# Install dependencies
sudo apt update
sudo apt install python3 python3-pip python3-venv nginx

# Clone your repo
git clone https://github.com/yourusername/kloqride.git
cd kloqride

# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with production values

# Run with gunicorn (production server)
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 🔧 Switch to PostgreSQL

1. Install psycopg2:
```bash
pip install psycopg2-binary
```

2. In `.env`, change:
```
DATABASE_URL=postgresql://user:password@localhost:5432/kloqride
```

Free PostgreSQL options:
- **Supabase:** https://supabase.com (recommended)
- **Railway:** https://railway.app
- **ElephantSQL:** https://elephantsql.com

---

## 📱 SMS Setup (Fast2SMS — India)

1. Register at https://fast2sms.com
2. Get your API key
3. In `.env`: `FAST2SMS_API_KEY=your-key`
4. In `app/utils/otp.py`, update `send_sms()`:

```python
import requests
def send_sms(phone: str, message: str) -> bool:
    response = requests.post(
        "https://www.fast2sms.com/dev/bulkV2",
        headers={"authorization": os.getenv("FAST2SMS_API_KEY")},
        data={
            "message": message,
            "language": "english",
            "route": "q",
            "numbers": phone
        }
    )
    return response.json().get("return") == True
```

5. Set `DEV_MODE = False` in `app/utils/otp.py`

---

## 👤 Default Admin Credentials
```
Phone    : 9000000000
Password : admin@kloq123
```
⚠️ Change this immediately after first login!

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| Framework | FastAPI |
| Database | SQLite (dev) / PostgreSQL (prod) |
| ORM | SQLAlchemy |
| Auth | JWT (python-jose) |
| Password | bcrypt (passlib) |
| Validation | Pydantic v2 |
| Server | Uvicorn / Gunicorn |

---

## 📞 Support
Built by Claude for Kloq Ride — Bharat Mobility and Tech Solution Pvt. Ltd.  
Bardhaman, West Bengal 🇮🇳
