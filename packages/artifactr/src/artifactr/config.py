"""Settings for the backend."""

from pydantic import EmailStr, Field
from pydantic_extra_types.semantic_version import SemanticVersion
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the backend."""

    model_config = SettingsConfigDict(
        validate_default=True, populate_by_name=True, extra="allow"
    )

    # App Settings
    title: str = "Idea"
    description: str = "The ideation backend."
    version: SemanticVersion = SemanticVersion(0, 1, 0, "alpha", 1)
    support_email: EmailStr = "support@example.com"

    openai_api_key: str = Field(default="")

    # Mode
    mode: str = Field(default="development")

    # Database Settings
    db_url: str | None = Field(
        description="The URL for the database (supports SQLite, MySQL, PostgreSQL, etc.).",
        default=None,
    )

    # MCP Settings
    mcp_idea_host: str = Field(default="127.0.0.1")
    mcp_idea_port: int = Field(default=8001)

    # WebSocket Settings
    put_timeout: float = 1.0
    ws_receive_timeout: float = 30.0
    heartbeat_interval: float = 10.0
    protocol_version: str = "1.0"
    queue_maxsize: int = 50


def get_settings() -> Settings:
    """Get the settings."""
    return Settings()
