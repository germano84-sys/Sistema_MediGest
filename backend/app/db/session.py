import hashlib
import hmac
from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings


engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
)


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Open a transaction with a signed, transaction-local tenant context."""
    settings = get_settings()
    signature = hmac.new(
        settings.tenant_context_secret.encode("utf-8"),
        str(tenant_id).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.execute(
            text(
                "SELECT app_private.set_tenant_context("
                "CAST(:tenant_id AS uuid), :signature)"
            ),
            {"tenant_id": str(tenant_id), "signature": signature},
        )
        yield session


@contextmanager
def platform_session() -> Iterator[Session]:
    """Open a transaction with a signed platform-wide administration context."""
    settings = get_settings()
    signature = hmac.new(
        settings.tenant_context_secret.encode("utf-8"),
        b"medigest:platform",
        hashlib.sha256,
    ).hexdigest()

    with Session(engine, expire_on_commit=False) as session, session.begin():
        session.execute(
            text("SELECT app_private.set_platform_context(:signature)"),
            {"signature": signature},
        )
        yield session
