"""Agent configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model: str = Field(default="anthropic:claude-opus-4-7", alias="AGENT_MODEL")
    mcp_url: str = Field(default="http://127.0.0.1:8000/mcp", alias="MCP_URL")
    mcp_static_token: str = Field(default="", alias="MCP_STATIC_TOKEN")

    langsmith_project: str = Field(default="vault-mcp", alias="LANGSMITH_PROJECT")
    langsmith_tracing: bool = Field(default=True, alias="LANGSMITH_TRACING")
