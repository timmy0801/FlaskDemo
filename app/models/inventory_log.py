from datetime import datetime, timezone
from app import db
from sqlalchemy import CheckConstraint


class InventoryLog(db.Model):
    __tablename__ = "inventory_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('deduct', 'restock', 'adjust')",
            name="ck_inventorylog_action_valid",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    action = db.Column(db.String(20), nullable=False)
    # action: 'deduct'（訂單扣除）/ 'restock'（補貨）/ 'adjust'（人工調整）
    quantity_before = db.Column(db.Integer, nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)  # 負數為扣除
    quantity_after = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    product = db.relationship(
        "Product", backref=db.backref("inventory_logs", lazy=True)
    )

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "order_id": self.order_id,
            "action": self.action,
            "quantity_before": self.quantity_before,
            "quantity_change": self.quantity_change,
            "quantity_after": self.quantity_after,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }
