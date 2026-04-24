from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.database import User, WalletTransaction


def credit(db: Session, user: User, amount: float, description: str, trip_id: int = None):
    """Add money to wallet."""
    user.wallet_balance = round(user.wallet_balance + amount, 2)
    txn = WalletTransaction(
        user_id      = user.id,
        amount       = amount,
        txn_type     = "credit",
        description  = description,
        trip_id      = trip_id,
        balance_after= user.wallet_balance,
    )
    db.add(txn)


def debit(db: Session, user: User, amount: float, description: str, trip_id: int = None):
    """Deduct from wallet. Raises error if insufficient balance."""
    if user.wallet_balance < amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance. Available: ₹{user.wallet_balance}, Required: ₹{amount}"
        )
    user.wallet_balance = round(user.wallet_balance - amount, 2)
    txn = WalletTransaction(
        user_id      = user.id,
        amount       = amount,
        txn_type     = "debit",
        description  = description,
        trip_id      = trip_id,
        balance_after= user.wallet_balance,
    )
    db.add(txn)


def refund(db: Session, user: User, amount: float, description: str, trip_id: int = None):
    """Refund money to wallet."""
    user.wallet_balance = round(user.wallet_balance + amount, 2)
    txn = WalletTransaction(
        user_id      = user.id,
        amount       = amount,
        txn_type     = "refund",
        description  = description,
        trip_id      = trip_id,
        balance_after= user.wallet_balance,
    )
    db.add(txn)
