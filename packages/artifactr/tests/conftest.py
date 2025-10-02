from datetime import datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from artifactr.config import get_settings
from artifactr.db import DatabaseManager
from artifactr.dependencies import get_db, get_session
from artifactr.main import app
from artifactr.models.db import Thread


# Mock agent class for testing
class MockAgent:
    """Mock agent for testing purposes."""

    def run_stream(self, message):
        """Mock implementation of run_stream."""
        return None


@pytest.fixture(name="engine")
def engine_fixture():
    """Create a SQLAlchemy engine for testing."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(engine):
    """Create a session for testing with a proper bind to the engine."""
    with Session(engine) as session:
        yield session


@pytest_asyncio.fixture(name="client")
async def client_fixture(session: Session):
    settings = get_settings()

    def get_session_override():
        return session

    def get_db_override():
        return DatabaseManager(session)

    def get_settings_override():
        return settings

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_db] = get_db_override
    app.dependency_overrides[get_settings] = get_settings_override

    # Set up a mock agent in the app state for testing
    app.state.idea_agent = MockAgent()

    client = TestClient(app)
    yield client

    # Clean up
    app.dependency_overrides.clear()
    if hasattr(app.state, "idea_agent"):
        delattr(app.state, "idea_agent")


@pytest.fixture
def thread(session: Session):
    """Create a test thread directly in the database."""
    thread = Thread(
        title="Test Thread",
        description="A test thread for testing",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    session.add(thread)
    session.commit()
    session.refresh(thread)
    return thread
