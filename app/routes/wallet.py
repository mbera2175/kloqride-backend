from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator
from app.models.database import get_db, User, WalletTransaction
from app.utils.dependencies import get_current_user, require_admin
from app.utils import wallet as wallet_svc

router = APIRouter(prefix="/wallet", tags=["Wallet"])

# ── Schemas ───────────────────────────────────────────────
class AddMoneyRequest(BaseModel):
    amount : float
    @validator("amount")
    def validate_amount(cls, v):
        if v < 10:
            raise ValueError("Minimum top-up is ₹10")
        if v > 10000:
            raise ValueError("Maximum top-up is ₹10,000 per transaction")
        return round(v, 2)

# ── Endpoints ─────────────────────────────────────────────
@router.get("/", summary="My wallet balance and transactions")
def get_wallet(
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db),
    limit       : int     = 20,
    offset      : int     = 0
):
    txns = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.user_id == current_user.id)
        .order_by(WalletTransaction.created_at.desc())
        .offset(offset).limit(limit).all()
    )
    return {
        "balance"     : current_user.wallet_balance,
        "transactions": [_fmt_txn(t) for t in txns],
    }


@router.post("/add", summary="Add money to wallet (simulate payment gateway)")
def add_money(
    data        : AddMoneyRequest,
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db)
):
    """
    In production: integrate Razorpay/PhonePe here before crediting.
    For now: direct credit (dev/demo mode).
    """
    wallet_svc.credit(
        db, current_user, data.amount,
        description=f"Wallet top-up ₹{data.amount}"
    )
    db.commit()
    return {
        "message"        : f"₹{data.amount} added to your wallet.",
        "new_balance"    : current_user.wallet_balance,
    }


@router.get("/transactions", summary="Full transaction history")
def transaction_history(
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db),
    txn_type    : str     = None,
    limit       : int     = 50,
    offset      : int     = 0,
):
    q = db.query(WalletTransaction).filter(WalletTransaction.user_id == current_user.id)
    if txn_type:
        q = q.filter(WalletTransaction.txn_type == txn_type)
    txns = q.order_by(WalletTransaction.created_at.desc()).offset(offset).limit(limit).all()
    return [_fmt_txn(t) for t in txns]


# ── Admin: manually credit/refund a user's wallet ─────────
@router.post("/admin/credit", summary="Admin: credit a user's wallet")
def admin_credit(
    user_id    : int,
    amount     : float,
    description: str,
    admin      = Depends(require_admin),
    db         : Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    wallet_svc.credit(db, user, amount, description=f"[Admin] {description}")
    db.commit()
    return {"message": f"₹{amount} credited to {user.full_name}.", "new_balance": user.wallet_balance}


def _fmt_txn(t):
    return {
        "id"          : t.id,
        "type"        : t.txn_type,
        "amount"      : t.amount,
        "description" : t.description,
        "balance_after": t.balance_after,
        "trip_id"     : t.trip_id,
        "created_at"  : t.created_at,
    }
