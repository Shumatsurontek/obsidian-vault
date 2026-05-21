"""Settings for the vault MCP server."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Direct filesystem access — no API key, no plugin.
    vault_path: str = Field(alias="VAULT_PATH")

    # MCP server
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    mcp_static_token: str = Field(default="", alias="MCP_STATIC_TOKEN")
    mcp_user_email: str = Field(default="", alias="MCP_USER_EMAIL")
    mcp_user_name: str = Field(default="", alias="MCP_USER_NAME")
