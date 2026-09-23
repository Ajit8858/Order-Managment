import logging
import os
import uuid

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.celery_app import celery_app
from app.models.order import Order
from app.tasks.db import sync_db_session

logger = logging.getLogger(__name__)

INVOICE_DIR = os.environ.get("INVOICE_DIR", "/tmp/invoices")


@celery_app.task(name="app.tasks.invoice_tasks.generate_invoice", bind=True, max_retries=2)
def generate_invoice(self, order_id: str):
    os.makedirs(INVOICE_DIR, exist_ok=True)

    with sync_db_session() as db:
        order = db.execute(select(Order).where(Order.id == uuid.UUID(order_id))).scalar_one_or_none()
        if order is None:
            logger.warning("generate_invoice: order %s not found", order_id)
            return {"generated": False}

        file_path = os.path.join(INVOICE_DIR, f"invoice_{order_id}.pdf")
        c = canvas.Canvas(file_path, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, "INVOICE")
        c.setFont("Helvetica", 11)
        c.drawString(50, 770, f"Order ID: {order.id}")
        c.drawString(50, 755, f"Status: {order.status.value}")
        c.drawString(50, 740, f"Total: {order.total_amount}")

        y = 700
        c.drawString(50, y, "Items:")
        y -= 20
        for item in order.items:
            c.drawString(60, y, f"- {item.product.name}  x{item.quantity}  @ {item.unit_price}")
            y -= 18

        c.save()
        logger.info("Invoice generated at %s", file_path)
        return {"generated": True, "path": file_path}
