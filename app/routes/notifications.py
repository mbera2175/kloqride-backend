from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.models.database import get_db, User, Notification
from app.utils.dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/", summary="My notifications")
def get_notifications(
    current_user: User    = Depends(get_current_user),
    db          : Session = Depends(get_db),
    unread_only : bool    = False,
    limit       : int     = 30,
    offset      : int     = 0,
):
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        q = q.filter(Notification.is_read == False)
    notifications = q.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()
    unread_count  = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    return {
        "unread_count"  : unread_count,
        "notifications" : [_fmt(n) for n in notifications],
    }


@router.patch("/read-all", summary="Mark all notifications as read")
def mark_all_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read."}


@router.patch("/{notif_id}/read", summary="Mark one notification as read")
def mark_read(notif_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id
    ).first()
    if n:
        n.is_read = True
        db.commit()
    return {"message": "Marked as read."}


@router.delete("/clear", summary="Delete all read notifications")
def clear_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    deleted = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == True
    ).delete()
    db.commit()
    return {"message": f"Cleared {deleted} notifications."}


def _fmt(n):
    return {
        "id"        : n.id,
        "title"     : n.title,
        "message"   : n.message,
        "type"      : n.notif_type,
        "is_read"   : n.is_read,
        "trip_id"   : n.trip_id,
        "created_at": n.created_at,
    }
