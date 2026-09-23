import logging
import uuid

from sqlalchemy import select

from app.celery_app import celery_app
from app.models.product import Product
from app.tasks.db import sync_db_session

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.inventory_tasks.decrement_stock", bind=True, max_retries=3)
def decrement_stock(self, product_id: str, quantity: int):
    """Async, best-effort ledger update. The authoritative stock check/deduction
    happens synchronously in the order-creation transaction; this task exists
    for follow-on bookkeeping (e.g. low-stock alerts) without blocking checkout.
    """
    with sync_db_session() as db:
        product = db.execute(select(Product).where(Product.id == uuid.UUID(product_id))).scalar_one_or_none()
        if product is None:
            logger.warning("decrement_stock: product %s not found", product_id)
            return

        if product.stock <= 5:
            logger.warning("LOW STOCK ALERT: product=%s stock=%s", product.name, product.stock)

        return {"product_id": product_id, "stock": product.stock}
