"""Check-outs in a SQL database."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from artifactr.files.checkouts import Checkout
from artifactr.files.sql.tables import CheckoutRow
from artifactr.workspace import Scope
from lattice_core.sql.sessions import awaited_to_the_end
from lattice_core.sql.tenancy import TENANT_KEY, TenantSession


class SqlCheckouts:
    """The [`Checkouts`][artifactr.files.checkouts.Checkouts] port in a SQL database.

    Args:
        engine: The database. The store does not dispose of it.
        row_level_security: Whether each transaction names its tenant to PostgreSQL.
    """

    def __init__(self, engine: AsyncEngine, *, row_level_security: bool = False) -> None:
        self._sessions = async_sessionmaker(
            engine,
            expire_on_commit=False,
            sync_session_class=TenantSession if row_level_security else Session,
        )

    def _session(self, scope: Scope) -> AsyncSession:
        return self._sessions(info={TENANT_KEY: scope.tenant_id})

    @awaited_to_the_end
    async def save(self, scope: Scope, checkout: Checkout) -> None:
        """Keep a check-out, replacing one with its id."""
        row = CheckoutRow(
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            id=checkout.id,
            artifact_id=checkout.artifact_id,
            base_version=checkout.base_version,
            base_sha256=checkout.base_sha256,
            actor=checkout.actor.model_dump(mode="json"),
            expires_at=checkout.expires_at,
            checked_in=checkout.checked_in,
        )
        async with self._session(scope) as session, session.begin():
            await session.merge(row)

    @awaited_to_the_end
    async def get(self, scope: Scope, checkout_id: str) -> Checkout | None:
        """Return a check-out, or None."""
        async with self._session(scope) as session:
            row = await session.get(CheckoutRow, (scope.tenant_id, scope.workspace_id, checkout_id))
        return None if row is None else Checkout.model_validate(row, from_attributes=True)
