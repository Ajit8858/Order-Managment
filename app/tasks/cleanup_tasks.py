import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete

from app.celery_app import celery_app
from app.models.user import RefreshToken
from app.models.order import Order, OrderStatus
from app.tasks.db import sync_db_session

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.cleanup_tasks.cleanup_expired_refresh_tokens")
def cleanup_expired_refresh_tokens():
    with sync_db_session() as db:
        now = datetime.now(timezone.utc)
        result = db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
        logger.info("Cleaned up %s expired refresh tokens", result.rowcount)
        return {"deleted": result.rowcount}


@celery_app.task(name="app.tasks.cleanup_tasks.cancel_stale_pending_orders")
def cancel_stale_pending_orders():
    """Orders left PENDING (never paid) for more than 24h are auto-cancelled."""
    with sync_db_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        stale = db.execute(
            select(Order).where(Order.status == OrderStatus.PENDING, Order.created_at < cutoff)
        ).scalars().all()
        for order in stale:
            order.status = OrderStatus.CANCELLED
        logger.info("Cancelled %s stale pending orders", len(stale))
        return {"cancelled": len(stale)}
