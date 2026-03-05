"""
SQLAlchemy model for tracking demo usage per IP address.

Used to enforce a small per-IP request allowance for the main query endpoint,
so that anonymous users can try the system without exhausting upstream quotas.
"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DemoUsage(Base):
    """
    Per-IP demo usage counter.

    Each row tracks how many demo queries a given IP address has used.
    The enforcement logic is implemented in the demo_limit service.
    """

    __tablename__ = "demo_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # IP address of the client (IPv4 or IPv6).
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, index=True)

    # Number of demo queries consumed by this IP.
    request_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamp of the first request from this IP (for observability).
    first_request_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

