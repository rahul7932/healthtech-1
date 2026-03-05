"""
Demo usage limiter.

Enforces a small per-IP allowance of demo queries against the main API,
backed by the PostgreSQL database so limits persist across restarts.
"""

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.demo_usage import DemoUsage

logger = logging.getLogger(__name__)


async def enforce_demo_limit(ip_address: str, db: AsyncSession) -> None:
    """
    Enforce a per-IP demo request limit.

    If the given IP has already consumed its allowance, raises HTTPException(429).
    Otherwise, increments the counter for this IP.
    """
    settings = get_settings()

    # Allow disabling via config (e.g., for local development).
    if not getattr(settings, "demo_limit_enabled", True):
        return

    max_requests: int = getattr(settings, "demo_limit_max_requests", 2)
    if max_requests <= 0:
        # Treat non-positive values as "no limit".
        return

    # Try to find an existing usage row for this IP, locking it to avoid races.
    result = await db.execute(
        select(DemoUsage).where(DemoUsage.ip_address == ip_address).with_for_update()
    )
    usage = result.scalar_one_or_none()

    if usage is None:
        # First request from this IP.
        usage = DemoUsage(ip_address=ip_address, request_count=1)
        db.add(usage)
        try:
            await db.commit()
        except Exception:
            logger.exception("Failed to create demo usage record")
            await db.rollback()
            raise
        return

    if usage.request_count >= max_requests:
        logger.info(
            "Demo limit reached for IP %s (count=%d, max=%d)",
            ip_address,
            usage.request_count,
            max_requests,
        )
        raise HTTPException(
            status_code=429,
            detail="Demo limit reached for this IP. Please contact us for full access.",
        )

    usage.request_count += 1

    try:
        await db.commit()
    except Exception:
        logger.exception("Failed to update demo usage record for IP %s", ip_address)
        await db.rollback()
        raise

